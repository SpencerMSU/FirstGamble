import time

from aiohttp import web

from .config import BASE_DIR, CONSERVE_AUTH_TOKEN
from .rpg import (
    RPG_ACCESSORIES,
    RPG_BAGS,
    RPG_CHAIN,
    RPG_MAX,
    RPG_RESOURCES,
    RPG_SELL_VALUES,
    RPG_TOOLS,
    rpg_calc_buffs,
    rpg_ensure,
    rpg_get_owned,
    rpg_roll_gather,
    rpg_state,
    key_rpg_cd,
    key_rpg_owned,
    key_rpg_res,
)
from .redis_utils import (
    ALLOWED_GAMES,
    USERS_SET,
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
    sanitize_redis_string,
    safe_int,
)

routes = web.RouteTableDef()


# ====== helpers ======
def json_error(message: str, status: int = 400):
    return web.json_response({"ok": False, "error": message}, status=status)


def is_conserve_request(request: web.Request) -> bool:
    if not CONSERVE_AUTH_TOKEN:
        return False
    token = request.headers.get("X-ConServe-Auth") or request.headers.get("X-Conserve-Auth")
    return token == CONSERVE_AUTH_TOKEN


# ================= RAFFLE TICKETS =================
def key_ticket_counter() -> str:
    return "raffle:ticket:counter"  # global counter


def key_user_tickets(uid: int) -> str:
    return f"user:{uid}:raffle:tickets"  # list of ticket numbers


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

    st = await r.hgetall(key_stats(uid))
    st = {k: safe_int(v) for k, v in st.items()}

    per_game = {}
    for g in ALLOWED_GAMES:
        d = await r.hgetall(key_gamestats(uid, g))
        per_game[g] = {k: safe_int(v) for k, v in d.items()}

    return web.json_response({"ok": True, "stats": st, "per_game": per_game})


@routes.post("/api/profile")
async def api_profile(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    name = (data.get("name") or "").strip()
    username = (data.get("username") or "").strip()

    if uid <= 0:
        return json_error("bad user_id")

    r = await get_redis()
    if not is_conserve_request(request):
        confirmed = await r.get(key_confirmed(uid))
        if confirmed != "1":
            return json_error("not confirmed", status=403)

    await ensure_user(uid)
    name_clean = sanitize_redis_string(name)
    username_clean = sanitize_redis_string(username)

    await r.hset(key_profile(uid), mapping={"name": name_clean, "username": username_clean})
    return web.json_response({"ok": True})


@routes.get("/api/leaderboard")
async def api_leaderboard(request: web.Request):
    r = await get_redis()

    top = await r.zrevrange(USERS_ZSET, 0, 99, withscores=True)
    items = []
    for uid, score in top:
        user_data = await r.hgetall(key_profile(int(uid)))
        items.append({"user_id": str(uid), "score": int(score), "profile": user_data})

    my_uid = request.query.get("user_id")
    if my_uid:
        my_pos = await r.zrevrank(USERS_ZSET, my_uid)
        my_score = await r.zscore(USERS_ZSET, my_uid)
        if my_pos is not None and my_score is not None:
            items.insert(0, {"me": True, "pos": my_pos + 1, "score": int(my_score)})

    return web.json_response({"ok": True, "items": items})


@routes.get("/api/leaderboard/positions")
async def api_leaderboard_positions(request: web.Request):
    r = await get_redis()

    raw = await r.zrevrange(USERS_ZSET, 0, -1, withscores=True)
    positions = {str(uid): pos + 1 for pos, (uid, _) in enumerate(raw)}
    return web.json_response({"ok": True, "positions": positions})


@routes.get("/api/leaderboard/extended")
async def api_leaderboard_extended(request: web.Request):
    r = await get_redis()

    raw = await r.zrevrange(USERS_ZSET, 0, -1, withscores=True)
    items = []
    for pos, (uid, score) in enumerate(raw, start=1):
        user_data = await r.hgetall(key_profile(int(uid)))
        items.append({"user_id": str(uid), "pos": pos, "score": int(score), "profile": user_data})
    return web.json_response({"ok": True, "items": items})


@routes.post("/api/rpg/gather")
async def api_rpg_gather(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    uid = safe_int(data.get("user_id"))
    if uid <= 0:
        return json_error("bad user_id")

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

    return web.json_response({"ok": True, "user_id": str(uid), "balance": bal, "tickets": tickets})


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
