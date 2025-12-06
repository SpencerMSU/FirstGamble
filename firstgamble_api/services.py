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
RPG_CONVERT_RATE_DEFAULT = 5
RPG_BASE_CD_DEFAULT = 300

RPG_ACCESSORIES = {
    "acc1": {
        "name": "Тканевая подвязка",
        "level": 1,
        "cost": 4,
        "cd_red": 0.03,
        "convert_bonus": 0.02,
        "yield_add": 0.02,
    },
    "acc2": {
        "name": "Жетон старателя",
        "level": 2,
        "cost": 7,
        "cd_red": 0.05,
        "convert_bonus": 0.04,
        "yield_add": 0.03,
    },
    "acc3": {
        "name": "Кольцо ускорения",
        "level": 3,
        "cost": 11,
        "cd_red": 0.07,
        "convert_bonus": 0.06,
        "yield_add": 0.05,
    },
    "acc4": {
        "name": "Амулет руды",
        "level": 4,
        "cost": 15,
        "cd_red": 0.10,
        "convert_bonus": 0.08,
        "yield_add": 0.06,
    },
    "acc5": {
        "name": "Браслет инженера",
        "level": 5,
        "cost": 21,
        "cd_red": 0.12,
        "convert_bonus": 0.10,
        "yield_add": 0.08,
    },
    "acc6": {
        "name": "Фазовый талисман",
        "level": 6,
        "cost": 28,
        "cd_red": 0.15,
        "convert_bonus": 0.12,
        "yield_add": 0.10,
    },
    "acc7": {
        "name": "Печать реликтов",
        "level": 7,
        "cost": 36,
        "cd_red": 0.18,
        "convert_bonus": 0.15,
        "yield_add": 0.12,
    },
    "acc8": {
        "name": "Корона алхимика",
        "level": 8,
        "cost": 45,
        "cd_red": 0.22,
        "convert_bonus": 0.18,
        "yield_add": 0.14,
    },
}

RPG_TOOLS = {
    "tool1": {
        "name": "Кирка новичка",
        "cost": 3,
        "cd_red": 0.00,
        "yield_add": 0.04,
        "extra_drops": [{"resource": "wood", "chance": 0.05, "amount": 1}],
    },
    "tool2": {
        "name": "Каменный долот",
        "cost": 6,
        "cd_red": 0.03,
        "yield_add": 0.06,
        "extra_drops": [{"resource": "stone", "chance": 0.08, "amount": 1}],
    },
    "tool3": {
        "name": "Железная кирка",
        "cost": 10,
        "cd_red": 0.05,
        "yield_add": 0.08,
        "extra_drops": [{"resource": "iron", "chance": 0.10, "amount": 1}],
    },
    "tool4": {
        "name": "Серебряная кирка",
        "cost": 15,
        "cd_red": 0.07,
        "yield_add": 0.10,
        "extra_drops": [{"resource": "silver", "chance": 0.12, "amount": 1}],
    },
    "tool5": {
        "name": "Золотая дрель",
        "cost": 21,
        "cd_red": 0.09,
        "yield_add": 0.12,
        "extra_drops": [{"resource": "gold", "chance": 0.15, "amount": 1}],
    },
    "tool6": {
        "name": "Кристальный резак",
        "cost": 28,
        "cd_red": 0.11,
        "yield_add": 0.14,
        "extra_drops": [{"resource": "crystal", "chance": 0.18, "amount": 1}],
    },
    "tool7": {
        "name": "Мифриловый бур",
        "cost": 36,
        "cd_red": 0.13,
        "yield_add": 0.16,
        "extra_drops": [{"resource": "mythril", "chance": 0.22, "amount": 1}],
    },
    "tool8": {
        "name": "Реликтовый экскаватор",
        "cost": 45,
        "cd_red": 0.15,
        "yield_add": 0.18,
        "extra_drops": [{"resource": "relic", "chance": 0.26, "amount": 1}],
    },
}

RPG_BAGS = {
    "bag1": {
        "name": "Мешок из ткани",
        "cost": 3,
        "cost_resource": "wood",
        "cap_add": 80,
    },
    "bag2": {
        "name": "Сумка старателя",
        "cost": 6,
        "cost_resource": "wood",
        "cap_add": 160,
    },
    "bag3": {
        "name": "Рюкзак шахтёра",
        "cost": 12,
        "cost_resource": "stone",
        "cap_add": 320,
    },
    "bag4": {
        "name": "Укреплённый рюкзак",
        "cost": 18,
        "cost_resource": "stone",
        "cap_add": 520,
    },
    "bag5": {
        "name": "Экспедиционный мешок",
        "cost": 25,
        "cost_resource": "iron",
        "cap_add": 800,
    },
    "bag6": {
        "name": "Каркасная сумка",
        "cost": 33,
        "cost_resource": "iron",
        "cap_add": 1100,
    },
    "bag7": {
        "name": "Горный баул",
        "cost": 42,
        "cost_resource": "silver",
        "cap_add": 1500,
    },
    "bag8": {
        "name": "Сумка инженера",
        "cost": 55,
        "cost_resource": "silver",
        "cap_add": 1900,
    },
    "bag9": {
        "name": "Артефактный рюкзак",
        "cost": 70,
        "cost_resource": "gold",
        "cap_add": 2500,
    },
    "bag10": {
        "name": "Легендарный контейнер",
        "cost": 95,
        "cost_resource": "gold",
        "cap_add": 3200,
    },
    "bag11": {
        "name": "Полевой контейнер",
        "cost": 125,
        "cost_resource": "crystal",
        "cap_add": 4200,
    },
    "bag12": {
        "name": "Стабилизированный ранец",
        "cost": 160,
        "cost_resource": "crystal",
        "cap_add": 5400,
    },
    "bag13": {
        "name": "Астероидный бокс",
        "cost": 200,
        "cost_resource": "mythril",
        "cap_add": 7000,
    },
    "bag14": {
        "name": "Квантовый рюкзак",
        "cost": 250,
        "cost_resource": "relic",
        "cap_add": 8800,
    },
    "bag15": {
        "name": "Хранилище первопроходца",
        "cost": 310,
        "cost_resource": "essence",
        "cap_add": 11000,
    },
    "bag16": {
        "name": "Экзоконтейнер",
        "cost": 380,
        "cost_resource": "essence",
        "cap_add": 14000,
    },
    "bag17": {
        "name": "Лабораторный отсек",
        "cost": 460,
        "cost_resource": "essence",
        "cap_add": 17000,
    },
    "bag18": {
        "name": "Стабилизированный карман",
        "cost": 550,
        "cost_resource": "essence",
        "cap_add": 20000,
    },
    "bag19": {
        "name": "Архив реликтов",
        "cost": 650,
        "cost_resource": "essence",
        "cap_add": 24000,
    },
    "bag20": {
        "name": "Континуум-хранилище",
        "cost": 780,
        "cost_resource": "essence",
        "cap_add": 28000,
    },
}

RPG_SELL_MIN_RESOURCE = "mythril"
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
        "bag_req": "bag3",
        "levels": [
            {"rate": 6, "interval": 60, "cost": {"wood": 1200}},
            {"rate": 12, "interval": 55, "cost": {"wood": 1800, "stone": 400}},
            {"rate": 18, "interval": 50, "cost": {"wood": 2400, "stone": 700}},
            {"rate": 24, "interval": 45, "cost": {"wood": 3000, "stone": 1000, "iron": 150}},
            {"rate": 30, "interval": 40, "cost": {"wood": 3800, "stone": 1500, "iron": 300}},
            {"rate": 38, "interval": 36, "cost": {"wood": 4700, "stone": 2100, "iron": 600, "silver": 100}},
            {"rate": 46, "interval": 32, "cost": {"wood": 5600, "stone": 2800, "iron": 900, "silver": 220}},
            {"rate": 55, "interval": 30, "cost": {"wood": 6600, "stone": 3600, "iron": 1300, "silver": 400, "gold": 120}},
            {"rate": 65, "interval": 28, "cost": {"wood": 7800, "stone": 4500, "iron": 1800, "silver": 650, "gold": 220, "crystal": 60}},
            {"rate": 80, "interval": 25, "cost": {"wood": 9200, "stone": 5600, "iron": 2400, "silver": 900, "gold": 350, "crystal": 120}},
        ],
    },
    {
        "id": "auto_stone",
        "name": "Каменный экскаватор",
        "resource": "stone",
        "bag_req": "bag5",
        "levels": [
            {"rate": 4, "interval": 90, "cost": {"wood": 1500, "stone": 900}},
            {"rate": 8, "interval": 80, "cost": {"wood": 2100, "stone": 1400}},
            {"rate": 12, "interval": 70, "cost": {"wood": 2800, "stone": 1900, "iron": 200}},
            {"rate": 16, "interval": 62, "cost": {"wood": 3600, "stone": 2500, "iron": 400}},
            {"rate": 22, "interval": 55, "cost": {"wood": 4500, "stone": 3200, "iron": 700, "silver": 120}},
            {"rate": 28, "interval": 50, "cost": {"wood": 5400, "stone": 3900, "iron": 1100, "silver": 220}},
            {"rate": 35, "interval": 45, "cost": {"wood": 6400, "stone": 4700, "iron": 1500, "silver": 350, "gold": 90}},
            {"rate": 43, "interval": 40, "cost": {"wood": 7500, "stone": 5600, "iron": 2100, "silver": 520, "gold": 160, "crystal": 70}},
            {"rate": 52, "interval": 36, "cost": {"wood": 8700, "stone": 6600, "iron": 2700, "silver": 720, "gold": 230, "crystal": 120}},
            {"rate": 65, "interval": 32, "cost": {"wood": 10000, "stone": 7800, "iron": 3400, "silver": 950, "gold": 320, "crystal": 180}},
        ],
    },
    {
        "id": "auto_iron",
        "name": "Железный бур",
        "resource": "iron",
        "bag_req": "bag7",
        "levels": [
            {"rate": 3, "interval": 120, "cost": {"stone": 1400, "iron": 600}},
            {"rate": 7, "interval": 110, "cost": {"stone": 1900, "iron": 950}},
            {"rate": 11, "interval": 100, "cost": {"stone": 2500, "iron": 1400}},
            {"rate": 16, "interval": 90, "cost": {"stone": 3200, "iron": 1900, "silver": 180}},
            {"rate": 22, "interval": 80, "cost": {"stone": 4000, "iron": 2500, "silver": 320}},
            {"rate": 29, "interval": 72, "cost": {"stone": 4900, "iron": 3200, "silver": 500, "gold": 120}},
            {"rate": 37, "interval": 65, "cost": {"stone": 5900, "iron": 4000, "silver": 720, "gold": 220, "crystal": 80}},
            {"rate": 46, "interval": 58, "cost": {"stone": 7000, "iron": 4900, "silver": 950, "gold": 320, "crystal": 140}},
            {"rate": 56, "interval": 52, "cost": {"stone": 8200, "iron": 5900, "silver": 1200, "gold": 450, "crystal": 200, "mythril": 80}},
            {"rate": 68, "interval": 48, "cost": {"stone": 9600, "iron": 7100, "silver": 1500, "gold": 600, "crystal": 260, "mythril": 130}},
        ],
    },
    {
        "id": "auto_silver",
        "name": "Серебряный конвейер",
        "resource": "silver",
        "bag_req": "bag9",
        "levels": [
            {"rate": 2, "interval": 180, "cost": {"iron": 950, "silver": 400}},
            {"rate": 5, "interval": 160, "cost": {"iron": 1400, "silver": 650}},
            {"rate": 8, "interval": 145, "cost": {"iron": 1900, "silver": 900, "gold": 140}},
            {"rate": 12, "interval": 130, "cost": {"iron": 2500, "silver": 1250, "gold": 260}},
            {"rate": 16, "interval": 115, "cost": {"iron": 3200, "silver": 1650, "gold": 380, "crystal": 90}},
            {"rate": 21, "interval": 100, "cost": {"iron": 4000, "silver": 2100, "gold": 520, "crystal": 150}},
            {"rate": 27, "interval": 90, "cost": {"iron": 4900, "silver": 2600, "gold": 680, "crystal": 210, "mythril": 70}},
            {"rate": 34, "interval": 80, "cost": {"iron": 5900, "silver": 3200, "gold": 860, "crystal": 280, "mythril": 120}},
            {"rate": 42, "interval": 72, "cost": {"iron": 7000, "silver": 3900, "gold": 1060, "crystal": 360, "mythril": 180, "relic": 60}},
            {"rate": 52, "interval": 65, "cost": {"iron": 8200, "silver": 4700, "gold": 1280, "crystal": 450, "mythril": 240, "relic": 90}},
        ],
    },
    {
        "id": "auto_gold",
        "name": "Золотой комбайн",
        "resource": "gold",
        "bag_req": "bag11",
        "levels": [
            {"rate": 1, "interval": 240, "cost": {"silver": 850, "gold": 250}},
            {"rate": 3, "interval": 210, "cost": {"silver": 1200, "gold": 420}},
            {"rate": 5, "interval": 190, "cost": {"silver": 1600, "gold": 600, "crystal": 120}},
            {"rate": 8, "interval": 170, "cost": {"silver": 2100, "gold": 820, "crystal": 190}},
            {"rate": 11, "interval": 150, "cost": {"silver": 2700, "gold": 1080, "crystal": 270, "mythril": 80}},
            {"rate": 15, "interval": 135, "cost": {"silver": 3400, "gold": 1380, "crystal": 360, "mythril": 140}},
            {"rate": 20, "interval": 120, "cost": {"silver": 4200, "gold": 1720, "crystal": 460, "mythril": 200, "relic": 70}},
            {"rate": 26, "interval": 108, "cost": {"silver": 5100, "gold": 2100, "crystal": 580, "mythril": 270, "relic": 110}},
            {"rate": 33, "interval": 96, "cost": {"silver": 6100, "gold": 2520, "crystal": 720, "mythril": 350, "relic": 160, "essence": 40}},
            {"rate": 42, "interval": 85, "cost": {"silver": 7200, "gold": 3000, "crystal": 880, "mythril": 440, "relic": 220, "essence": 70}},
        ],
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


def key_rpg_runs(uid: int) -> str:
    return f"user:{uid}:rpg:runs"


def key_rpg_economy() -> str:
    return "rpg:economy"


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


async def get_rpg_economy(r=None) -> Dict[str, int]:
    if r is None:
        r = await get_redis()
    raw = await r.hgetall(key_rpg_economy())
    convert_rate = safe_int(raw.get("convert_rate"), RPG_CONVERT_RATE_DEFAULT)
    base_cd = safe_int(raw.get("base_cd"), RPG_BASE_CD_DEFAULT)
    convert_rate = max(1, convert_rate or RPG_CONVERT_RATE_DEFAULT)
    base_cd = max(30, base_cd or RPG_BASE_CD_DEFAULT)
    return {"convert_rate": convert_rate, "base_cd": base_cd}


async def save_rpg_economy(data: Dict[str, Any]) -> Dict[str, int]:
    r = await get_redis()
    mapping: Dict[str, int] = {}
    if "convert_rate" in data and data.get("convert_rate") is not None:
        mapping["convert_rate"] = max(1, int(data.get("convert_rate")))
    if "base_cd" in data and data.get("base_cd") is not None:
        mapping["base_cd"] = max(30, int(data.get("base_cd")))
    if mapping:
        await r.hset(key_rpg_economy(), mapping=mapping)
    return await get_rpg_economy(r)


def rpg_calc_buffs(owned: Dict[str, Any]):
    cd_mult = 1.0
    yield_add = 0.0
    cap_add = {r: 0 for r in RPG_RESOURCES}
    extra_drops = []
    convert_bonus = 0.0

    for tid in owned.get("tools", []):
        it = RPG_TOOLS.get(tid)
        if it:
            cd_mult *= (1.0 - float(it.get("cd_red", 0.0)))
            yield_add += float(it.get("yield_add", 0.0))
            extra_drops.extend(it.get("extra_drops", []) or [])

    for aid in owned.get("acc", []):
        it = RPG_ACCESSORIES.get(aid)
        if it:
            cd_mult *= (1.0 - float(it.get("cd_red", 0.0)))
            yield_add += float(it.get("yield_add", 0.0))
            convert_bonus += float(it.get("convert_bonus", 0.0))

    for bid in owned.get("bags", []):
        it = RPG_BAGS.get(bid)
        if it:
            add = int(it.get("cap_add", 0))
            for r in cap_add:
                cap_add[r] += add

    cd_mult = max(0.2, min(cd_mult, 1.0))
    yield_add = max(0.0, min(yield_add, 1.0))
    convert_bonus = max(0.0, min(convert_bonus, 1.0))
    return cd_mult, yield_add, cap_add, extra_drops, convert_bonus


def rpg_auto_state_level(state: Dict[str, Any], max_level: int) -> int:
    base_level = safe_int(state.get("level"), 1 if state else 0)
    return max(0, min(base_level, max_level))


def rpg_auto_level_cfg(cfg: Dict[str, Any], level: int) -> Optional[Dict[str, Any]]:
    levels = cfg.get("levels", []) or []
    if level <= 0 or level > len(levels):
        return None
    return levels[level - 1]


def rpg_auto_missing(costs: Dict[str, int], res: Dict[str, int]):
    missing_res = {}
    for k, need in (costs or {}).items():
        have = res.get(k, 0)
        if have < int(need):
            missing_res[k] = int(need - have)
    return missing_res


def rpg_auto_requirements(
    cfg: Dict[str, Any], res: Dict[str, int], owned: Dict[str, Any], state_level: int
):
    bag_req = cfg.get("bag_req")
    has_bag = (not bag_req) or (bag_req in owned.get("bags", []))
    next_cfg = rpg_auto_level_cfg(cfg, state_level + 1)
    missing_upgrade = rpg_auto_missing(next_cfg.get("cost") if next_cfg else {}, res)
    return missing_upgrade, has_bag, next_cfg


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

        levels = cfg.get("levels", []) or []
        level = rpg_auto_state_level(state, len(levels))
        level_cfg = rpg_auto_level_cfg(cfg, level)
        if not level_cfg:
            continue

        last = safe_int(state.get("last"), now)
        interval = int(level_cfg.get("interval", 60))
        if interval <= 0:
            continue
        ticks = max(0, (now - last) // interval)
        if ticks <= 0:
            continue

        gain = ticks * int(level_cfg.get("rate", 1))
        res_name = cfg.get("resource")
        cap = RPG_MAX + int(cap_add.get(res_name, 0))
        cur_val = res.get(res_name, 0)
        add_val = min(gain, max(0, cap - cur_val))
        if add_val > 0:
            res[res_name] = cur_val + add_val
            pipe.hset(key_rpg_res(uid), res_name, res[res_name])

        state["last"] = last + ticks * interval
        state["level"] = level
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
    pipe.setnx(key_rpg_runs(uid), 0)
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
    bal = await get_balance(uid)
    res = await r.hgetall(key_rpg_res(uid))
    res = {k: safe_int(v) for k, v in res.items()}
    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add, extra_drops, convert_bonus = rpg_calc_buffs(owned)
    res = await rpg_apply_auto(uid, res, cap_add)

    economy = await get_rpg_economy(r)

    total_runs = safe_int(await r.get(key_rpg_runs(uid)))

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
        levels = cfg.get("levels", []) or []
        max_level = len(levels)
        level = rpg_auto_state_level(state, max_level)
        level_cfg = rpg_auto_level_cfg(cfg, level) or {}
        next_cfg = rpg_auto_level_cfg(cfg, level + 1)
        last_tick = safe_int(state.get("last"), 0)
        interval = int(level_cfg.get("interval") or (next_cfg or {}).get("interval", 0))
        rate = int(level_cfg.get("rate") or (next_cfg or {}).get("rate", 0))
        next_tick = last_tick + interval if active else 0
        missing_res, has_bag, _next_cfg = rpg_auto_requirements(cfg, res, owned, level)
        auto_list.append(
            {
                "id": cfg["id"],
                "name": cfg.get("name", ""),
                "resource": cfg.get("resource"),
                "rate": rate,
                "interval": interval,
                "level": level,
                "max_level": max_level,
                "next_level": level + 1 if _next_cfg else None,
                "upgrade_cost": (_next_cfg or {}).get("cost"),
                "bag_req": cfg.get("bag_req"),
                "active": active,
                "last_tick": last_tick,
                "next_tick": next_tick,
                "unlocked": level > 0 and has_bag,
                "missing": missing_res,
                "missing_upgrade": missing_res,
                "has_bag": has_bag,
                "can_start": level > 0 and has_bag,
                "can_upgrade": bool(_next_cfg and not missing_res),
                "preview_rate": level_cfg.get("rate") if level_cfg else (_next_cfg or {}).get("rate"),
                "preview_interval": level_cfg.get("interval")
                if level_cfg
                else (_next_cfg or {}).get("interval"),
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
        "buffs": {
            "cd_mult": cd_mult,
            "yield_add": yield_add,
            "extra_drops": extra_drops,
            "convert_bonus": convert_bonus,
        },
        "caps": cap_add,
        "auto": {"miners": auto_list, "now": now},
        "stats": {"total_runs": total_runs},
        "economy": economy,
    }


def rpg_roll_gather(extra_drops=None):
    import random

    res = {
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

    for bonus in extra_drops or []:
        try:
            chance = float(bonus.get("chance", 0.0))
        except Exception:
            chance = 0.0
        if chance <= 0:
            continue
        if random.random() <= chance:
            res_name = bonus.get("resource")
            amt = int(bonus.get("amount", 1))
            if res_name:
                res[res_name] = res.get(res_name, 0) + max(1, amt)

    return res


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
