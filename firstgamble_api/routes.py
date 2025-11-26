import time
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .models import (
    AddPointRequest,
    AuthContext,
    RaffleBuyRequest,
    ReportGameRequest,
    RpgBuyRequest,
    RpgConvertRequest,
    RpgGatherRequest,
    UpdateProfileRequest,
)
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
from .services import (
    RPG_ACCESSORIES,
    RPG_BAGS,
    RPG_CHAIN,
    RPG_RESOURCES,
    RPG_SELL_VALUES,
    RPG_TOOLS,
    build_auth_context_from_headers,
    key_rpg_cd,
    key_rpg_owned,
    key_rpg_res,
    key_ticket_counter,
    key_user_tickets,
    rpg_calc_buffs,
    rpg_ensure,
    rpg_get_owned,
    rpg_roll_gather,
    rpg_state,
    _ensure_profile_identity_fields,
)


async def get_current_auth(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-InitData"),
    x_conserve_auth: Optional[str] = Header(default=None, alias="X-ConServe-Auth"),
) -> AuthContext:
    try:
        body_data = None
        if request.method.upper() != "GET":
            try:
                body_data = await request.json()
            except Exception:
                body_data = None
        auth = build_auth_context_from_headers(
            request.method,
            body_data,
            dict(request.query_params),
            x_telegram_init_data,
            x_conserve_auth,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    r = await get_redis()
    if auth.from_telegram:
        confirmed = await r.get(key_confirmed(auth.user_id))
        if confirmed != "1":
            raise HTTPException(status_code=403, detail="not confirmed")
        await ensure_user(auth.user_id)
    if auth.from_conserve:
        await ensure_user(auth.user_id)
    return auth


def register_routes(app: FastAPI):
    @app.get("/api/ping")
    async def api_ping() -> Dict[str, Any]:
        return {"ok": True, "message": "pong"}

    @app.get("/api/balance")
    async def api_balance(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        bal = await get_balance(auth.user_id)
        return {"ok": True, "balance": bal}

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
        stats = {k: safe_int(v) for k, v in stats.items()}

        per_game = {}
        for g in ALLOWED_GAMES:
            d = await r.hgetall(key_gamestats(auth.user_id, g))
            per_game[g] = {k: safe_int(v) for k, v in d.items()}

        return {"ok": True, "stats": stats, "per_game": per_game}

    @app.post("/api/profile")
    async def api_update_profile(
        body: UpdateProfileRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        if not auth.from_telegram:
            raise HTTPException(status_code=403, detail="webapp only")

        name = (body.name or "").strip()
        username = (body.username or "").strip()

        await ensure_user(auth.user_id)

        r = await get_redis()
        await r.hset(key_profile(auth.user_id), mapping={"name": name, "username": username})
        return {"ok": True}

    @app.get("/api/leaderboard")
    async def api_leaderboard(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        r = await get_redis()

        top = await r.zrevrange(USERS_ZSET, 0, 99, withscores=True)
        items = []
        for uid, score in top:
            user_data = await r.hgetall(key_profile(int(uid)))
            items.append({"user_id": str(uid), "score": int(score), "profile": user_data})

        my_pos = await r.zrevrank(USERS_ZSET, auth.user_id)
        my_score = await r.zscore(USERS_ZSET, auth.user_id)
        if my_pos is not None and my_score is not None:
            items.insert(0, {"me": True, "pos": my_pos + 1, "score": int(my_score)})

        return {"ok": True, "items": items}

    @app.get("/api/leaderboard/positions")
    async def api_leaderboard_positions(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        r = await get_redis()

        raw = await r.zrevrange(USERS_ZSET, 0, -1, withscores=True)
        positions = {str(uid): pos + 1 for pos, (uid, _) in enumerate(raw)}
        return {"ok": True, "positions": positions}

    @app.get("/api/leaderboard/extended")
    async def api_leaderboard_extended(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        r = await get_redis()

        raw = await r.zrevrange(USERS_ZSET, 0, -1, withscores=True)
        items = []
        for pos, (uid, score) in enumerate(raw, start=1):
            user_data = await r.hgetall(key_profile(int(uid)))
            items.append({"user_id": str(uid), "pos": pos, "score": int(score), "profile": user_data})
        return {"ok": True, "items": items}

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
        for k in gained:
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

    return app
