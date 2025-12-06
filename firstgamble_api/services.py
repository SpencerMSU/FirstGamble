import hmac
import hashlib
import json
import time
from typing import Any, Dict, Optional

from .config import BOT_TOKEN, CONSERVE_AUTH_TOKEN
from .models import AuthContext
from .redis_utils import (
    ALLOWED_GAMES,
    USERS_ZSET,
    add_points,
    ensure_user,
    get_balance,
    get_redis,
    key_balance,
    key_confirmed,
    key_gamestats,
    key_profile,
    key_stats,
    safe_int,
)

RPG_RESOURCES = [
    "wood",
    "stone",
    "iron",
    "silver",
    "gold",
    "crystal",
    "mythril",
    "relic",
    "essence",
]
RPG_MAX = 999

RPG_ACCESSORIES = {
    "acc1": {"name": "Талисман удачи", "cost": 3, "cd_red": 0.05, "yield_add": 0.05},
    "acc2": {"name": "Кольцо шахтёра", "cost": 5, "cd_red": 0.08, "yield_add": 0.07},
    "acc3": {"name": "Амулет времени", "cost": 8, "cd_red": 0.10, "yield_add": 0.06},
    "acc4": {"name": "Браслет скорости", "cost": 12, "cd_red": 0.12, "yield_add": 0.08},
    "acc5": {"name": "Печать старателя", "cost": 16, "cd_red": 0.15, "yield_add": 0.10},
    "acc6": {"name": "Подвеска кристалла", "cost": 22, "cd_red": 0.18, "yield_add": 0.12},
    "acc7": {"name": "Сердце леса", "cost": 7, "cd_red": 0.06, "yield_add": 0.09},
    "acc8": {"name": "Око горы", "cost": 11, "cd_red": 0.09, "yield_add": 0.11},
    "acc9": {"name": "Звезда артефактов", "cost": 18, "cd_red": 0.13, "yield_add": 0.14},
    "acc10": {"name": "Корона старателя", "cost": 30, "cd_red": 0.20, "yield_add": 0.20},
}

RPG_TOOLS = {
    "tool1": {"name": "Кирка новичка", "cost": 2, "cd_red": 0.00, "yield_add": 0.05},
    "tool2": {"name": "Каменная кирка", "cost": 4, "cd_red": 0.04, "yield_add": 0.07},
    "tool3": {"name": "Железная кирка", "cost": 7, "cd_red": 0.06, "yield_add": 0.10},
    "tool4": {"name": "Серебряная кирка", "cost": 10, "cd_red": 0.08, "yield_add": 0.12},
    "tool5": {"name": "Золотая кирка", "cost": 14, "cd_red": 0.10, "yield_add": 0.15},
    "tool6": {"name": "Кристальная кирка", "cost": 20, "cd_red": 0.12, "yield_add": 0.18},
    "tool7": {"name": "Буровой молот", "cost": 24, "cd_red": 0.15, "yield_add": 0.20},
    "tool8": {"name": "Резак руды", "cost": 28, "cd_red": 0.18, "yield_add": 0.22},
}

RPG_BAGS = {
    "bag1": {"name": "Мешок из ткани", "cost": 3, "cap_add": 50},
    "bag2": {"name": "Сумка старателя", "cost": 6, "cap_add": 100},
    "bag3": {"name": "Рюкзак шахтёра", "cost": 12, "cap_add": 200},
    "bag4": {"name": "Укреплённый рюкзак", "cost": 18, "cap_add": 300},
    "bag5": {"name": "Экспедиционный мешок", "cost": 25, "cap_add": 450},
    "bag6": {"name": "Каркасная сумка", "cost": 33, "cap_add": 650},
    "bag7": {"name": "Горный баул", "cost": 42, "cap_add": 900},
    "bag8": {"name": "Сумка инженера", "cost": 55, "cap_add": 1200},
    "bag9": {"name": "Артефактный рюкзак", "cost": 70, "cap_add": 1600},
    "bag10": {"name": "Легендарный контейнер", "cost": 95, "cap_add": 2200},
}

RPG_SELL_VALUES = {
    "wood": 1,
    "stone": 2,
    "iron": 5,
    "silver": 8,
    "gold": 12,
    "crystal": 20,
    "mythril": 30,
    "relic": 45,
    "essence": 70,
}
RPG_CHAIN = [
    ("wood", "stone"),
    ("stone", "iron"),
    ("iron", "silver"),
    ("silver", "gold"),
    ("gold", "crystal"),
    ("crystal", "mythril"),
    ("mythril", "relic"),
    ("relic", "essence"),
]


def key_rpg_res(uid: int) -> str:
    return f"user:{uid}:rpg:res"


def key_rpg_cd(uid: int) -> str:
    return f"user:{uid}:rpg:cd"


def key_rpg_owned(uid: int, cat: str) -> str:
    return f"user:{uid}:rpg:owned:{cat}"


def key_ticket_counter() -> str:
    return "raffle:ticket:counter"


def key_user_tickets(uid: int) -> str:
    return f"user:{uid}:raffle:tickets"


def key_ticket_owners() -> str:
    return "raffle:ticket:owners"  # hash: ticket -> user_id


def key_prize_counter() -> str:
    return "raffle:prize:counter"


def key_prizes_set() -> str:
    return "raffle:prizes"


def key_prize_item(pid: int) -> str:
    return f"raffle:prize:{pid}"


def key_prizes_visible() -> str:
    return "raffle:prizes_visible"


def key_raffle_winners() -> str:
    return "raffle:winners"


def key_last_raffle_winners() -> str:
    return "raffle:last_winners"


def key_raffle_status() -> str:
    return "raffle:status"


def key_user_raffle_wins(uid: int) -> str:
    return f"user:{uid}:raffle:wins"


def rpg_calc_buffs(owned: Dict[str, Any]):
    cd_mult = 1.0
    yield_add = 0.0
    cap_add = {r: 0 for r in RPG_RESOURCES}

    for tid in owned.get("tools", []):
        it = RPG_TOOLS.get(tid)
        if it:
            cd_mult *= (1.0 - float(it.get("cd_red", 0.0)))
            yield_add += float(it.get("yield_add", 0.0))

    for aid in owned.get("acc", []):
        it = RPG_ACCESSORIES.get(aid)
        if it:
            cd_mult *= (1.0 - float(it.get("cd_red", 0.0)))
            yield_add += float(it.get("yield_add", 0.0))

    for bid in owned.get("bags", []):
        it = RPG_BAGS.get(bid)
        if it:
            add = int(it.get("cap_add", 0))
            for r in cap_add:
                cap_add[r] += add

    cd_mult = max(0.2, min(cd_mult, 1.0))
    yield_add = max(0.0, min(yield_add, 1.0))
    return cd_mult, yield_add, cap_add


async def rpg_ensure(uid: int):
    r = await get_redis()
    pipe = r.pipeline()
    for res in RPG_RESOURCES:
        pipe.hsetnx(key_rpg_res(uid), res, 0)
    pipe.setnx(key_rpg_cd(uid), 0)
    await pipe.execute()


async def rpg_get_owned(uid: int):
    r = await get_redis()
    tools = await r.smembers(key_rpg_owned(uid, "tools"))
    acc = await r.smembers(key_rpg_owned(uid, "acc"))
    bags = await r.smembers(key_rpg_owned(uid, "bags"))
    return {"tools": list(tools), "acc": list(acc), "bags": list(bags)}


async def rpg_state(uid: int):
    r = await get_redis()
    await rpg_ensure(uid)
    bal = safe_int(await r.get(key_balance(uid)))
    res = await r.hgetall(key_rpg_res(uid))
    res = {k: safe_int(v) for k, v in res.items()}
    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add = rpg_calc_buffs(owned)
    next_ts = safe_int(await r.get(key_rpg_cd(uid)))
    now = int(time.time())
    cooldown_remaining = max(0, next_ts - now)
    return {
        "balance": bal,
        "resources": res,
        "owned": owned,
        "cooldown_remaining": cooldown_remaining,
        "cooldown_until": next_ts,
        "buffs": {"cd_mult": cd_mult, "yield_add": yield_add},
        "caps": cap_add,
    }


def rpg_roll_gather():
    import random

    return {
        "wood": random.randint(2, 5),
        "stone": random.randint(1, 4),
        "iron": random.randint(0, 3),
        "silver": 0,
        "gold": 0,
        "crystal": 0,
        "mythril": 0,
        "relic": 0,
        "essence": 0,
    }


def _build_tg_secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


TG_SECRET_KEY = _build_tg_secret(BOT_TOKEN)


def parse_init_data(init_data: str) -> Dict[str, Any]:
    from urllib.parse import parse_qsl

    if not init_data:
        raise ValueError("empty initData")

    pairs = parse_qsl(init_data, strict_parsing=True)
    data: Dict[str, str] = {}
    for k, v in pairs:
        data[k] = v

    hash_value = data.pop("hash", None)
    if not hash_value:
        raise ValueError("no hash in initData")

    data_check_array = [f"{k}={v}" for k, v in sorted(data.items())]
    data_check_string = "\n".join(data_check_array)

    h = hmac.new(TG_SECRET_KEY, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if h != hash_value:
        raise ValueError("initData hash mismatch")

    if "user" in data:
        try:
            data["user"] = json.loads(data["user"])
        except Exception:
            raise ValueError("bad user json")

    return data


def _normalize_username(username: Optional[str]) -> str:
    if not username:
        return ""
    username = str(username).strip()
    if username.startswith("@"):  # убираем @ для хранения
        username = username[1:]
    return username


def _ensure_profile_identity_fields(profile: Dict[str, Any], username: Optional[str], tg_id: Optional[int]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    uname = _normalize_username(username)
    if uname and not profile.get("username"):
        mapping["username"] = uname
    if tg_id and not profile.get("tg_id"):
        mapping["tg_id"] = str(tg_id)
    return mapping


def is_conserve_token(token: Optional[str]) -> bool:
    return bool(CONSERVE_AUTH_TOKEN and token and token == CONSERVE_AUTH_TOKEN)


def build_auth_context_from_headers(
    method: str,
    request_body: Optional[Dict[str, Any]],
    query_params: Dict[str, Any],
    telegram_init_data: Optional[str],
    conserve_header: Optional[str],
) -> AuthContext:
    if telegram_init_data:
        data = parse_init_data(telegram_init_data)
        user = data.get("user") or {}
        uid = int(user.get("id"))
        return AuthContext(
            user_id=uid,
            from_telegram=True,
            from_conserve=False,
            username=user.get("username"),
            tg_id=uid,
        )

    if is_conserve_token(conserve_header):
        uid_val: Optional[int] = None
        if method.upper() == "GET":
            uid_val = safe_int(query_params.get("user_id"))
        else:
            uid_val = safe_int((request_body or {}).get("user_id"))
        if not uid_val or uid_val <= 0:
            raise ValueError("user_id required for external auth")
        return AuthContext(user_id=uid_val, from_telegram=False, from_conserve=True)

    raise ValueError("unauthorized")
