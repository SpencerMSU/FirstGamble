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
    key_ban,
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

AUTO_INV_BASE = 500
AUTO_INV_MAX = 12000
AUTO_INV_GROW_INTERVAL = 600
AUTO_INV_GROW_AMOUNT = 80

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
    """Gets the Redis key for a user's RPG resources.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's RPG resources.
    """
    return f"user:{uid}:rpg:res"


def key_rpg_cd(uid: int) -> str:
    """Gets the Redis key for a user's RPG cooldown.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's RPG cooldown.
    """
    return f"user:{uid}:rpg:cd"


def key_rpg_owned(uid: int, cat: str) -> str:
    """Gets the Redis key for a user's owned RPG items in a category.

    Args:
        uid: The user's unique identifier.
        cat: The item category.

    Returns:
        The Redis key for the user's owned RPG items.
    """
    return f"user:{uid}:rpg:owned:{cat}"


def key_rpg_auto(uid: int) -> str:
    """Gets the Redis key for a user's RPG auto-miner state.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's RPG auto-miner state.
    """
    return f"user:{uid}:rpg:auto"


def key_rpg_runs(uid: int) -> str:
    """Gets the Redis key for a user's RPG run count.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's RPG run count.
    """
    return f"user:{uid}:rpg:runs"


def key_rpg_economy() -> str:
    """Gets the Redis key for the RPG economy settings."""
    return "rpg:economy"


def key_ticket_counter() -> str:
    """Gets the Redis key for the raffle ticket counter."""
    return "raffle:ticket:counter"


def key_user_tickets(uid: int) -> str:
    """Gets the Redis key for a user's raffle tickets.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's raffle tickets.
    """
    return f"user:{uid}:raffle:tickets"


def key_ticket_owners() -> str:
    """Gets the Redis key for the raffle ticket owners."""
    return "raffle:ticket:owners"  # hash: ticket -> user_id


def key_prize_counter() -> str:
    """Gets the Redis key for the raffle prize counter."""
    return "raffle:prize:counter"


def key_prizes_set() -> str:
    """Gets the Redis key for the set of raffle prizes."""
    return "raffle:prizes"


def key_prize_item(pid: int) -> str:
    """Gets the Redis key for a specific raffle prize.

    Args:
        pid: The prize ID.

    Returns:
        The Redis key for the prize.
    """
    return f"raffle:prize:{pid}"


def key_prizes_visible() -> str:
    """Gets the Redis key for the raffle prizes visibility flag."""
    return "raffle:prizes_visible"


def key_raffle_winners() -> str:
    """Gets the Redis key for the list of raffle winners."""
    return "raffle:winners"


def key_last_raffle_winners() -> str:
    """Gets the Redis key for the list of the last raffle's winners."""
    return "raffle:last_winners"


def key_raffle_status() -> str:
    """Gets the Redis key for the raffle status."""
    return "raffle:status"


def key_user_raffle_wins(uid: int) -> str:
    """Gets the Redis key for a user's raffle wins.

    Args:
        uid: The user's unique identifier.

    Returns:
        The Redis key for the user's raffle wins.
    """
    return f"user:{uid}:raffle:wins"


async def get_rpg_economy(r=None) -> Dict[str, int]:
    """Gets the RPG economy settings.

    Args:
        r: An optional Redis connection object.

    Returns:
        A dictionary containing the RPG economy settings.
    """
    if r is None:
        r = await get_redis()
    raw = await r.hgetall(key_rpg_economy())
    convert_rate = safe_int(raw.get("convert_rate"), RPG_CONVERT_RATE_DEFAULT)
    base_cd = safe_int(raw.get("base_cd"), RPG_BASE_CD_DEFAULT)
    convert_rate = max(1, convert_rate or RPG_CONVERT_RATE_DEFAULT)
    base_cd = max(30, base_cd or RPG_BASE_CD_DEFAULT)
    return {"convert_rate": convert_rate, "base_cd": base_cd}


async def save_rpg_economy(data: Dict[str, Any]) -> Dict[str, int]:
    """Saves the RPG economy settings.

    Args:
        data: A dictionary containing the new economy settings.

    Returns:
        The updated RPG economy settings.
    """
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
    """Gets the current level of an auto-miner.

    Args:
        state: The auto-miner's state.
        max_level: The maximum possible level for the auto-miner.

    Returns:
        The auto-miner's current level.
    """
    base_level = safe_int(state.get("level"), 1 if state else 0)
    return max(0, min(base_level, max_level))


def rpg_auto_level_cfg(cfg: Dict[str, Any], level: int) -> Optional[Dict[str, Any]]:
    """Gets the configuration for a specific auto-miner level.

    Args:
        cfg: The auto-miner's base configuration.
        level: The level to get the configuration for.

    Returns:
        The configuration for the specified level, or None if the level is
        invalid.
    """
    levels = cfg.get("levels", []) or []
    if level <= 0 or level > len(levels):
        return None
    return levels[level - 1]


def rpg_auto_missing(costs: Dict[str, int], res: Dict[str, int]):
    """Calculates the resources missing for an auto-miner upgrade.

    Args:
        costs: The costs of the upgrade.
        res: The user's current resources.

    Returns:
        A dictionary of the missing resources and their amounts.
    """
    missing_res = {}
    for k, need in (costs or {}).items():
        have = res.get(k, 0)
        if have < int(need):
            missing_res[k] = int(need - have)
    return missing_res


def rpg_auto_refresh_state(state: Dict[str, Any], now: int):
    """Refreshes the state of an auto-miner.

    This function updates the miner's inventory capacity and amount based on
    the time elapsed since the last refresh.

    Args:
        state: The auto-miner's current state.
        now: The current timestamp.

    Returns:
        A tuple containing the updated state, inventory capacity, and
        inventory amount.
    """
    inv_cap = max(AUTO_INV_BASE, safe_int(state.get("inv_cap"), AUTO_INV_BASE))
    inv_amt = max(0, safe_int(state.get("inv"), 0))
    cap_ts = safe_int(state.get("cap_ts"), now)
    if cap_ts <= 0:
        cap_ts = now

    growth_steps = max(0, (now - cap_ts) // AUTO_INV_GROW_INTERVAL)
    if growth_steps > 0:
        inv_cap = min(AUTO_INV_MAX, inv_cap + growth_steps * AUTO_INV_GROW_AMOUNT)
        cap_ts += growth_steps * AUTO_INV_GROW_INTERVAL

    state["inv_cap"] = inv_cap
    state["inv"] = inv_amt
    state["cap_ts"] = cap_ts
    return state, inv_cap, inv_amt


def rpg_auto_requirements(
    cfg: Dict[str, Any], res: Dict[str, int], owned: Dict[str, Any], state_level: int
):
    """Checks the requirements for upgrading an auto-miner.

    Args:
        cfg: The auto-miner's configuration.
        res: The user's current resources.
        owned: The user's owned items.
        state_level: The auto-miner's current level.

    Returns:
        A tuple containing the missing resources for the upgrade, whether the
        user has the required bag, and the configuration for the next level.
    """
    bag_req = cfg.get("bag_req")
    has_bag = (not bag_req) or (bag_req in owned.get("bags", []))
    next_cfg = rpg_auto_level_cfg(cfg, state_level + 1)
    missing_upgrade = rpg_auto_missing(next_cfg.get("cost") if next_cfg else {}, res)
    return missing_upgrade, has_bag, next_cfg


async def rpg_apply_auto(uid: int, res: Dict[str, int], cap_add: Dict[str, int]):
    """Applies the effects of auto-miners.

    This function calculates the resources generated by a user's auto-miners
    since the last update and adds them to the user's inventory.

    Args:
        uid: The user's unique identifier.
        res: The user's current resources.
        cap_add: The user's additional resource capacity from items.

    Returns:
        The user's updated resources.
    """
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

        state, inv_cap, inv_amt = rpg_auto_refresh_state(state, now)

        if not state.get("active"):
            state["level"] = rpg_auto_state_level(state, len(cfg.get("levels", []) or []))
            pipe.hset(key_rpg_auto(uid), cfg["id"], json.dumps(state))
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

        if ticks > 0:
            gain = ticks * int(level_cfg.get("rate", 1))
            capacity_left = max(0, inv_cap - inv_amt)
            add_val = min(gain, capacity_left)
            inv_amt += add_val
            last += ticks * interval

        if inv_amt >= inv_cap and state.get("active"):
            state["active"] = False

        state["last"] = last
        state["level"] = level
        state["inv"] = inv_amt
        state["inv_cap"] = inv_cap
        pipe.hset(key_rpg_auto(uid), cfg["id"], json.dumps(state))

    if pipe.command_stack:
        await pipe.execute()
    return res


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
    pipe.setnx(key_rpg_runs(uid), 0)
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
        state, inv_cap, inv_amt = rpg_auto_refresh_state(state, now)
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
        storage_full = inv_amt >= inv_cap > 0
        can_start = level > 0 and has_bag and not storage_full
        can_collect = inv_amt > 0
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
                "can_start": can_start,
                "can_upgrade": bool(_next_cfg and not missing_res),
                "preview_rate": level_cfg.get("rate") if level_cfg else (_next_cfg or {}).get("rate"),
                "preview_interval": level_cfg.get("interval")
                if level_cfg
                else (_next_cfg or {}).get("interval"),
                "inventory": {"amount": inv_amt, "cap": inv_cap},
                "storage_full": storage_full,
                "can_collect": can_collect,
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
    """Rolls for resource gathering in the RPG.

    Args:
        extra_drops: A list of potential extra drops.

    Returns:
        A dictionary of the gathered resources and their amounts.
    """
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
    """Builds the secret key for Telegram data validation.

    Args:
        bot_token: The bot's Telegram token.

    Returns:
        The secret key.
    """
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


TG_SECRET_KEY = _build_tg_secret(BOT_TOKEN)


def parse_init_data(init_data: str) -> Dict[str, Any]:
    """Parses and validates Telegram's initData string.

    Args:
        init_data: The initData string from Telegram.

    Returns:
        A dictionary containing the parsed and validated data.

    Raises:
        ValueError: If the initData is invalid or the hash does not match.
    """
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
    """Normalizes a Telegram username.

    Args:
        username: The username to normalize.

    Returns:
        The normalized username.
    """
    if not username:
        return ""
    username = str(username).strip()
    if username.startswith("@"):  # убираем @ для хранения
        username = username[1:]
    return username


def _ensure_profile_identity_fields(profile: Dict[str, Any], username: Optional[str], tg_id: Optional[int]) -> Dict[str, str]:
    """Ensures that a user's profile has the necessary identity fields.

    Args:
        profile: The user's profile.
        username: The user's Telegram username.
        tg_id: The user's Telegram ID.

    Returns:
        A dictionary of the fields that were added to the profile.
    """
    mapping: Dict[str, str] = {}
    uname = _normalize_username(username)
    if uname and not profile.get("username"):
        mapping["username"] = uname
    if tg_id and not profile.get("tg_id"):
        mapping["tg_id"] = str(tg_id)
    return mapping


def is_conserve_token(token: Optional[str]) -> bool:
    """Checks if a token is a valid ConServe token.

    Args:
        token: The token to check.

    Returns:
        True if the token is valid, False otherwise.
    """
    return bool(CONSERVE_AUTH_TOKEN and token and token == CONSERVE_AUTH_TOKEN)


def build_auth_context_from_headers(
    method: str,
    request_body: Optional[Dict[str, Any]],
    query_params: Dict[str, Any],
    telegram_init_data: Optional[str],
    conserve_header: Optional[str],
) -> AuthContext:
    """Builds an authentication context from request headers.

    Args:
        method: The HTTP method of the request.
        request_body: The request body.
        query_params: The request query parameters.
        telegram_init_data: The Telegram initData string.
        conserve_header: The ConServe authentication header.

    Returns:
        The authentication context.

    Raises:
        ValueError: If the request is unauthorized.
    """
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


async def check_ban(user_id: int):
    """Checks if a user is banned.

    Args:
        user_id: The user's unique identifier.

    Raises:
        ValueError: If the user is banned (with details).
    """
    r = await get_redis()
    ban_data_raw = await r.get(key_ban(user_id))
    if not ban_data_raw:
        return

    try:
        ban_info = json.loads(ban_data_raw)
    except Exception:
        return

    until = ban_info.get("until")
    if until == "forever":
        # Always banned
        pass
    else:
        # Check expiration
        exp = safe_int(until)
        if exp < time.time():
            # Expired
            await r.delete(key_ban(user_id))
            return

    # User is banned
    reason = ban_info.get("reason", "No reason")
    raise ValueError(f"banned: {reason}|{until}")


async def ban_user(user_id: int, duration_days: int, reason: str = None) -> Dict[str, Any]:
    """Bans a user.

    Args:
        user_id: The user's unique identifier.
        duration_days: Duration in days. -1 for forever.
        reason: Optional reason.

    Returns:
        The ban info dictionary.
    """
    r = await get_redis()

    if duration_days == 0:
        await r.delete(key_ban(user_id))
        return {"banned": False}

    until = "forever"
    if duration_days > 0:
        until = int(time.time() + duration_days * 86400)

    ban_info = {
        "user_id": user_id,
        "until": until,
        "reason": reason or "Admin ban",
        "banned_at": int(time.time()),
    }

    await r.set(key_ban(user_id), json.dumps(ban_info))
    return {"banned": True, "info": ban_info}


async def unban_user(user_id: int):
    """Unbans a user.

    Args:
        user_id: The user's unique identifier.
    """
    r = await get_redis()
    await r.delete(key_ban(user_id))
