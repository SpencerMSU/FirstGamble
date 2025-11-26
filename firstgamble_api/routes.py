import json
import logging
import random
import time
from typing import Any, Dict, Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request

from .models import (
    AddPointRequest,
    AdminDrawRequest,
    AdminFindUserRequest,
    AdminPrizeRequest,
    AdminPrizeUpdateRequest,
    AdminSetPointsRequest,
    AuthContext,
    BuyRaffleTicketRequest,
    ReportGameRequest,
    RpgBuyRequest,
    RpgConvertRequest,
    RpgGatherRequest,
    UpdateProfileRequest,
)
from .config import (
    ADMIN_TG_ID,
    RAFFLE_TICKET_PRICE,
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
    key_prize_counter,
    key_prize_item,
    key_prizes_set,
    key_raffle_status,
    key_last_raffle_winners,
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


logger = logging.getLogger(__name__)


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

    async def get_raffle_status(r) -> str:
        status = await r.get(key_raffle_status())
        return (status or "preparing").lower()

    async def resolve_winner_name(r, uid: Optional[int]) -> str:
        if not uid:
            return ""
        profile = await r.hgetall(key_profile(uid))
        return (
            profile.get("name")
            or (f"@{profile.get('username')}" if profile.get("username") else "")
            or f"user {uid}"
        )

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
            "is_admin": bool(auth.user_id == ADMIN_TG_ID),
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
    async def api_raffle_buy_ticket(
        body: BuyRaffleTicketRequest = Body(default_factory=BuyRaffleTicketRequest),
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        uid = auth.user_id

        try:
            r = await get_redis()
            await ensure_user(uid)

            count = max(1, min(body.count or 1, 100))

            balance_raw = await r.get(key_balance(uid))
            balance = safe_int(balance_raw)
            total_cost = RAFFLE_TICKET_PRICE * count

            if balance < total_cost:
                return {"ok": False, "error": "not_enough_points", "balance": balance}

            last_ticket = await r.incrby(key_ticket_counter(), count)
            first_ticket = last_ticket - count + 1
            bought_numbers = list(range(first_ticket, last_ticket + 1))

            new_balance = balance - total_cost
            tickets_key = key_user_tickets(uid)
            owners_map = {str(num): str(uid) for num in bought_numbers}

            pipe = r.pipeline()
            pipe.set(key_balance(uid), new_balance)
            pipe.zadd(USERS_ZSET, {uid: new_balance})
            pipe.rpush(tickets_key, *[str(num) for num in bought_numbers])
            pipe.hset(key_ticket_owners(), mapping=owners_map)
            status = await get_raffle_status(r)
            if status != "finished":
                pipe.set(key_raffle_status(), "active")
            await pipe.execute()

            user_tickets = [safe_int(t) for t in await r.lrange(tickets_key, 0, -1)]

            return {
                "ok": True,
                "balance": new_balance,
                "bought": bought_numbers,
                "tickets": user_tickets,
            }
        except Exception:
            logger.exception("raffle buy ticket failed")
            return {"ok": False, "error": "internal_error"}

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

    @app.get("/api/raffle/state")
    async def api_raffle_state(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        r = await get_redis()
        status = await get_raffle_status(r)

        result = {"ok": True, "status": status, "prizes": []}
        if status in {"preparing", "closed"}:
            return result

        prizes = await get_prizes(r)
        winners_raw = await r.lrange(key_raffle_winners(), 0, -1)
        winners = []
        for item in winners_raw:
            try:
                winners.append(json.loads(item))
            except Exception:
                continue

        winners_by_prize: Dict[int, Dict[str, Any]] = {}
        for w in winners:
            pid = safe_int(w.get("prize_id"))
            if pid:
                winners_by_prize[pid] = w

        prize_rows = []
        for prize in prizes:
            pid = prize.get("id")
            winner = winners_by_prize.get(pid) if status == "finished" else None
            ticket_no = None
            winner_name = None
            if winner:
                ticket_no = safe_int(winner.get("ticket_no") or winner.get("ticket")) or None
                winner_name = await resolve_winner_name(r, safe_int(winner.get("user_id"))) or None

            prize_rows.append(
                {
                    "id": pid,
                    "name": prize.get("name", ""),
                    "description": prize.get("description", ""),
                    "order": prize.get("order", 0),
                    "winner_name": winner_name,
                    "ticket_no": ticket_no,
                }
            )

        result["prizes"] = prize_rows
        return result

    @app.get("/api/admin/raffle/prizes")
    async def api_admin_get_prizes() -> Dict[str, Any]:
        r = await get_redis()
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.post("/api/admin/raffle/prizes")
    async def api_admin_create_prize(body: AdminPrizeRequest) -> Dict[str, Any]:
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
    async def api_admin_delete_prize(prize_id: int) -> Dict[str, Any]:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.srem(key_prizes_set(), prize_id)
        pipe.delete(key_prize_item(prize_id))
        await pipe.execute()
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.get("/api/admin/raffle/winners")
    async def api_admin_winners() -> Dict[str, Any]:
        r = await get_redis()
        raw = await r.lrange(key_raffle_winners(), 0, -1)
        winners = []
        for item in raw:
            try:
                winners.append(json.loads(item))
            except Exception:
                continue
        enriched = []
        for w in winners:
            uid = safe_int(w.get("user_id"))
            enriched.append(
                {
                    **w,
                    "ticket_no": safe_int(w.get("ticket_no") or w.get("ticket")) or None,
                    "user_name": await resolve_winner_name(r, uid),
                }
            )
        return {"ok": True, "items": enriched}

    @app.post("/api/admin/raffle/draw")
    async def api_admin_draw(
        body: AdminDrawRequest,
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
            winners.append(
                {
                    "prize_id": prize.get("id"),
                    "ticket": ticket,
                    "ticket_no": safe_int(ticket),
                    "user_id": uid,
                }
            )

        pipe = r.pipeline()
        pipe.delete(key_raffle_winners())
        if winners:
            pipe.rpush(key_raffle_winners(), *[json.dumps(w) for w in winners])
            for w in winners:
                pipe.rpush(key_user_raffle_wins(int(w.get("user_id"))), json.dumps(w))
        pipe.set(key_raffle_status(), "finished")
        await pipe.execute()

        return {"ok": True, "items": winners, "total_tickets": total_tickets}

    @app.post("/api/admin/raffle/finish_payout")
    async def api_admin_finish_payout() -> Dict[str, Any]:
        r = await get_redis()
        winners = await r.lrange(key_raffle_winners(), 0, -1)

        pipe = r.pipeline()
        if winners:
            pipe.delete(key_last_raffle_winners())
            pipe.rpush(key_last_raffle_winners(), *winners)
        pipe.set(key_raffle_status(), "closed")
        await pipe.execute()

        return {"ok": True, "status": "closed"}

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
    async def api_admin_user_by_nick(body: AdminFindUserRequest) -> Dict[str, Any]:
        r = await get_redis()
        user = await find_user_by_nick(r, body.nickname)
        if not user:
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True, **user}

    @app.post("/api/admin/users/set_points")
    async def api_admin_set_points(body: AdminSetPointsRequest) -> Dict[str, Any]:
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
