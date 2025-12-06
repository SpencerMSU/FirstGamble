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
    "bag11": {"name": "Полевой контейнер", "cost": 125, "cap_add": 3000},
    "bag12": {"name": "Стабилизированный ранец", "cost": 160, "cap_add": 4000},
    "bag13": {"name": "Астероидный бокс", "cost": 200, "cap_add": 5200},
    "bag14": {"name": "Квантовый рюкзак", "cost": 250, "cap_add": 6600},
    "bag15": {"name": "Хранилище первопроходца", "cost": 310, "cap_add": 8200},
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

RPG_AUTO_MINERS = [
    {
        "id": "auto_wood",
        "name": "Дроворуб",
        "resource": "wood",
        "rate": 6,
        "interval": 60,
        "requires": {"wood": 1200},
        "bag_req": "bag3",
    },
    {
        "id": "auto_stone",
        "name": "Каменный экскаватор",
        "resource": "stone",
        "rate": 4,
        "interval": 90,
        "requires": {"wood": 1500, "stone": 900},
        "bag_req": "bag5",
    },
    {
        "id": "auto_iron",
        "name": "Железный бур",
        "resource": "iron",
        "rate": 3,
        "interval": 120,
        "requires": {"stone": 1400, "iron": 600},
        "bag_req": "bag7",
    },
    {
        "id": "auto_silver",
        "name": "Серебряный конвейер",
        "resource": "silver",
        "rate": 2,
        "interval": 180,
        "requires": {"iron": 950, "silver": 400},
        "bag_req": "bag9",
    },
    {
        "id": "auto_gold",
        "name": "Золотой комбайн",
        "resource": "gold",
        "rate": 1,
        "interval": 240,
        "requires": {"silver": 850, "gold": 250},
        "bag_req": "bag11",
    },
]


def key_rpg_res(uid: int) -> str:
    return f"user:{uid}:rpg:res"


def key_rpg_cd(uid: int) -> str:
    return f"user:{uid}:rpg:cd"


def key_rpg_owned(uid: int, cat: str) -> str:
    return f"user:{uid}:rpg:owned:{cat}"


def key_rpg_auto(uid: int) -> str:
    return f"user:{uid}:rpg:auto"


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


def rpg_auto_requirements(cfg: Dict[str, Any], res: Dict[str, int], owned: Dict[str, Any]):
    reqs = cfg.get("requires", {}) or {}
    missing_res = {}
    for k, need in reqs.items():
        have = res.get(k, 0)
        if have < int(need):
            missing_res[k] = int(need)

    bag_req = cfg.get("bag_req")
    has_bag = (not bag_req) or (bag_req in owned.get("bags", []))
    return missing_res, has_bag


async def rpg_apply_auto(uid: int, res: Dict[str, int], cap_add: Dict[str, int]):
    r = await get_redis()
    auto_raw = await r.hgetall(key_rpg_auto(uid))
    now = int(time.time())
    pipe = r.pipeline()
    for cfg in RPG_AUTO_MINERS:
        raw_state = auto_raw.get(cfg["id"])
        state: Dict[str, Any] = {}
        if raw_state:
            try:
                state = json.loads(raw_state)
            except Exception:
                state = {}
        if not state.get("active"):
            continue

        last = safe_int(state.get("last"), now)
        interval = int(cfg.get("interval", 60))
        if interval <= 0:
            continue
        ticks = max(0, (now - last) // interval)
        if ticks <= 0:
            continue

        gain = ticks * int(cfg.get("rate", 1))
        res_name = cfg.get("resource")
        cap = RPG_MAX + int(cap_add.get(res_name, 0))
        cur_val = res.get(res_name, 0)
        add_val = min(gain, max(0, cap - cur_val))
        if add_val > 0:
            res[res_name] = cur_val + add_val
            pipe.hset(key_rpg_res(uid), res_name, res[res_name])

        state["last"] = last + ticks * interval
        pipe.hset(key_rpg_auto(uid), cfg["id"], json.dumps(state))

    if pipe.command_stack:
        await pipe.execute()
    return res


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
    res = await rpg_apply_auto(uid, res, cap_add)

    auto_raw = await r.hgetall(key_rpg_auto(uid))
    auto_list = []
    now = int(time.time())
    for cfg in RPG_AUTO_MINERS:
        raw_state = auto_raw.get(cfg["id"])
        state: Dict[str, Any] = {}
        if raw_state:
            try:
                state = json.loads(raw_state)
            except Exception:
                state = {}
        active = bool(state.get("active"))
        last_tick = safe_int(state.get("last"), 0)
        next_tick = last_tick + int(cfg.get("interval", 0)) if active else 0
        missing_res, has_bag = rpg_auto_requirements(cfg, res, owned)
        auto_list.append(
            {
                "id": cfg["id"],
                "name": cfg.get("name", ""),
                "resource": cfg.get("resource"),
                "rate": int(cfg.get("rate", 1)),
                "interval": int(cfg.get("interval", 60)),
                "requires": cfg.get("requires", {}),
                "bag_req": cfg.get("bag_req"),
                "active": active,
                "last_tick": last_tick,
                "next_tick": next_tick,
                "unlocked": not missing_res and has_bag,
                "missing": missing_res,
                "has_bag": has_bag,
            }
        )

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
        "auto": {"miners": auto_list, "now": now},
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
