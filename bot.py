import asyncio
import logging
import os
import time
import random
from pathlib import Path
from typing import Dict, Optional

from aiohttp import web
import redis.asyncio as redis

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
TOKENS_FILE = BASE_DIR / "tokens.txt"

if not TOKENS_FILE.exists():
    raise SystemExit("tokens.txt not found")


def load_config() -> Dict[str, str]:
    config: Dict[str, str] = {}
    with TOKENS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


config = load_config()

BOT_TOKEN = config.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is missing in tokens.txt")

# Access token for external SAMP/game integrations
# Put ConServeAuthToken=<your_secret_here> into tokens.txt
CONSERVE_AUTH_TOKEN = config.get("ConServeAuthToken") or config.get("CONSERVE_AUTH_TOKEN")
if not CONSERVE_AUTH_TOKEN:
    logging.warning(
        "ConServeAuthToken is not set in tokens.txt; external SAMP access will be disabled."
    )

REDIS_HOST = config.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(config.get("REDIS_PORT", "6379"))
REDIS_DB = int(config.get("REDIS_DB", "0"))

WEBAPP_URL = config.get("WEBAPP_URL", "").rstrip("/")
if not WEBAPP_URL:
    raise SystemExit("WEBAPP_URL is missing in tokens.txt")

logging.info(f"WEBAPP_URL = {WEBAPP_URL}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

rds: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global rds
    if rds is None:
        rds = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
    return rds


# ====== Redis keys ======
def key_confirmed(user_id: int) -> str:
    return f"user:{user_id}:confirmed"


def key_balance(user_id: int) -> str:
    return f"user:{user_id}:balance"


def key_profile(user_id: int) -> str:
    return f"user:{user_id}:profile"  # hash: name, username


def key_stats(user_id: int) -> str:
    return f"user:{user_id}:stats"  # hash: wins, losses, draws, games_total


def key_gamestats(user_id: int, game: str) -> str:
    return f"user:{user_id}:game:{game}"  # hash: wins, losses, draws, games_total


USERS_ZSET = "leaderboard:points"  # zset: user_id -> points
USERS_SET = "users:all"  # set of user_ids

ALLOWED_GAMES = {"dice", "bj", "slot"}


# ====== helpers ======
def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def json_error(message: str, status: int = 400):
    return web.json_response({"ok": False, "error": message}, status=status)


def is_conserve_request(request: web.Request) -> bool:
    """
    Returns True if request is authorized by external SAMP/game token.
    Client must send header: X-ConServe-Auth: <ConServeAuthToken from tokens.txt>
    """
    if not CONSERVE_AUTH_TOKEN:
        return False
    token = request.headers.get("X-ConServe-Auth") or request.headers.get("X-Conserve-Auth")
    return token == CONSERVE_AUTH_TOKEN


async def ensure_user(user_id: int):
    r = await get_redis()
    await r.sadd(USERS_SET, user_id)

    bal = await r.get(key_balance(user_id))
    if bal is None:
        await r.set(key_balance(user_id), "0")
        await r.zadd(USERS_ZSET, {user_id: 0}, nx=True)

    if not await r.exists(key_profile(user_id)):
        await r.hset(key_profile(user_id), mapping={"name": "", "username": ""})

    if not await r.exists(key_stats(user_id)):
        await r.hset(
            key_stats(user_id),
            mapping={"wins": 0, "losses": 0, "draws": 0, "games_total": 0},
        )

    for g in ALLOWED_GAMES:
        ks = key_gamestats(user_id, g)
        if not await r.exists(ks):
            await r.hset(
                ks,
                mapping={
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "games_total": 0,
                },
            )


async def get_balance(user_id: int) -> int:
    r = await get_redis()
    val = await r.get(key_balance(user_id))
    return safe_int(val)


async def add_points(user_id: int, delta: int) -> int:
    r = await get_redis()
    pipe = r.pipeline()
    pipe.incrby(key_balance(user_id), delta)
    pipe.get(key_balance(user_id))
    res = await pipe.execute()
    new_balance = safe_int(res[1])
    await r.zadd(USERS_ZSET, {user_id: new_balance})
    return new_balance


# ====== Telegram handlers ======
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    user_id = user.id

    r = await get_redis()
    await ensure_user(user_id)

    confirmed = await r.get(key_confirmed(user_id))
    if confirmed == "1":
        webapp_button = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть приложение",
                        web_app=WebAppInfo(url=f"{WEBAPP_URL}/?uid={user_id}"),
                    )
                ]
            ]
        )
        await message.answer(
            "✅ Ты уже подтвердил запуск. Можно открыть мини-приложение:",
            reply_markup=webapp_button,
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data="decline")],
        ]
    )

    text = (
        "Добро пожаловать в FirstGamble / FirstClub!\n\n"
        "Перед использованием вы должны ознакомиться с условиями сервиса:\n"
        "https://telegra.ph/Terms-of-Service--FirstGamble-11-26\n\n"
        "Подтвердите, что вы согласны с правилами."
    )
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "confirm")
async def on_confirm(cb: CallbackQuery):
    user_id = cb.from_user.id
    r = await get_redis()

    await ensure_user(user_id)
    await r.set(key_confirmed(user_id), "1")

    webapp_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть приложение",
                    web_app=WebAppInfo(url=f"{WEBAPP_URL}/?uid={user_id}"),
                )
            ]
        ]
    )

    await cb.message.edit_text(
        "✅ Подтверждено! Теперь можно открыть мини-приложение:",
        reply_markup=webapp_button,
    )
    await cb.answer()


@dp.callback_query(F.data == "decline")
async def on_decline(cb: CallbackQuery):
    await cb.message.edit_text("❌ Вы отклонили запуск мини-приложения.")
    await cb.answer()


# ================= RPG SYSTEM (including 10 bags) =================
RPG_RESOURCES = ["wood", "stone", "iron", "silver", "gold", "crystal"]
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

# 10 сумок (3 старые + 7 новых)
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
}
RPG_CHAIN = [
    ("wood", "stone"),
    ("stone", "iron"),
    ("iron", "silver"),
    ("silver", "gold"),
    ("gold", "crystal"),
]


def key_rpg_res(uid: int) -> str:
    return f"user:{uid}:rpg:res"  # hash


def key_rpg_cd(uid: int) -> str:
    return f"user:{uid}:rpg:cd"  # unix next gather time


def key_rpg_owned(uid: int, cat: str) -> str:
    return f"user:{uid}:rpg:owned:{cat}"  # set


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


def rpg_calc_buffs(owned: dict):
    cd_mult = 1.0
    yield_add = 0.0
    cap_add = {r: 0 for r in RPG_RESOURCES}

    for tid in owned.get("tools", []):
        it = RPG_TOOLS.get(tid)
        if it:
            cd_mult *= 1.0 - float(it.get("cd_red", 0.0))
            yield_add += float(it.get("yield_add", 0.0))

    for aid in owned.get("acc", []):
        it = RPG_ACCESSORIES.get(aid)
        if it:
            cd_mult *= 1.0 - float(it.get("cd_red", 0.0))
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
    return {
        "wood": random.randint(2, 5),
        "stone": random.randint(1, 4),
        "iron": random.randint(0, 3),
        "silver": random.randint(0, 2),
        "gold": random.choice([0, 1]),
        "crystal": 1 if random.random() < 0.35 else 0,
    }


# ================= RAFFLE TICKETS =================
def key_ticket_counter() -> str:
    return "raffle:ticket:counter"  # global counter


def key_user_tickets(uid: int) -> str:
    return f"user:{uid}:raffle:tickets"  # list of ticket numbers


# ====== HTTP API ======
routes = web.RouteTableDef()


@routes.get("/api/ping")
async def api_ping(request: web.Request):
    return web.json_response({"ok": True, "message": "pong"})


@routes.get("/api/balance")
async def api_balance(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    uid = safe_int(user_id)
    if uid <= 0:
        return json_error("bad user_id")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    bal = await get_balance(uid)
    return web.json_response({"ok": True, "balance": bal})


@routes.post("/api/add_point")
async def api_add_point(request: web.Request):
    """
    POST JSON: { "user_id": ..., "game": "dice"|"bj"|"slot", "delta"?: int }
    Увеличивает баланс (по умолчанию на 1) и обновляет лидерборд.
    """
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    user_id = safe_int(data.get("user_id"))
    game = (data.get("game") or "").strip().lower()
    delta = max(1, safe_int(data.get("delta"), 1))

    if user_id <= 0:
        return json_error("user_id required")
    if game not in ALLOWED_GAMES:
        return json_error("bad game")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(user_id))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(user_id)
    new_balance = await add_points(user_id, delta)

    return web.json_response({"ok": True, "balance": new_balance})


@routes.post("/api/report_game")
async def api_report_game(request: web.Request):
    """
    POST JSON:
    { "user_id": ..., "game": "...", "result": "win"|"loss"|"draw" }
    """
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    user_id = safe_int(data.get("user_id"))
    game = (data.get("game") or "").strip().lower()
    result = (data.get("result") or "").strip().lower()

    if user_id <= 0:
        return json_error("user_id required")
    if game not in ALLOWED_GAMES:
        return json_error("bad game")
    if result not in {"win", "loss", "draw"}:
        return json_error("bad result")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(user_id))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(user_id)

    field_map = {"win": "wins", "loss": "losses", "draw": "draws"}
    field = field_map[result]

    await r.hincrby(key_stats(user_id), field, 1)
    await r.hincrby(key_stats(user_id), "games_total", 1)

    await r.hincrby(key_gamestats(user_id, game), field, 1)
    await r.hincrby(key_gamestats(user_id, game), "games_total", 1)

    return web.json_response({"ok": True})


@routes.get("/api/stats")
async def api_stats(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    uid = safe_int(user_id)
    if uid <= 0:
        return json_error("bad user_id")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(uid)

    stats = await r.hgetall(key_stats(uid))

    games_stats: Dict[str, Dict[str, int]] = {}
    for g in ALLOWED_GAMES:
        gs = await r.hgetall(key_gamestats(uid, g))
        games_stats[g] = {k: safe_int(v) for k, v in gs.items()}

    return web.json_response(
        {
            "ok": True,
            "stats": {k: safe_int(v) for k, v in stats.items()},
            "games": games_stats,
        }
    )


@routes.get("/api/leaderboard")
async def api_leaderboard(request: web.Request):
    game = (request.query.get("game") or "all").strip().lower()
    sort_by = (request.query.get("sort") or "points").strip().lower()
    limit = safe_int(request.query.get("limit"), 10)
    if limit <= 0 or limit > 100:
        limit = 10

    r = await get_redis()
    if game not in {"all", "dice", "bj", "slot"}:
        game = "all"
    if sort_by not in {"points", "wins", "winrate", "games"}:
        sort_by = "points"

    user_ids = await r.smembers(USERS_SET)
    rows = []
    for user_id_str in user_ids:
        uid = safe_int(user_id_str)
        if uid <= 0:
            continue

        profile = await r.hgetall(key_profile(uid))
        points = safe_int(await r.get(key_balance(uid)))
        stats_key = key_stats(uid) if game == "all" else key_gamestats(uid, game)
        stats_raw = await r.hgetall(stats_key)
        wins = safe_int(stats_raw.get("wins"))
        losses = safe_int(stats_raw.get("losses"))
        draws = safe_int(stats_raw.get("draws"))
        games_total = safe_int(stats_raw.get("games_total"))
        winrate = float(wins) / games_total if games_total > 0 else 0.0

        rows.append(
            {
                "user_id": uid,
                "points": points,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "games_total": games_total,
                "winrate": winrate,
                "name": profile.get("name") or "",
                "username": profile.get("username") or "",
            }
        )

    def sort_key(row):
        if sort_by == "wins":
            return (row["wins"], row["points"])
        if sort_by == "winrate":
            return (row["winrate"], row["games_total"], row["points"])
        if sort_by == "games":
            return (row["games_total"], row["points"])
        return (row["points"], row["wins"])

    rows.sort(key=sort_key, reverse=True)
    rows = rows[:limit]

    return web.json_response({"ok": True, "rows": rows})


@routes.post("/api/update_profile")
async def api_update_profile(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    user_id = safe_int(data.get("user_id"))
    name = (data.get("name") or "").strip()
    username = (data.get("username") or "").strip()

    if user_id <= 0:
        return json_error("user_id required")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(user_id))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(user_id)

    mapping = {}
    if name:
        mapping["name"] = name
    if username:
        mapping["username"] = username

    if mapping:
        await r.hset(key_profile(user_id), mapping=mapping)

    return web.json_response({"ok": True})


# ---------- RPG endpoints ----------
@routes.get("/api/rpg/state")
async def api_rpg_state(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    uid = safe_int(user_id)
    if uid <= 0:
        return json_error("bad user_id")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    st = await rpg_state(uid)
    return web.json_response({"ok": True, "state": st})


@routes.post("/api/rpg/gather")
async def api_rpg_gather(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    if uid <= 0:
        return json_error("user_id required")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await rpg_ensure(uid)
    now = int(time.time())
    next_ts = safe_int(await r.get(key_rpg_cd(uid)))
    if now < next_ts:
        return web.json_response(
            {
                "ok": False,
                "error": "cooldown",
                "cooldown_remaining": next_ts - now,
            }
        )

    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add = rpg_calc_buffs(owned)

    gained = rpg_roll_gather()
    for k in gained:
        gained[k] = int(round(gained[k] * (1.0 + yield_add)))

    cur = await r.hgetall(key_rpg_res(uid))
    cur = {k: safe_int(v) for k, v in cur.items()}

    pipe = r.pipeline()
    for res_name in RPG_RESOURCES:
        max_cap = RPG_MAX + int(cap_add.get(res_name, 0))
        new_val = min(max_cap, cur.get(res_name, 0) + gained.get(res_name, 0))
        pipe.hset(key_rpg_res(uid), res_name, new_val)

    base_cd = 300
    pipe.set(key_rpg_cd(uid), now + int(base_cd * cd_mult))
    await pipe.execute()

    st = await rpg_state(uid)
    return web.json_response({"ok": True, "gained": gained, "state": st})


@routes.post("/api/rpg/buy")
async def api_rpg_buy(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    cat = (data.get("category") or "").lower()
    item_id = (data.get("item_id") or "").lower()

    if uid <= 0 or not cat or not item_id:
        return json_error("bad data")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(uid)

    if cat == "tools":
        store = RPG_TOOLS
    elif cat == "acc":
        store = RPG_ACCESSORIES
    elif cat == "bags":
        store = RPG_BAGS
    else:
        return json_error("bad category")

    item = store.get(item_id)
    if not item:
        return json_error("bad item")

    owned_key = key_rpg_owned(uid, cat)
    if await r.sismember(owned_key, item_id):
        st = await rpg_state(uid)
        return web.json_response({"ok": True, "state": st})

    cost = int(item.get("cost", 0))
    bal = safe_int(await r.get(key_balance(uid)))
    if bal < cost:
        return json_error("not enough points")

    pipe = r.pipeline()
    pipe.incrby(key_balance(uid), -cost)
    pipe.zadd(USERS_ZSET, {uid: bal - cost})
    pipe.sadd(owned_key, item_id)
    await pipe.execute()

    st = await rpg_state(uid)
    return web.json_response({"ok": True, "state": st})


@routes.post("/api/rpg/convert")
async def api_rpg_convert(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    from_r = (data.get("from") or "").lower()
    to_r = (data.get("to") or "").lower()
    amount = safe_int(data.get("amount"), 1)

    if uid <= 0 or not from_r or not to_r or amount <= 0:
        return json_error("bad data")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await rpg_ensure(uid)
    res = await r.hgetall(key_rpg_res(uid))
    res = {k: safe_int(v) for k, v in res.items()}

    if to_r == "points":
        if from_r not in RPG_RESOURCES:
            return json_error("bad from")
        need = amount
        if res.get(from_r, 0) < need:
            return json_error("not enough resources")
        value = RPG_SELL_VALUES.get(from_r, 1) * amount

        pipe = r.pipeline()
        pipe.hincrby(key_rpg_res(uid), from_r, -need)
        pipe.incrby(key_balance(uid), value)
        await pipe.execute()

        new_bal = safe_int(await r.get(key_balance(uid)))
        await r.zadd(USERS_ZSET, {uid: new_bal})

        st = await rpg_state(uid)
        return web.json_response({"ok": True, "state": st})

    pair_ok = any(from_r == a and to_r == b for a, b in RPG_CHAIN)
    if not pair_ok:
        return json_error("bad convert pair")

    rate = 5
    need = amount * rate
    if res.get(from_r, 0) < need:
        return json_error("not enough resources")

    pipe = r.pipeline()
    pipe.hincrby(key_rpg_res(uid), from_r, -need)
    pipe.hincrby(key_rpg_res(uid), to_r, amount)
    await pipe.execute()

    st = await rpg_state(uid)
    return web.json_response({"ok": True, "state": st})


# ---------- Raffle tickets endpoints ----------
@routes.post("/api/raffle/buy_ticket")
async def api_buy_ticket(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    if uid <= 0:
        return json_error("user_id required")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(uid)

    PRICE = 500
    bal = safe_int(await r.get(key_balance(uid)))
    if bal < PRICE:
        return json_error("not enough points")

    num = await r.incr(key_ticket_counter()) - 1
    ticket = str(num).zfill(8)

    pipe = r.pipeline()
    pipe.incrby(key_balance(uid), -PRICE)
    pipe.zadd(USERS_ZSET, {uid: bal - PRICE})
    pipe.rpush(key_user_tickets(uid), ticket)
    await pipe.execute()

    tickets = await r.lrange(key_user_tickets(uid), 0, -1)

    return web.json_response(
        {
            "ok": True,
            "ticket": ticket,
            "balance": bal - PRICE,
            "tickets": tickets,
        }
    )


@routes.get("/api/cabinet")
async def api_cabinet(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    uid = safe_int(user_id)
    if uid <= 0:
        return json_error("bad user_id")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(uid)

    bal = safe_int(await r.get(key_balance(uid)))
    tickets = await r.lrange(key_user_tickets(uid), 0, -1)

    return web.json_response(
        {"ok": True, "user_id": str(uid), "balance": bal, "tickets": tickets}
    )


# ====== HTML pages ======
@routes.get("/")
async def index_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "index.html")


@routes.get("/ludka")
async def ludka_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "ludka.html")


@routes.get("/dice")
async def dice_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "dice.html")


@routes.get("/bj")
async def bj_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "bj.html")


@routes.get("/slot")
async def slot_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "slot.html")


@routes.get("/rating")
async def rating_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "rating.html")


@routes.get("/prices")
async def prices_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "prices.html")


@routes.get("/shop")
async def shop_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "shop.html")


@routes.get("/rpg")
async def rpg_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "rpg.html")


@routes.get("/raffles")
async def raffles_page(request: web.Request):
    return web.FileResponse(BASE_DIR / "raffles.html")

# (кабинет страницу добавим в пункте 3, пока не трогаю)


# ====== Startup / run ======
async def on_startup(app: web.Application):
    global rds
    rds = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )
    logging.info("Redis connected")


async def on_cleanup(app: web.Application):
    if rds:
        await rds.close()


async def main():
    app = web.Application()
    app.add_routes(routes)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"HTTP server started on 0.0.0.0:{port}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
