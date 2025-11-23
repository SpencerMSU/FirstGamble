import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
import redis.asyncio as redis
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# ========= tokens.txt loader =========
def load_tokens(path: str = "tokens.txt") -> Dict[str, str]:
    p = Path(path)
    data: Dict[str, str] = {}
    if not p.exists():
        raise FileNotFoundError(f"{path} not found")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data

TOKENS = load_tokens("tokens.txt")
API_TOKEN = TOKENS.get("API_TOKEN")
REDIS_HOST = TOKENS.get("REDIS_HOST", "localhost")
REDIS_PORT = int(TOKENS.get("REDIS_PORT", "6379"))
REDIS_DB = int(TOKENS.get("REDIS_DB", "0"))
WEBAPP_URL = TOKENS.get("WEBAPP_URL", "https://firstgamble.ru/").rstrip("/") + "/"

if not API_TOKEN or API_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
    raise RuntimeError("API_TOKEN is missing in tokens.txt")

# ========= Redis keys =========
def key_confirmed(user_id: int) -> str:
    return f"user:{user_id}:confirmed"

def key_balance(user_id: int) -> str:
    return f"user:{user_id}:balance"

def key_profile(user_id: int) -> str:
    return f"user:{user_id}:profile"   # hash: name, username

def key_stats(user_id: int) -> str:
    return f"user:{user_id}:stats"     # hash: wins, losses, draws, games_total

def key_gamestats(user_id: int, game: str) -> str:
    return f"user:{user_id}:game:{game}"  # hash: wins, losses, draws, games_total

USERS_ZSET = "leaderboard:points"      # zset: user_id -> points
USERS_SET = "users:all"               # set of user_ids

ALLOWED_GAMES = {"dice", "bj", "slot"}

import time

# ========= RPG system =========
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

RPG_BAGS = {
    "bag1": {"name": "Мешок из ткани", "cost": 3, "cap_add": 50},
    "bag2": {"name": "Сумка старателя", "cost": 6, "cap_add": 100},
    "bag3": {"name": "Рюкзак шахтёра", "cost": 12, "cap_add": 200},
}

RPG_SELL_VALUES = {"wood": 1, "stone": 2, "iron": 5, "silver": 8, "gold": 12, "crystal": 20}
RPG_CHAIN = [("wood", "stone"), ("stone", "iron"), ("iron", "silver"), ("silver", "gold"), ("gold", "crystal")]

def key_rpg_res(user_id: int) -> str:
    return f"user:{user_id}:rpg:res"     # hash

def key_rpg_cd(user_id: int) -> str:
    return f"user:{user_id}:rpg:cd"      # unix next gather time

def key_rpg_owned(user_id: int, cat: str) -> str:
    return f"user:{user_id}:rpg:owned:{cat}"  # set

async def rpg_ensure(uid: int):
    pipe = rds.pipeline()
    for r in RPG_RESOURCES:
        pipe.hsetnx(key_rpg_res(uid), r, 0)
    pipe.setnx(key_rpg_cd(uid), 0)
    await pipe.execute()

async def rpg_get_owned(uid: int):
    tools = await rds.smembers(key_rpg_owned(uid, "tools"))
    acc = await rds.smembers(key_rpg_owned(uid, "acc"))
    bags = await rds.smembers(key_rpg_owned(uid, "bags"))
    return {"tools": list(tools), "acc": list(acc), "bags": list(bags)}

def rpg_calc_buffs(owned: dict):
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

    cd_mult = max(0.2, min(cd_mult, 1.0))  # keep sane
    yield_add = max(0.0, min(yield_add, 1.0))  # up to +100%
    return cd_mult, yield_add, cap_add

async def rpg_state(uid: int):
    await rpg_ensure(uid)
    bal = safe_int(await rds.get(key_balance(uid)))
    res = await rds.hgetall(key_rpg_res(uid))
    res = {k: safe_int(v) for k, v in res.items()}
    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add = rpg_calc_buffs(owned)
    next_ts = safe_int(await rds.get(key_rpg_cd(uid)))
    now = int(time.time())
    cooldown_remaining = max(0, next_ts - now)
    return {
        "balance": bal,
        "resources": res,
        "owned": owned,
        "cooldown_remaining": cooldown_remaining,
        "buffs": {"cd_mult": cd_mult, "yield_add": yield_add},
        "caps": cap_add
    }

def rpg_roll_gather():
    # Weighted random gather by rarity
    import random
    gains = {
        "wood": random.randint(2, 5),
        "stone": random.randint(1, 4),
        "iron": random.randint(0, 3),
        "silver": random.randint(0, 2),
        "gold": random.choice([0, 1]),
        "crystal": random.choice([0, 1]) if random.random() < 0.35 else 0
    }
    return gains

# ========= globals =========
rds: Optional[redis.Redis] = None

# ========= Telegram bot =========
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data="confirm_no")
        ]
    ])

def kb_open_webapp(user_id: int) -> InlineKeyboardMarkup:
    url = f"{WEBAPP_URL}?uid={user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть мини-аппку", web_app=WebAppInfo(url=url))]
    ])

async def ensure_user(user: Message | CallbackQuery):
    """Create all default fields so rating works for new users."""
    uid = user.from_user.id
    name = user.from_user.full_name or ""
    username = user.from_user.username or ""

    pipe = rds.pipeline()
    pipe.sadd(USERS_SET, uid)
    pipe.hsetnx(key_profile(uid), "name", name)
    pipe.hsetnx(key_profile(uid), "username", username)
    pipe.setnx(key_balance(uid), "0")
    pipe.zadd(USERS_ZSET, {uid: 0}, nx=True)
    pipe.hsetnx(key_stats(uid), "wins", 0)
    pipe.hsetnx(key_stats(uid), "losses", 0)
    pipe.hsetnx(key_stats(uid), "draws", 0)
    pipe.hsetnx(key_stats(uid), "games_total", 0)
    await pipe.execute()

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await ensure_user(message)
    user_id = message.from_user.id
    name = message.from_user.full_name

    confirmed = await rds.get(key_confirmed(user_id))
    if confirmed == "1":
        await message.answer(
            f"Привет, {name}! Доступ уже подтверждён ✅\nЖми кнопку ниже:",
            reply_markup=kb_open_webapp(user_id)
        )
        return

    await message.answer(
        "Привет! Чтобы продолжить и получить доступ к мини‑аппке, нужно подтвердить согласие.",
        reply_markup=kb_start()
    )

@dp.callback_query(F.data == "confirm_yes")
async def confirm_yes(call: CallbackQuery):
    await ensure_user(call)
    user_id = call.from_user.id
    name = call.from_user.full_name

    await rds.set(key_confirmed(user_id), "1")

    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer(
        f"Спасибо, {name}! Доступ подтверждён ✅",
        reply_markup=kb_open_webapp(user_id)
    )
    await call.answer()

@dp.callback_query(F.data == "confirm_no")
async def confirm_no(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Ок, без подтверждения доступ к мини‑аппке закрыт.")
    await call.answer()

# ========= HTTP API (aiohttp) =========
routes = web.RouteTableDef()
@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        resp = await handler(request)

    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp
def json_error(msg: str, status: int = 400):
    return web.json_response({"ok": False, "error": msg}, status=status)

def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

@routes.get("/api/balance")
async def api_balance(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    uid = safe_int(user_id)
    bal = await rds.get(key_balance(uid))
    if bal is None:
        bal = "0"
        await rds.set(key_balance(uid), bal)
        await rds.zadd(USERS_ZSET, {uid: 0}, nx=True)
        await rds.sadd(USERS_SET, uid)
    return web.json_response({"user_id": str(uid), "balance": int(bal)})

@routes.post("/api/add_point")
async def api_add_point(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    user_id = data.get("user_id")
    delta = data.get("delta", 0)

    if user_id is None:
        return json_error("user_id required")
    uid_int = safe_int(user_id, None)
    delta_int = safe_int(delta, None)
    if uid_int is None or delta_int is None:
        return json_error("bad data")

    confirmed = await rds.get(key_confirmed(uid_int))
    if confirmed != "1":
        return json_error("not confirmed", status=403)

    await rds.sadd(USERS_SET, uid_int)
    new_bal = await rds.incrby(key_balance(uid_int), delta_int)
    await rds.zadd(USERS_ZSET, {uid_int: new_bal})
    return web.json_response({"ok": True, "user_id": str(uid_int), "balance": int(new_bal)})

@routes.post("/api/report_game")
async def api_report_game(request: web.Request):
    """
    Body:
      { "user_id": "123", "game": "dice|bj|slot", "result": "win|lose|draw" }
    """
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    game = (data.get("game") or "").strip().lower()
    result = (data.get("result") or "").strip().lower()

    if not uid:
        return json_error("user_id required")
    if game not in ALLOWED_GAMES:
        return json_error("bad game")
    if result not in ("win", "lose", "draw"):
        return json_error("bad result")

    confirmed = await rds.get(key_confirmed(uid))
    if confirmed != "1":
        return json_error("not confirmed", status=403)

    await rds.sadd(USERS_SET, uid)

    # update overall stats
    pipe = rds.pipeline()
    pipe.hincrby(key_stats(uid), "games_total", 1)
    if result == "win":
        pipe.hincrby(key_stats(uid), "wins", 1)
    elif result == "lose":
        pipe.hincrby(key_stats(uid), "losses", 1)
    else:
        pipe.hincrby(key_stats(uid), "draws", 1)

    # update game stats
    gkey = key_gamestats(uid, game)
    pipe.hincrby(gkey, "games_total", 1)
    if result == "win":
        pipe.hincrby(gkey, "wins", 1)
    elif result == "lose":
        pipe.hincrby(gkey, "losses", 1)
    else:
        pipe.hincrby(gkey, "draws", 1)

    await pipe.execute()
    return web.json_response({"ok": True})


@routes.get("/api/rpg/state")
async def api_rpg_state(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    uid = safe_int(user_id, None)
    if uid is None:
        return json_error("bad user_id")
    confirmed = await rds.get(key_confirmed(uid))
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
    uid = safe_int(data.get("user_id"), None)
    if uid is None:
        return json_error("user_id required")
    confirmed = await rds.get(key_confirmed(uid))
    if confirmed != "1":
        return json_error("not confirmed", status=403)

    await rpg_ensure(uid)
    now = int(time.time())
    next_ts = safe_int(await rds.get(key_rpg_cd(uid)))
    if now < next_ts:
        return web.json_response({"ok": False, "error": "cooldown", "cooldown_remaining": next_ts - now})

    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add = rpg_calc_buffs(owned)

    gained = rpg_roll_gather()
    # apply yield bonus
    for k in gained:
        gained[k] = int(round(gained[k] * (1.0 + yield_add)))

    # update resources with caps
    pipe = rds.pipeline()
    cur = await rds.hgetall(key_rpg_res(uid))
    cur = {k: safe_int(v) for k, v in cur.items()}
    for r in RPG_RESOURCES:
        max_cap = RPG_MAX + int(cap_add.get(r, 0))
        new_val = min(max_cap, cur.get(r, 0) + gained.get(r, 0))
        pipe.hset(key_rpg_res(uid), r, new_val)

    base_cd = 300
    new_next = now + int(base_cd * cd_mult)
    pipe.set(key_rpg_cd(uid), new_next)
    await pipe.execute()

    st = await rpg_state(uid)
    return web.json_response({"ok": True, "gained": gained, "state": st})

@routes.post("/api/rpg/buy")
async def api_rpg_buy(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")
    uid = safe_int(data.get("user_id"), None)
    cat = (data.get("category") or "").lower()
    item_id = (data.get("item_id") or "").lower()

    if uid is None or not cat or not item_id:
        return json_error("bad data")

    confirmed = await rds.get(key_confirmed(uid))
    if confirmed != "1":
        return json_error("not confirmed", status=403)

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
    if await rds.sismember(owned_key, item_id):
        st = await rpg_state(uid)
        return web.json_response({"ok": True, "state": st})

    cost = int(item.get("cost", 0))
    bal = safe_int(await rds.get(key_balance(uid)))
    if bal < cost:
        return json_error("not enough points")

    pipe = rds.pipeline()
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
    uid = safe_int(data.get("user_id"), None)
    from_r = (data.get("from") or "").lower()
    to_r = (data.get("to") or "").lower()
    amount = safe_int(data.get("amount"), 1)

    if uid is None or not from_r or not to_r or amount <= 0:
        return json_error("bad data")

    confirmed = await rds.get(key_confirmed(uid))
    if confirmed != "1":
        return json_error("not confirmed", status=403)

    await rpg_ensure(uid)
    res = await rds.hgetall(key_rpg_res(uid))
    res = {k: safe_int(v) for k, v in res.items()}

    if to_r == "points":
        if from_r not in RPG_RESOURCES:
            return json_error("bad from")
        need = amount
        if res.get(from_r, 0) < need:
            return json_error("not enough resources")
        value = RPG_SELL_VALUES.get(from_r, 1) * amount
        pipe = rds.pipeline()
        pipe.hincrby(key_rpg_res(uid), from_r, -need)
        new_bal = await rds.incrby(key_balance(uid), value)
        pipe.zadd(USERS_ZSET, {uid: new_bal})
        await pipe.execute()
        st = await rpg_state(uid)
        return web.json_response({"ok": True, "state": st})

    # convert along chain at 5:1
    pair_ok = False
    for a, b in RPG_CHAIN:
        if from_r == a and to_r == b:
            pair_ok = True
            break
    if not pair_ok:
        return json_error("bad convert pair")

    rate = 5
    need = amount * rate
    if res.get(from_r, 0) < need:
        return json_error("not enough resources")

    pipe = rds.pipeline()
    pipe.hincrby(key_rpg_res(uid), from_r, -need)
    pipe.hincrby(key_rpg_res(uid), to_r, amount)
    await pipe.execute()

    st = await rpg_state(uid)
    return web.json_response({"ok": True, "state": st})
@routes.get("/api/leaderboard")
async def api_leaderboard(request: web.Request):
    """
    Query:
      limit=50
      sort=points|wins|winrate|games
      game=dice|bj|slot|all
    """
    limit = safe_int(request.query.get("limit"), 50)
    sort = (request.query.get("sort") or "points").lower()
    game = (request.query.get("game") or "all").lower()

    if game != "all" and game not in ALLOWED_GAMES:
        return json_error("bad game")

    user_ids: List[int] = [safe_int(x) for x in await rds.smembers(USERS_SET)]
    user_ids = [u for u in user_ids if u]

    rows: List[dict] = []
    for uid in user_ids:
        profile = await rds.hgetall(key_profile(uid))
        name = profile.get("name") or f"User {uid}"
        username = profile.get("username") or ""

        points = safe_int(await rds.get(key_balance(uid)))

        if game == "all":
            stats = await rds.hgetall(key_stats(uid))
        else:
            stats = await rds.hgetall(key_gamestats(uid, game))

        wins = safe_int(stats.get("wins"))
        losses = safe_int(stats.get("losses"))
        draws = safe_int(stats.get("draws"))
        games_total = safe_int(stats.get("games_total"))
        winrate = (wins / games_total) if games_total > 0 else 0.0

        rows.append({
            "user_id": uid,
            "name": name,
            "username": username,
            "points": points,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "games_total": games_total,
            "winrate": winrate
        })

    if sort == "points":
        rows.sort(key=lambda r: (r["points"], r["wins"]), reverse=True)
    elif sort == "wins":
        rows.sort(key=lambda r: (r["wins"], r["points"]), reverse=True)
    elif sort == "winrate":
        rows.sort(key=lambda r: (r["winrate"], r["wins"], r["games_total"]), reverse=True)
    elif sort == "games":
        rows.sort(key=lambda r: (r["games_total"], r["wins"]), reverse=True)
    else:
        return json_error("bad sort")

    return web.json_response({"ok": True, "game": game, "sort": sort, "rows": rows[:limit]})

async def run_api(app_host="0.0.0.0", app_port=8080):
    app = web.Application(middlewares=[cors_middleware])
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, app_host, app_port)
    await site.start()
    logging.info(f"API started on http://{app_host}:{app_port}")

async def main():
    global rds
    rds = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    await run_api()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
