import logging
import time
import hmac
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field

import redis.asyncio as redis
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ================== Config / Redis ==================

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

# токен для SAMP/игры
CONSERVE_AUTH_TOKEN = config.get("ConServeAuthToken") or config.get("CONSERVE_AUTH_TOKEN")

REDIS_HOST = config.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(config.get("REDIS_PORT", "6379"))
REDIS_DB   = int(config.get("REDIS_DB", "0"))

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

def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# ================== Redis keys / доменная логика ==================

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

async def ensure_user(user_id: int):
    r = await get_redis()
    await r.sadd(USERS_SET, user_id)

    bal = await r.get(key_balance(user_id))
    if bal is None:
        await r.set(key_balance(user_id), "0")
        await r.zadd(USERS_ZSET, {user_id: 0}, nx=True)

    if not await r.exists(key_profile(user_id)):
        await r.hset(
            key_profile(user_id),
            mapping={"name": "", "username": "", "tg_id": ""},
        )

    if not await r.exists(key_stats(user_id)):
        await r.hset(key_stats(user_id), mapping={
            "wins": 0, "losses": 0, "draws": 0, "games_total": 0
        })

    for g in ALLOWED_GAMES:
        ks = key_gamestats(user_id, g)
        if not await r.exists(ks):
            await r.hset(ks, mapping={
                "wins": 0, "losses": 0, "draws": 0, "games_total": 0
            })

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

# ---------- RPG ----------

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
    "acc10":{"name": "Корона старателя", "cost": 30, "cd_red": 0.20, "yield_add": 0.20},
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
    "bag1":  {"name": "Мешок из ткани",         "cost": 3,  "cap_add": 50},
    "bag2":  {"name": "Сумка старателя",        "cost": 6,  "cap_add": 100},
    "bag3":  {"name": "Рюкзак шахтёра",         "cost": 12, "cap_add": 200},
    "bag4":  {"name": "Укреплённый рюкзак",     "cost": 18, "cap_add": 300},
    "bag5":  {"name": "Экспедиционный мешок",  "cost": 25, "cap_add": 450},
    "bag6":  {"name": "Каркасная сумка",       "cost": 33, "cap_add": 650},
    "bag7":  {"name": "Горный баул",           "cost": 42, "cap_add": 900},
    "bag8":  {"name": "Сумка инженера",        "cost": 55, "cap_add": 1200},
    "bag9":  {"name": "Артефактный рюкзак",    "cost": 70, "cap_add": 1600},
    "bag10": {"name": "Легендарный контейнер", "cost": 95, "cap_add": 2200},
}

RPG_SELL_VALUES = {"wood": 1, "stone": 2, "iron": 5, "silver": 8, "gold": 12, "crystal": 20}
RPG_CHAIN = [("wood", "stone"), ("stone", "iron"), ("iron", "silver"), ("silver", "gold"), ("gold", "crystal")]

def key_rpg_res(uid: int) -> str:
    return f"user:{uid}:rpg:res"

def key_rpg_cd(uid: int) -> str:
    return f"user:{uid}:rpg:cd"

def key_rpg_owned(uid: int, cat: str) -> str:
    return f"user:{uid}:rpg:owned:{cat}"

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
        "caps": cap_add
    }

def rpg_roll_gather():
    import random
    return {
        "wood": random.randint(2, 5),
        "stone": random.randint(1, 4),
        "iron": random.randint(0, 3),
        "silver": random.randint(0, 2),
        "gold": random.choice([0, 1]),
        "crystal": 1 if random.random() < 0.35 else 0
    }

# ---------- Raffle ----------

def key_ticket_counter() -> str:
    return "raffle:ticket:counter"

def key_user_tickets(uid: int) -> str:
    return f"user:{uid}:raffle:tickets"

# ================== Telegram WebApp auth ==================

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

class AuthContext(BaseModel):
    user_id: int
    from_telegram: bool
    from_conserve: bool
    username: Optional[str] = None
    tg_id: Optional[int] = None

async def get_current_auth(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-InitData"),
    x_conserve_auth: Optional[str] = Header(default=None, alias="X-ConServe-Auth"),
) -> AuthContext:
    r = await get_redis()

    # Telegram WebApp
    if x_telegram_init_data:
        try:
            data = parse_init_data(x_telegram_init_data)
            user = data.get("user") or {}
            uid = int(user.get("id"))
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"bad telegram auth: {e}")

        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            raise HTTPException(status_code=403, detail="not confirmed")

        await ensure_user(uid)
        return AuthContext(
            user_id=uid,
            from_telegram=True,
            from_conserve=False,
            username=user.get("username"),
            tg_id=uid,
        )

    # Внешняя игра (SAMP) по ConServeAuthToken
    if x_conserve_auth and CONSERVE_AUTH_TOKEN and x_conserve_auth == CONSERVE_AUTH_TOKEN:
        uid_val: Optional[int] = None
        if request.method.upper() == "GET":
            uid_val = safe_int(request.query_params.get("user_id"))
        else:
            try:
                body = await request.json()
                uid_val = safe_int(body.get("user_id"))
            except Exception:
                uid_val = None
        if not uid_val or uid_val <= 0:
            raise HTTPException(status_code=400, detail="user_id required for external auth")

        await ensure_user(uid_val)
        return AuthContext(user_id=uid_val, from_telegram=False, from_conserve=True)

    raise HTTPException(status_code=401, detail="unauthorized")

# ================== FastAPI app ==================

app = FastAPI(
    title="FirstGamble API",
    description="HTTP API для мини-приложения, бота и внешних игр.",
    version="1.0.0",
)

# CORS (пока всё, потом можно зажать до firstgamble.ru)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

def api_error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)

# ================== Schemas ==================

class AddPointRequest(BaseModel):
    user_id: Optional[str] = None
    game: str
    delta: Optional[int] = 1

class ReportGameRequest(BaseModel):
    user_id: Optional[str] = None
    game: str
    result: str

class UpdateProfileRequest(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None

class RpgGatherRequest(BaseModel):
    user_id: Optional[str] = None

class RpgBuyRequest(BaseModel):
    user_id: Optional[str] = None
    category: str
    item_id: str


class RpgConvertRequest(BaseModel):
    user_id: Optional[str] = None
    from_: str = Field(alias="from")
    to: str
    amount: int

    model_config = {"populate_by_name": True}

class RaffleBuyRequest(BaseModel):
    user_id: Optional[str] = None

# ================== Endpoints ==================

@app.get("/api/ping")
async def api_ping() -> Dict[str, Any]:
    return {"ok": True, "message": "pong"}

@app.get("/api/balance")
async def api_balance(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
    bal = await get_balance(auth.user_id)
    return {"ok": True, "balance": bal}

def _normalize_username(username: Optional[str]) -> str:
    if not username:
        return ""
    username = str(username).strip()
    if username.startswith("@"):  # убираем @ для хранения
        username = username[1:]
    return username


def _ensure_profile_identity_fields(
    profile: Dict[str, Any], username: Optional[str], tg_id: Optional[int]
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    uname = _normalize_username(username)
    if uname and not profile.get("username"):
        mapping["username"] = uname
    if tg_id and not profile.get("tg_id"):
        mapping["tg_id"] = str(tg_id)
    return mapping


@app.get("/api/profile")
async def api_profile(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
    if not auth.from_telegram:
        raise HTTPException(status_code=403, detail="webapp only")

    r = await get_redis()
    await ensure_user(auth.user_id)
    profile = await r.hgetall(key_profile(auth.user_id))

    mapping = _ensure_profile_identity_fields(profile, auth.username, auth.tg_id)
    if mapping:
        await r.hset(key_profile(auth.user_id), mapping=mapping)
        profile.update(mapping)

    return {
        "ok": True,
        "user_id": auth.user_id,
        "name": profile.get("name") or "",
        "username": profile.get("username") or "",
        "tg_id": int(profile.get("tg_id") or auth.user_id),
    }

@app.post("/api/add_point")
async def api_add_point(
    body: AddPointRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    game = (body.game or "").strip().lower()
    if game not in ALLOWED_GAMES:
        return {"ok": False, "error": "bad game"}

    delta = body.delta or 1
    if delta <= 0:
        delta = 1

    r = await get_redis()
    await ensure_user(auth.user_id)
    new_balance = await add_points(auth.user_id, delta)

    return {"ok": True, "balance": new_balance}

@app.post("/api/report_game")
async def api_report_game(
    body: ReportGameRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    game = (body.game or "").strip().lower()
    result = (body.result or "").strip().lower()

    if game not in ALLOWED_GAMES:
        return {"ok": False, "error": "bad game"}
    if result not in {"win", "loss", "draw"}:
        return {"ok": False, "error": "bad result"}

    r = await get_redis()
    await ensure_user(auth.user_id)

    field_map = {"win": "wins", "loss": "losses", "draw": "draws"}
    field = field_map[result]

    await r.hincrby(key_stats(auth.user_id), field, 1)
    await r.hincrby(key_stats(auth.user_id), "games_total", 1)

    await r.hincrby(key_gamestats(auth.user_id, game), field, 1)
    await r.hincrby(key_gamestats(auth.user_id, game), "games_total", 1)

    return {"ok": True}

@app.get("/api/stats")
async def api_stats(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
    r = await get_redis()
    await ensure_user(auth.user_id)

    stats = await r.hgetall(key_stats(auth.user_id))

    games_stats: Dict[str, Dict[str, int]] = {}
    for g in ALLOWED_GAMES:
        gs = await r.hgetall(key_gamestats(auth.user_id, g))
        games_stats[g] = {k: safe_int(v) for k, v in gs.items()}

    return {
        "ok": True,
        "stats": {k: safe_int(v) for k, v in stats.items()},
        "games": games_stats,
    }

@app.get("/api/leaderboard")
async def api_leaderboard(
    game: str = "all",
    sort: str = "points",
    limit: int = 10,
) -> Dict[str, Any]:
    game = (game or "all").strip().lower()
    sort_by = (sort or "points").strip().lower()
    if limit <= 0 or limit > 100:
        limit = 10

    r = await get_redis()
    if game not in {"all", "dice", "bj", "slot"}:
        game = "all"
    if sort_by not in {"points", "wins", "winrate", "games"}:
        sort_by = "points"

    user_ids = await r.smembers(USERS_SET)
    rows: List[Dict[str, Any]] = []
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

        rows.append({
            "user_id": uid,
            "points": points,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "games_total": games_total,
            "winrate": winrate,
            "name": profile.get("name") or "",
            "username": profile.get("username") or "",
        })

    def sort_key(row: Dict[str, Any]):
        if sort_by == "wins":
            return (row["wins"], row["points"])
        if sort_by == "winrate":
            return (row["winrate"], row["games_total"], row["points"])
        if sort_by == "games":
            return (row["games_total"], row["points"])
        return (row["points"], row["wins"])

    rows.sort(key=sort_key, reverse=True)
    rows = rows[:limit]

    return {"ok": True, "rows": rows}

@app.post("/api/update_profile")
async def api_update_profile(
    body: UpdateProfileRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    if not auth.from_telegram:
        raise HTTPException(status_code=403, detail="webapp only")

    name = (body.name or "").strip()
    r = await get_redis()
    await ensure_user(auth.user_id)

    profile = await r.hgetall(key_profile(auth.user_id))
    current_name = (profile.get("name") or "").strip()
    if current_name:
        return {"ok": False, "error": "Никнейм уже установлен"}

    if not name:
        return {"ok": False, "error": "Никнейм обязателен"}

    if not re.fullmatch(r"^[A-Za-z0-9_-]{3,20}$", name):
        return {
            "ok": False,
            "error": "Никнейм должен быть 3-20 символов: латиница, цифры, _ или -",
        }

    BAD_WORDS = [
        "хуй",
        "пизд",
        "еба",
        "бля",
        "сука",
        "fuck",
        "shit",
        "bitch",
        "asshole",
    ]
    name_lc = name.lower()
    if any(bad in name_lc for bad in BAD_WORDS):
        return {"ok": False, "error": "Никнейм содержит запрещённые слова"}

    mapping: Dict[str, str] = {"name": name}
    mapping.update(_ensure_profile_identity_fields(profile, auth.username, auth.tg_id))

    await r.hset(key_profile(auth.user_id), mapping=mapping)

    return {"ok": True}

# ---------- RPG ----------

@app.get("/api/rpg/state")
async def api_rpg_state(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
    st = await rpg_state(auth.user_id)
    return {"ok": True, "state": st}

@app.post("/api/rpg/gather")
async def api_rpg_gather(
    body: RpgGatherRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    uid = auth.user_id
    r = await get_redis()
    await rpg_ensure(uid)
    now = int(time.time())
    next_ts = safe_int(await r.get(key_rpg_cd(uid)))
    if now < next_ts:
        return {
            "ok": False,
            "error": "cooldown",
            "cooldown_remaining": next_ts - now,
        }

    owned = await rpg_get_owned(uid)
    cd_mult, yield_add, cap_add = rpg_calc_buffs(owned)

    gained = rpg_roll_gather()
    for k in list(gained.keys()):
        gained[k] = int(round(gained[k] * (1.0 + yield_add)))

    cur = await r.hgetall(key_rpg_res(uid))
    cur_int = {k: safe_int(v) for k, v in cur.items()}

    pipe = r.pipeline()
    for res_name in RPG_RESOURCES:
        max_cap = RPG_MAX + int(cap_add.get(res_name, 0))
        new_val = min(max_cap, cur_int.get(res_name, 0) + gained.get(res_name, 0))
        pipe.hset(key_rpg_res(uid), res_name, new_val)

    base_cd = 300
    pipe.set(key_rpg_cd(uid), now + int(base_cd * cd_mult))
    await pipe.execute()

    st = await rpg_state(uid)
    return {"ok": True, "gained": gained, "state": st}

@app.post("/api/rpg/buy")
async def api_rpg_buy(
    body: RpgBuyRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    uid = auth.user_id
    cat = (body.category or "").lower()
    item_id = (body.item_id or "").lower()

    if not cat or not item_id:
        return {"ok": False, "error": "bad data"}

    r = await get_redis()
    await ensure_user(uid)

    if cat == "tools":
        store = RPG_TOOLS
    elif cat == "acc":
        store = RPG_ACCESSORIES
    elif cat == "bags":
        store = RPG_BAGS
    else:
        return {"ok": False, "error": "bad category"}

    item = store.get(item_id)
    if not item:
        return {"ok": False, "error": "bad item"}

    owned_key = key_rpg_owned(uid, cat)
    if await r.sismember(owned_key, item_id):
        st = await rpg_state(uid)
        return {"ok": True, "state": st}

    cost = int(item.get("cost", 0))
    bal = safe_int(await r.get(key_balance(uid)))
    if bal < cost:
        return {"ok": False, "error": "not enough points"}

    pipe = r.pipeline()
    pipe.incrby(key_balance(uid), -cost)
    pipe.zadd(USERS_ZSET, {uid: bal - cost})
    pipe.sadd(owned_key, item_id)
    await pipe.execute()

    st = await rpg_state(uid)
    return {"ok": True, "state": st}

@app.post("/api/rpg/convert")
async def api_rpg_convert(
    body: RpgConvertRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    uid = auth.user_id
    from_r = (body.from_ or "").lower()
    to_r = (body.to or "").lower()
    amount = body.amount or 1

    if not from_r or not to_r or amount <= 0:
        return {"ok": False, "error": "bad data"}

    r = await get_redis()
    await rpg_ensure(uid)
    res = await r.hgetall(key_rpg_res(uid))
    res_int = {k: safe_int(v) for k, v in res.items()}

    if to_r == "points":
        if from_r not in RPG_RESOURCES:
            return {"ok": False, "error": "bad from"}
        need = amount
        if res_int.get(from_r, 0) < need:
            return {"ok": False, "error": "not enough resources"}
        value = RPG_SELL_VALUES.get(from_r, 1) * amount

        pipe = r.pipeline()
        pipe.hincrby(key_rpg_res(uid), from_r, -need)
        pipe.incrby(key_balance(uid), value)
        await pipe.execute()

        new_bal = safe_int(await r.get(key_balance(uid)))
        await r.zadd(USERS_ZSET, {uid: new_bal})

        st = await rpg_state(uid)
        return {"ok": True, "state": st}

    pair_ok = any(from_r == a and to_r == b for a, b in RPG_CHAIN)
    if not pair_ok:
        return {"ok": False, "error": "bad convert pair"}

    rate = 5
    need = amount * rate
    if res_int.get(from_r, 0) < need:
        return {"ok": False, "error": "not enough resources"}

    pipe = r.pipeline()
    pipe.hincrby(key_rpg_res(uid), from_r, -need)
    pipe.hincrby(key_rpg_res(uid), to_r, amount)
    await pipe.execute()

    st = await rpg_state(uid)
    return {"ok": True, "state": st}

# ---------- Raffle / cabinet ----------

@app.post("/api/raffle/buy_ticket")
async def api_buy_ticket(
    body: RaffleBuyRequest,
    auth: AuthContext = Depends(get_current_auth),
) -> Dict[str, Any]:
    uid = auth.user_id
    r = await get_redis()
    await ensure_user(uid)

    PRICE = 500
    bal = safe_int(await r.get(key_balance(uid)))
    if bal < PRICE:
        return {"ok": False, "error": "not enough points"}

    num = await r.incr(key_ticket_counter()) - 1
    ticket = str(num).zfill(8)

    pipe = r.pipeline()
    pipe.incrby(key_balance(uid), -PRICE)
    pipe.zadd(USERS_ZSET, {uid: bal - PRICE})
    pipe.rpush(key_user_tickets(uid), ticket)
    await pipe.execute()

    tickets = await r.lrange(key_user_tickets(uid), 0, -1)

    return {
        "ok": True,
        "ticket": ticket,
        "balance": bal - PRICE,
        "tickets": tickets,
    }

@app.get("/api/cabinet")
async def api_cabinet(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
    uid = auth.user_id
    r = await get_redis()
    await ensure_user(uid)

    bal = safe_int(await r.get(key_balance(uid)))
    tickets = await r.lrange(key_user_tickets(uid), 0, -1)

    return {
        "ok": True,
        "user_id": str(uid),
        "balance": bal,
        "tickets": tickets,
    }
