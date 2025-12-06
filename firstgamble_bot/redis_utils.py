import re
import logging
from typing import Optional

import redis.asyncio as redis

from .config import REDIS_HOST, REDIS_PORT, REDIS_DB

rds: Optional[redis.Redis] = None
logger = logging.getLogger(__name__)


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

ALLOWED_GAMES = {"dice", "bj", "slot", "snake", "runner", "pulse"}

BALANCE_LIMIT = 999_999
BALANCE_RESET = 2_000

_CONTROL_CHARS_RE = re.compile(r"[\r\n\x00]")


def sanitize_redis_string(value: Optional[str]) -> str:
    """Strip control chars that can be used for Redis injection."""

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
    bal = safe_int(val)
    if bal > BALANCE_LIMIT:
        await r.set(key_balance(user_id), BALANCE_RESET)
        await r.zadd(USERS_ZSET, {user_id: BALANCE_RESET})
        return BALANCE_RESET
    return bal


def clamp_balance(value: int) -> int:
    if value > BALANCE_LIMIT:
        return BALANCE_LIMIT
    if value < -BALANCE_LIMIT:
        return -BALANCE_LIMIT
    return value


async def add_points(user_id: int, delta: int, game_code: str = "unknown") -> int:
    r = await get_redis()
    pipe = r.pipeline()
    pipe.incrby(key_balance(user_id), delta)
    pipe.get(key_balance(user_id))
    res = await pipe.execute()
    new_balance = clamp_balance(safe_int(res[1]))
    await r.set(key_balance(user_id), new_balance)
    await r.zadd(USERS_ZSET, {user_id: new_balance})
    if delta > 0:
        logger.info(
            f"Игрок с id {user_id} получил {delta} очков в игре {game_code} "
            f"(новый баланс: {new_balance})"
        )
    return new_balance
