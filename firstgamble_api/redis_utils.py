import re
from typing import Optional

import redis.asyncio as redis

from .config import REDIS_DB, REDIS_HOST, REDIS_PORT

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


def key_admin_session(token: str) -> str:
    return f"admin:session:{token}"


USERS_ZSET = "leaderboard:points"  # zset: user_id -> points
USERS_SET = "users:all"  # set of user_ids

ALLOWED_GAMES = {"dice", "bj", "slot", "snake", "runner", "pulse"}

_CONTROL_CHARS_RE = re.compile(r"[\r\n\x00]")


def sanitize_redis_string(value: Optional[str]) -> str:
    """Remove Redis injection primitives (CR, LF, NULL) from a string."""

    if value is None:
        return ""

    text = str(value)
    if not text:
        return ""

    return _CONTROL_CHARS_RE.sub("", text)


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


def _normalize_game_nick(nick: str) -> str:
    return (nick or "").strip().lower()


async def find_user_by_game_nick(nick: str) -> int:
    target = _normalize_game_nick(nick)
    if not target:
        return 0

    r = await get_redis()
    user_ids = await r.smembers(USERS_SET)
    for uid_raw in user_ids:
        uid = safe_int(uid_raw)
        if uid <= 0:
            continue

        profile = await r.hgetall(key_profile(uid))
        if _normalize_game_nick(profile.get("Nick_Name")) == target:
            return uid

    return 0
