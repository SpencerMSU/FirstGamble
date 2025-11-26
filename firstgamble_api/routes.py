import json
import random
import secrets
import time
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response

from .models import (
    AddPointRequest,
    AdminDrawRequest,
    AdminFindUserRequest,
    AdminLoginRequest,
    AdminPrizeRequest,
    AdminPrizeUpdateRequest,
    AdminSetPointsRequest,
    AuthContext,
    RaffleBuyRequest,
    ReportGameRequest,
    RpgBuyRequest,
    RpgConvertRequest,
    RpgGatherRequest,
    UpdateProfileRequest,
)
from .config import ADMIN_PASS, ADMIN_SESSION_TTL, ADMIN_TOKEN, ADMIN_USER
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
    key_prize_counter,
    key_prize_item,
    key_prizes_set,
    key_raffle_winners,
    key_ticket_counter,
    key_ticket_owners,
    key_user_tickets,
    key_user_raffle_wins,
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


def key_admin_session(session_id: str) -> str:
    return f"admin:session:{session_id}"


async def get_admin_user(request: Request) -> str:
    session_id = request.cookies.get("admin_session") or request.headers.get("X-Admin-Session")
    if not session_id:
        raise HTTPException(status_code=401, detail="admin session required")

    r = await get_redis()
    username = await r.get(key_admin_session(session_id))
    if not username:
        raise HTTPException(status_code=401, detail="invalid admin session")

    await r.expire(key_admin_session(session_id), ADMIN_SESSION_TTL)
    return username


def register_routes(app: FastAPI):
    async def rebuild_ticket_owners(r) -> Dict[str, int]:
        owners: Dict[str, int] = {}
        user_ids = await r.smembers(USERS_SET)
        for uid_raw in user_ids:
            uid = safe_int(uid_raw)
            if uid <= 0:
                continue
            tickets = await r.lrange(key_user_tickets(uid), 0, -1)
            for t in tickets:
                owners[t] = uid
        if owners:
            await r.hset(key_ticket_owners(), mapping={k: str(v) for k, v in owners.items()})
        return owners

    async def get_ticket_owners(r) -> Dict[str, int]:
        owners = await r.hgetall(key_ticket_owners())
        if owners:
            return {k: safe_int(v) for k, v in owners.items()}
        return await rebuild_ticket_owners(r)

    async def get_prizes(r):
        ids = await r.smembers(key_prizes_set())
        prizes = []
        for pid_raw in ids:
            pid = safe_int(pid_raw)
            data = await r.hgetall(key_prize_item(pid))
            if data:
                prizes.append(
                    {
                        "id": pid,
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "order": safe_int(data.get("order"), 0),
                    }
                )
        prizes.sort(key=lambda x: (x.get("order", 0), x.get("id", 0)))
        return prizes

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
    async def api_leaderboard(
        game: str = "all",
        sort: str = "points",
        limit: int = 100,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        r = await get_redis()

        game = (game or "all").lower()
        if game in {"*"}:
            game = "all"
        if game not in {"all", *ALLOWED_GAMES}:
            game = "all"

        sort = (sort or "points").lower()
        allowed_sorts = {"points", "wins", "games", "winrate", "losses", "draws"}
        if sort not in allowed_sorts:
            sort = "points"

        if limit is None or limit <= 0:
            limit = 100
        limit = min(limit, 100)

        top = await r.zrevrange(USERS_ZSET, 0, limit - 1, withscores=True)

        rows = []
        for uid, score in top:
            profile = await r.hgetall(key_profile(int(uid)))

            if game == "all":
                stats_key = key_stats(int(uid))
            else:
                stats_key = key_gamestats(int(uid), game)

            stats = await r.hgetall(stats_key)

            wins = int(stats.get("wins", 0) or 0)
            losses = int(stats.get("losses", 0) or 0)
            draws = int(stats.get("draws", 0) or 0)
            games_total = int(stats.get("games_total", 0) or 0)

            if games_total == 0:
                games_total = wins + losses + draws

            winrate = round(wins * 100.0 / games_total, 2) if games_total > 0 else 0.0

            rows.append(
                {
                    "user_id": str(uid),
                    "points": int(score),
                    "wins": wins,
                    "losses": losses,
                    "draws": draws,
                    "games_total": games_total,
                    "winrate": winrate,
                    "name": profile.get("name", ""),
                    "username": profile.get("username", ""),
                }
            )

        if sort == "wins":
            rows.sort(key=lambda x: x.get("wins", 0), reverse=True)
        elif sort == "games":
            rows.sort(key=lambda x: x.get("games_total", 0), reverse=True)
        elif sort == "winrate":
            rows.sort(key=lambda x: x.get("winrate", 0), reverse=True)
        elif sort == "losses":
            rows.sort(key=lambda x: x.get("losses", 0), reverse=True)
        elif sort == "draws":
            rows.sort(key=lambda x: x.get("draws", 0), reverse=True)
        else:
            rows.sort(key=lambda x: x.get("points", 0), reverse=True)

        return {"ok": True, "rows": rows}

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
        body: Optional[RaffleBuyRequest] = None,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        uid = auth.user_id
        r = await get_redis()
        await ensure_user(uid)

        PRICE = 500
        cnt = 1
        if body and body.count:
            try:
                cnt = int(body.count)
            except Exception:
                cnt = 1
        cnt = max(1, min(cnt, 20))

        bal = safe_int(await r.get(key_balance(uid)))
        total_cost = PRICE * cnt
        if bal < total_cost:
            return {"ok": False, "error": "not_enough_points", "message": "Недостаточно очков"}

        start_num = await r.incrby(key_ticket_counter(), cnt) - cnt
        tickets_bought = []
        owners_map = {}
        for i in range(cnt):
            ticket_val = start_num + i
            ticket = str(ticket_val).zfill(8)
            tickets_bought.append(ticket)
            owners_map[ticket] = uid

        pipe = r.pipeline()
        pipe.incrby(key_balance(uid), -total_cost)
        pipe.zadd(USERS_ZSET, {uid: bal - total_cost})
        if tickets_bought:
            pipe.rpush(key_user_tickets(uid), *tickets_bought)
            pipe.hset(key_ticket_owners(), mapping={k: str(v) for k, v in owners_map.items()})
        await pipe.execute()

        tickets = await r.lrange(key_user_tickets(uid), 0, -1)

        return {
            "ok": True,
            "ticket": tickets_bought[0] if tickets_bought else None,
            "tickets_bought": tickets_bought,
            "balance": bal - total_cost,
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

    @app.post("/api/admin/login")
    async def api_admin_login(body: AdminLoginRequest, response: Response) -> Dict[str, Any]:
        username = (body.username or "").strip()
        password = (body.password or "").strip()

        authorized = False
        if ADMIN_TOKEN and password == ADMIN_TOKEN:
            authorized = True
            username = username or ADMIN_USER
        elif username == ADMIN_USER and password == ADMIN_PASS:
            authorized = True

        if not authorized:
            raise HTTPException(status_code=401, detail="bad credentials")

        session_id = secrets.token_urlsafe(32)
        r = await get_redis()
        await r.setex(key_admin_session(session_id), ADMIN_SESSION_TTL, username)

        response.set_cookie(
            "admin_session",
            session_id,
            httponly=True,
            samesite="lax",
            max_age=ADMIN_SESSION_TTL,
        )
        return {"ok": True, "user": username}

    @app.post("/api/admin/logout")
    async def api_admin_logout(request: Request) -> Dict[str, Any]:
        session_id = request.cookies.get("admin_session") or request.headers.get("X-Admin-Session")
        if session_id:
            r = await get_redis()
            await r.delete(key_admin_session(session_id))
        return {"ok": True}

    @app.get("/api/admin/session")
    async def api_admin_session(username: str = Depends(get_admin_user)) -> Dict[str, Any]:
        return {"ok": True, "user": username}

    @app.get("/api/admin/raffle/prizes")
    async def api_admin_get_prizes(username: str = Depends(get_admin_user)) -> Dict[str, Any]:
        r = await get_redis()
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.post("/api/admin/raffle/prizes")
    async def api_admin_create_prize(
        body: AdminPrizeRequest, username: str = Depends(get_admin_user)
    ) -> Dict[str, Any]:
        r = await get_redis()
        pid = await r.incr(key_prize_counter())
        data = {"name": body.name, "description": body.description or "", "order": int(body.order or 0)}
        pipe = r.pipeline()
        pipe.sadd(key_prizes_set(), pid)
        pipe.hset(key_prize_item(pid), mapping=data)
        await pipe.execute()
        data.update({"id": pid})
        return {"ok": True, "prize": data}

    @app.put("/api/admin/raffle/prizes/{prize_id}")
    async def api_admin_update_prize(
        prize_id: int,
        body: AdminPrizeUpdateRequest,
        username: str = Depends(get_admin_user),
    ) -> Dict[str, Any]:
        r = await get_redis()
        exists = await r.sismember(key_prizes_set(), prize_id)
        if not exists:
            raise HTTPException(status_code=404, detail="prize not found")
        updates: Dict[str, Any] = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.description is not None:
            updates["description"] = body.description
        if body.order is not None:
            updates["order"] = int(body.order)
        if updates:
            await r.hset(key_prize_item(prize_id), mapping=updates)
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.delete("/api/admin/raffle/prizes/{prize_id}")
    async def api_admin_delete_prize(
        prize_id: int, username: str = Depends(get_admin_user)
    ) -> Dict[str, Any]:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.srem(key_prizes_set(), prize_id)
        pipe.delete(key_prize_item(prize_id))
        await pipe.execute()
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.get("/api/admin/raffle/winners")
    async def api_admin_winners(username: str = Depends(get_admin_user)) -> Dict[str, Any]:
        r = await get_redis()
        raw = await r.lrange(key_raffle_winners(), 0, -1)
        winners = []
        for item in raw:
            try:
                winners.append(json.loads(item))
            except Exception:
                continue
        return {"ok": True, "items": winners}

    @app.post("/api/admin/raffle/draw")
    async def api_admin_draw(
        body: AdminDrawRequest, username: str = Depends(get_admin_user)
    ) -> Dict[str, Any]:
        r = await get_redis()
        prizes = await get_prizes(r)
        if not prizes:
            raise HTTPException(status_code=400, detail="no prizes")
        owners = await get_ticket_owners(r)
        total_tickets = len(owners)
        if total_tickets == 0:
            raise HTTPException(status_code=400, detail="no tickets")

        if not body.force:
            existing = await r.llen(key_raffle_winners())
            if existing > 0:
                raise HTTPException(status_code=400, detail="already drawn")

        tickets_pool = list(owners.keys())
        random.shuffle(tickets_pool)

        used_users = set()
        used_tickets = set()
        winners = []

        for prize in prizes:
            available = [
                t
                for t in tickets_pool
                if t not in used_tickets and owners.get(t) not in used_users
            ]
            if not available:
                continue
            ticket = random.choice(available)
            uid = owners.get(ticket)
            used_tickets.add(ticket)
            if uid:
                used_users.add(uid)
            winners.append({"prize_id": prize.get("id"), "ticket": ticket, "user_id": uid})

        pipe = r.pipeline()
        pipe.delete(key_raffle_winners())
        if winners:
            pipe.rpush(key_raffle_winners(), *[json.dumps(w) for w in winners])
            for w in winners:
                pipe.rpush(key_user_raffle_wins(int(w.get("user_id"))), json.dumps(w))
        await pipe.execute()

        return {"ok": True, "items": winners, "total_tickets": total_tickets}

    def normalize_nickname(name: str) -> str:
        return (name or "").strip().lower()

    async def find_user_by_nick(r, nickname: str):
        target = normalize_nickname(nickname)
        if not target:
            return None
        user_ids = await r.smembers(USERS_SET)
        for uid_raw in user_ids:
            uid = safe_int(uid_raw)
            if uid <= 0:
                continue
            profile = await r.hgetall(key_profile(uid))
            if normalize_nickname(profile.get("name")) == target:
                bal = safe_int(await r.get(key_balance(uid)))
                return {"user_id": uid, "profile": profile, "balance": bal}
        return None

    @app.post("/api/admin/users/by_nickname")
    async def api_admin_user_by_nick(
        body: AdminFindUserRequest, username: str = Depends(get_admin_user)
    ) -> Dict[str, Any]:
        r = await get_redis()
        user = await find_user_by_nick(r, body.nickname)
        if not user:
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True, **user}

    @app.post("/api/admin/users/set_points")
    async def api_admin_set_points(
        body: AdminSetPointsRequest, username: str = Depends(get_admin_user)
    ) -> Dict[str, Any]:
        r = await get_redis()
        uid = body.user_id
        if (not uid or uid <= 0) and body.nickname:
            user = await find_user_by_nick(r, body.nickname)
            if user:
                uid = user.get("user_id")
        if not uid or uid <= 0:
            raise HTTPException(status_code=400, detail="user_id required")

        await ensure_user(uid)
        cur_balance = safe_int(await r.get(key_balance(uid)))

        if body.new_balance is not None:
            new_balance = int(body.new_balance)
        elif body.points_delta is not None:
            new_balance = cur_balance + int(body.points_delta)
        else:
            raise HTTPException(status_code=400, detail="no changes provided")

        pipe = r.pipeline()
        pipe.set(key_balance(uid), new_balance)
        pipe.zadd(USERS_ZSET, {uid: new_balance})
        await pipe.execute()

        profile = await r.hgetall(key_profile(uid))
        return {
            "ok": True,
            "user_id": uid,
            "balance": new_balance,
            "profile": profile,
        }

    return app
