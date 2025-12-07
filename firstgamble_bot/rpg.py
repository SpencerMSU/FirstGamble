import random
import time
from typing import Dict

from .redis_utils import (
    add_points,
    get_balance,
    get_redis,
    key_balance,
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
        "cost_resource": "wood",
        "cd_red": 0.03,
        "convert_bonus": 0.02,
        "yield_add": 0.02,
    },
    "acc2": {
        "name": "Жетон старателя",
        "level": 2,
        "cost": 7,
        "cost_resource": "stone",
        "cd_red": 0.05,
        "convert_bonus": 0.04,
        "yield_add": 0.03,
    },
    "acc3": {
        "name": "Кольцо ускорения",
        "level": 3,
        "cost": 11,
        "cost_resource": "iron",
        "cd_red": 0.07,
        "convert_bonus": 0.06,
        "yield_add": 0.05,
    },
    "acc4": {
        "name": "Амулет руды",
        "level": 4,
        "cost": 15,
        "cost_resource": "silver",
        "cd_red": 0.10,
        "convert_bonus": 0.08,
        "yield_add": 0.06,
    },
    "acc5": {
        "name": "Браслет инженера",
        "level": 5,
        "cost": 21,
        "cost_resource": "gold",
        "cd_red": 0.12,
        "convert_bonus": 0.10,
        "yield_add": 0.08,
    },
    "acc6": {
        "name": "Фазовый талисман",
        "level": 6,
        "cost": 28,
        "cost_resource": "crystal",
        "cd_red": 0.15,
        "convert_bonus": 0.12,
        "yield_add": 0.10,
    },
    "acc7": {
        "name": "Печать реликтов",
        "level": 7,
        "cost": 36,
        "cost_resource": "mythril",
        "cd_red": 0.18,
        "convert_bonus": 0.15,
        "yield_add": 0.12,
    },
    "acc8": {
        "name": "Корона алхимика",
        "level": 8,
        "cost": 45,
        "cost_resource": "relic",
        "cd_red": 0.22,
        "convert_bonus": 0.18,
        "yield_add": 0.14,
    },
}

RPG_TOOLS = {
    "tool1": {
        "name": "Кирка новичка",
        "cost": 3,
        "cost_resource": "wood",
        "cd_red": 0.00,
        "yield_add": 0.04,
        "extra_drops": [{"resource": "wood", "chance": 0.05, "amount": 1}],
    },
    "tool2": {
        "name": "Каменный долот",
        "cost": 6,
        "cost_resource": "stone",
        "cd_red": 0.03,
        "yield_add": 0.06,
        "extra_drops": [{"resource": "stone", "chance": 0.08, "amount": 1}],
    },
    "tool3": {
        "name": "Железная кирка",
        "cost": 10,
        "cost_resource": "iron",
        "cd_red": 0.05,
        "yield_add": 0.08,
        "extra_drops": [{"resource": "iron", "chance": 0.10, "amount": 1}],
    },
    "tool4": {
        "name": "Серебряная кирка",
        "cost": 15,
        "cost_resource": "silver",
        "cd_red": 0.07,
        "yield_add": 0.10,
        "extra_drops": [{"resource": "silver", "chance": 0.12, "amount": 1}],
    },
    "tool5": {
        "name": "Золотая дрель",
        "cost": 21,
        "cost_resource": "gold",
        "cd_red": 0.09,
        "yield_add": 0.12,
        "extra_drops": [{"resource": "gold", "chance": 0.15, "amount": 1}],
    },
    "tool6": {
        "name": "Кристальный резак",
        "cost": 28,
        "cost_resource": "crystal",
        "cd_red": 0.11,
        "yield_add": 0.14,
        "extra_drops": [{"resource": "crystal", "chance": 0.18, "amount": 1}],
    },
    "tool7": {
        "name": "Мифриловый бур",
        "cost": 36,
        "cost_resource": "mythril",
        "cd_red": 0.13,
        "yield_add": 0.16,
        "extra_drops": [{"resource": "mythril", "chance": 0.22, "amount": 1}],
    },
    "tool8": {
        "name": "Реликтовый экскаватор",
        "cost": 45,
        "cost_resource": "relic",
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
    "bag21": {
        "name": "Усиленный лабораторный ранец",
        "cost": 320,
        "cost_resource": "relic",
        "cap_add": 10500,
    },
    "bag22": {
        "name": "Космический отсек",
        "cost": 420,
        "cost_resource": "essence",
        "cap_add": 13500,
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

RPG_SELL_MIN_RESOURCE = "essence"
RPG_SELL_VALUES = {
    "essence": 5,
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
    """Gets the Redis key for a user's RPG resources.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's RPG resources.
    """
    return f"user:{uid}:rpg:res"  # hash


def key_rpg_cd(uid: int) -> str:
    """Gets the Redis key for a user's RPG cooldown.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's RPG cooldown.
    """
    return f"user:{uid}:rpg:cd"  # unix next gather time


def key_rpg_owned(uid: int, cat: str) -> str:
    """Gets the Redis key for a user's owned RPG items in a category.

    Args:
        uid: The user's unique identifier.
        cat: The item category.

    Returns:
        The Redis key for the user's owned RPG items.
    """
    return f"user:{uid}:rpg:owned:{cat}"  # set


async def rpg_ensure(uid: int):
    """Ensures that a user has the necessary data structures for the RPG.

    Args:
        uid: The user's unique identifier.
    """
    r = await get_redis()
    pipe = r.pipeline()
    for res in RPG_RESOURCES:
        pipe.hsetnx(key_rpg_res(uid), res, 0)
    pipe.setnx(key_rpg_cd(uid), 0)
    await pipe.execute()


async def rpg_get_owned(uid: int):
    """Gets a user's owned RPG items.

    Args:
        uid: The user's unique identifier.

    Returns:
        A dictionary of the user's owned items, categorized by type.
    """
    r = await get_redis()
    tools = await r.smembers(key_rpg_owned(uid, "tools"))
    acc = await r.smembers(key_rpg_owned(uid, "acc"))
    bags = await r.smembers(key_rpg_owned(uid, "bags"))
    return {"tools": list(tools), "acc": list(acc), "bags": list(bags)}


def rpg_calc_buffs(owned: Dict):
    """Calculates a user's RPG buffs based on their owned items.

    Args:
        owned: A dictionary of the user's owned items.

    Returns:
        A tuple containing the user's calculated buffs.
    """
    cd_mult = 1.0
    yield_add = 0.0
    cap_add = {r: 0 for r in RPG_RESOURCES}
    extra_drops = []
    convert_bonus = 0.0

    for tid in owned.get("tools", []):
        it = RPG_TOOLS.get(tid)
        if it:
            cd_mult *= 1.0 - float(it.get("cd_red", 0.0))
            yield_add += float(it.get("yield_add", 0.0))
            extra_drops.extend(it.get("extra_drops", []) or [])

    for aid in owned.get("acc", []):
        it = RPG_ACCESSORIES.get(aid)
        if it:
            cd_mult *= 1.0 - float(it.get("cd_red", 0.0))
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


async def rpg_state(uid: int):
    """Gets the complete RPG state for a user.

    Args:
        uid: The user's unique identifier.

    Returns:
        A dictionary representing the user's RPG state.
    """
    r = await get_redis()
    await rpg_ensure(uid)
    bal = await get_balance(uid)
    res = await r.hgetall(key_rpg_res(uid))
    res = {k: safe_int(v) for k, v in res.items()}
    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add, extra_drops, convert_bonus = rpg_calc_buffs(owned)

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
    }


def rpg_roll_gather(extra_drops=None):
    """Rolls for resource gathering in the RPG.

    Args:
        extra_drops: A list of potential extra drops.

    Returns:
        A dictionary of the gathered resources and their amounts.
    """
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
