import json
import logging
import random
import re
import time
from secrets import token_urlsafe
from typing import Any, Dict, Optional
import aiohttp

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .chat import chat_manager
from .durak_manager import durak_manager

from .models import (
    AddPointRequest,
    AdminDrawRequest,
    AdminEconomyUpdateRequest,
    AdminFindUserRequest,
    AdminLoginRequest,
    AdminPrizeRequest,
    AdminPrizeUpdateRequest,
    AdminPublishPrizesRequest,
    AdminSetPointsRequest,
    AdminGrantResourcesRequest,
    AuthContext,
    BuyRaffleTicketRequest,
    DiceExternalAwardRequest,
    ReportGameRequest,
    RpgBuyRequest,
    RpgAutoRequest,
    RpgConvertRequest,
    RpgGatherRequest,
    UpdateProfileRequest,
)
from .config import (
    ADMIN_PASS,
    ADMIN_SESSION_TTL,
    ADMIN_TG_ID,
    ADMIN_TOKEN,
    ADMIN_USER,
    RAFFLE_TICKET_PRICE,
)
from .redis_utils import (
    ALLOWED_GAMES,
    USERS_SET,
    USERS_ZSET,
    add_points,
    clamp_balance,
    ensure_user,
    get_balance,
    get_redis,
    key_admin_session,
    key_balance,
    key_confirmed,
    key_gamestats,
    key_profile,
    key_stats,
    safe_int,
    sanitize_redis_string,
    find_user_by_game_nick,
)
from .services import (
    RPG_ACCESSORIES,
    RPG_BASE_CD_DEFAULT,
    RPG_CONVERT_RATE_DEFAULT,
    RPG_AUTO_MINERS,
    RPG_BAGS,
    RPG_MAX,
    RPG_CHAIN,
    RPG_SELL_MIN_RESOURCE,
    RPG_RESOURCES,
    RPG_SELL_VALUES,
    RPG_TOOLS,
    get_rpg_economy,
    build_auth_context_from_headers,
    key_rpg_auto,
    key_rpg_cd,
    key_rpg_owned,
    key_rpg_res,
    key_rpg_runs,
    key_prize_counter,
    key_prize_item,
    key_prizes_visible,
    key_prizes_set,
    key_raffle_status,
    key_last_raffle_winners,
    key_raffle_winners,
    key_ticket_counter,
    key_ticket_owners,
    key_user_tickets,
    key_user_raffle_wins,
    rpg_auto_refresh_state,
    rpg_auto_requirements,
    rpg_auto_state_level,
    rpg_calc_buffs,
    rpg_ensure,
    rpg_get_owned,
    rpg_roll_gather,
    rpg_state,
    save_rpg_economy,
    _ensure_profile_identity_fields,
    is_conserve_token,
)


logger = logging.getLogger(__name__)

ADMIN_COOKIE_NAME = "admin_session"
SLOT_WIN_POINTS = 1


async def get_current_auth(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-InitData"),
    x_conserve_auth: Optional[str] = Header(default=None, alias="X-ConServe-Auth"),
) -> AuthContext:
    """Gets the current authentication context.

    This function is used as a dependency in API endpoints to get the
    authentication context of the current user.

    Args:
        request: The incoming request.
        x_telegram_init_data: The Telegram initData string.
        x_conserve_auth: The ConServe authentication header.

    Returns:
        The authentication context.

    Raises:
        HTTPException: If the user is not authenticated or not confirmed.
    """
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


async def require_admin(request: Request) -> str:
    """Requires the user to be an admin.

    This function is used as a dependency in API endpoints to ensure that the
    user is an admin.

    Args:
        request: The incoming request.

    Returns:
        The admin's session token.

    Raises:
        HTTPException: If the user is not an admin.
    """
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="unauthorized")

    r = await get_redis()
    stored = await r.get(key_admin_session(token))
    if not stored:
        raise HTTPException(status_code=401, detail="unauthorized")

    await r.expire(key_admin_session(token), ADMIN_SESSION_TTL)
    return token


async def require_conserve_auth(
    x_conserve_auth: Optional[str] = Header(default=None, alias="X-ConServe-Auth"),
    x_conserve_auth_alt: Optional[str] = Header(default=None, alias="X-Conserve-Auth"),
):
    """Requires a valid ConServe authentication token.

    This function is used as a dependency in API endpoints to ensure that the
    request is coming from a trusted source.

    Args:
        x_conserve_auth: The ConServe authentication token.
        x_conserve_auth_alt: An alternative ConServe authentication token.

    Returns:
        The ConServe authentication token.

    Raises:
        HTTPException: If the token is invalid.
    """
    token = x_conserve_auth or x_conserve_auth_alt
    if not is_conserve_token(token):
        raise HTTPException(status_code=401, detail="invalid conserve token")
    return token


def register_routes(app: FastAPI):
    """Registers the API routes.

    Args:
        app: The FastAPI application.
    """
    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket, token: str = ""):
        # Simple token check? User didn't specify strict auth for chat,
        # but we need user info for sender name.
        # We can extract name from query param 'name' for simplicity
        # or reuse AuthContext if we can parse it.
        # WebSocket headers are hard to customize in JS cleanly (protocol arg used usually).
        # Let's rely on query param ?name=...&uid=...
        # Security: In prod, validate via hash. For this task, trust query params (guarded by webapp logic)

        name = websocket.query_params.get("name", "Anon")

        await chat_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Rate limit or length check could go here
                if len(data) > 500: continue

                filtered = chat_manager.filter_message(data)
                if filtered:
                    await chat_manager.broadcast(filtered, name)
        except WebSocketDisconnect:
            chat_manager.disconnect(websocket)

    @app.websocket("/ws/durak/{room_id}")
    async def ws_durak(websocket: WebSocket, room_id: str):
        uid_str = websocket.query_params.get("uid")
        if not uid_str:
            await websocket.close()
            return
        uid = safe_int(uid_str)

        await durak_manager.connect_auth(websocket, room_id, uid)
        try:
            while True:
                data = await websocket.receive_json()
                await durak_manager.handle_message(room_id, uid, data)
        except WebSocketDisconnect:
            durak_manager.disconnect(websocket, room_id, uid)

    @app.get("/api/durak/rooms")
    async def api_durak_rooms(auth: AuthContext = Depends(get_current_auth)):
        # List active rooms
        # Return summary: id, name, players/max, settings
        active_rooms = []
        for rid, game in durak_manager.rooms.items():
            if game.state == "waiting":
                active_rooms.append({
                    "id": rid,
                    "players": len(game.players),
                    "max": 4, # Hardcoded max 4
                    "settings": game.settings,
                    # Name of creator or room name?
                    # "creator": game.players[0].name if game.players else "Unknown"
                })
        return {"ok": True, "rooms": active_rooms}

    @app.post("/api/durak/create")
    async def api_durak_create(
        request: Request,
        auth: AuthContext = Depends(get_current_auth)
    ):
        body = await request.json()
        settings = {
            "size": safe_int(body.get("size"), 36),
            "mode": body.get("mode", "podkidnoy")
        }
        name = auth.username or "Player"

        room_id = await durak_manager.create_room(auth.user_id, name, settings)
        if not room_id:
             return {"ok": False, "error": "Not enough points (need 30)"}

        return {"ok": True, "room_id": room_id}

    @app.post("/api/durak/join")
    async def api_durak_join(
        request: Request,
        auth: AuthContext = Depends(get_current_auth)
    ):
        body = await request.json()
        room_id = body.get("room_id")
        name = auth.username or "Player"

        success = await durak_manager.join_room(auth.user_id, name, room_id)
        if not success:
             return {"ok": False, "error": "Cannot join (full, started, or no points)"}

        return {"ok": True, "room_id": room_id}


    async def rebuild_ticket_owners(r) -> Dict[str, int]:
        """Rebuilds the ticket owners mapping.

        Args:
            r: The Redis connection.

        Returns:
            A dictionary mapping ticket numbers to user IDs.
        """
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
        """Gets the ticket owners mapping.

        Args:
            r: The Redis connection.

        Returns:
            A dictionary mapping ticket numbers to user IDs.
        """
        owners = await r.hgetall(key_ticket_owners())
        if owners:
            return {k: safe_int(v) for k, v in owners.items()}
        return await rebuild_ticket_owners(r)

    async def get_prizes(r):
        """Gets the list of raffle prizes.

        Args:
            r: The Redis connection.

        Returns:
            A list of prize dictionaries.
        """
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
        """Gets the current status of the raffle.

        Args:
            r: The Redis connection.

        Returns:
            The current status of the raffle.
        """
        status = await r.get(key_raffle_status())
        return (status or "preparing").lower()

    def normalize_nickname(name: str) -> str:
        """Normalizes a nickname.

        Args:
            name: The nickname to normalize.

        Returns:
            The normalized nickname.
        """
        return (name or "").strip().lower()

    async def find_user_by_nick(
        r, nickname: str, skip_user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Finds a user by their nickname.

        Args:
            r: The Redis connection.
            nickname: The nickname to search for.
            skip_user_id: A user ID to skip in the search.

        Returns:
            A dictionary containing the user's data if found, otherwise None.
        """
        target = normalize_nickname(nickname)
        if not target:
            return None
        user_ids = await r.smembers(USERS_SET)
        for uid_raw in user_ids:
            uid = safe_int(uid_raw)
            if uid <= 0:
                continue
            if skip_user_id and uid == skip_user_id:
                continue
            profile = await r.hgetall(key_profile(uid))
            if normalize_nickname(profile.get("name")) == target:
                bal = await get_balance(uid)
                return {"user_id": uid, "profile": profile, "balance": bal}
        return None

    async def resolve_winner_name(r, uid: Optional[int]) -> str:
        """Resolves the name of a raffle winner.

        Args:
            r: The Redis connection.
            uid: The user ID of the winner.

        Returns:
            The winner's name.
        """
        if not uid:
            return ""
        profile = await r.hgetall(key_profile(uid))
        if profile.get("username"):
            return f"@{profile.get('username')}"
        return profile.get("name") or f"user {uid}"

    @app.get("/api/ping")
    async def api_ping() -> Dict[str, Any]:
        """A simple ping endpoint to check if the API is running."""
        return {"ok": True, "message": "pong"}

    @app.post("/api/admin/login")
    async def api_admin_login(
        body: AdminLoginRequest,
        response: Response,
        request: Request
    ) -> Dict[str, Any]:
        """Logs in an admin.

        Args:
            body: The request body, containing the admin's credentials.
            response: The response object.
            request: The incoming request.

        Returns:
            A dictionary indicating whether the login was successful.
        """
        r = await get_redis()

        logger.info(f"Admin Login attempt: user='{body.username}' (expected '{ADMIN_USER}'), pass='***' (match={body.password == ADMIN_PASS})")

        if body.username != ADMIN_USER or body.password != ADMIN_PASS:
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")

        token = ADMIN_TOKEN or token_urlsafe(32)
        await r.set(key_admin_session(token), ADMIN_USER, ex=ADMIN_SESSION_TTL)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            secure=True,
        )
        return {"ok": True}

    @app.get("/api/balance")
    async def api_balance(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        """Gets the current user's balance."""
        bal = await get_balance(auth.user_id)
        return {"ok": True, "balance": bal}

    @app.get("/api/profile")
    async def api_profile(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        """Gets the current user's profile."""
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
            "nick_name": profile.get("Nick_Name") or "",
        }

    @app.post("/api/add_point")
    async def api_add_point(
        body: AddPointRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Adds a point to the current user's balance."""
        game = (body.game or "").strip().lower()
        if game not in ALLOWED_GAMES:
            return {"ok": False, "error": "bad game"}

        delta = body.delta or 1
        if delta <= 0:
            delta = 1
        if game == "slot":
            delta = SLOT_WIN_POINTS

        await ensure_user(auth.user_id)
        new_balance = await add_points(auth.user_id, delta, game)

        logger.info(
            "add_point: user=%s game=%s delta=%s new_balance=%s",
            auth.user_id,
            game,
            delta,
            new_balance,
        )

        return {"ok": True, "balance": new_balance}

    @app.post("/api/dice/award", include_in_schema=True)
    async def api_dice_external_award(
        body: DiceExternalAwardRequest,
        _conserve_token: str = Depends(require_conserve_auth),
    ) -> Dict[str, Any]:
        """Awards points for an external dice game.

        This endpoint is used to award points to a user for a dice game that is
        played outside of the main application.

        Args:
            body: The request body, containing the user's nickname and the sum of
                the dice roll.
            _conserve_token: The ConServe authentication token.

        Returns:
            A dictionary containing the result of the award.
        """
        # Внешний запрос не обязан передавать количество кубиков: используем
        # фиксированное значение для проверки корректности суммы.
        dice_count = 2
        dice_sum = safe_int(body.dice_sum)

        min_sum = dice_count
        max_sum = dice_count * 6
        if dice_sum < min_sum or dice_sum > max_sum:
            raise HTTPException(status_code=400, detail="dice_sum out of range")

        uid = None
        if body.Nick_Name:
            uid = await find_user_by_game_nick(body.Nick_Name)
        if not uid:
            raise HTTPException(status_code=404, detail="Nick_Name is not linked")

        await ensure_user(uid)
        new_balance = await add_points(uid, dice_sum, "dice")

        logger.info(
            "dice external award: nick=%s user=%s dice_sum=%s dice_count=%s balance=%s",
            body.Nick_Name,
            uid,
            dice_sum,
            dice_count,
            new_balance,
        )

        return {
            "ok": True,
            "user_id": uid,
            "nick_name": body.Nick_Name,
            "dice_sum": dice_sum,
            "added_points": dice_sum,
            "balance": new_balance,
        }

    @app.post("/api/report_game")
    async def api_report_game(
        body: ReportGameRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Reports the result of a game."""
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
        """Gets the current user's stats."""
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
        """Updates the current user's profile."""
        if not auth.from_telegram:
            raise HTTPException(status_code=403, detail="webapp only")

        await ensure_user(auth.user_id)

        r = await get_redis()
        existing_profile = await r.hgetall(key_profile(auth.user_id))

        name = (body.name if body.name is not None else existing_profile.get("name") or "").strip()
        username = (body.username if body.username is not None else existing_profile.get("username") or "").strip()
        nick_name_raw = body.Nick_Name if body.Nick_Name is not None else existing_profile.get("Nick_Name")
        nick_name = (nick_name_raw or "").strip()

        if not name:
            logger.info("update_profile rejected: empty name user=%s", auth.user_id)
            return {"ok": False, "error": "Nickname cannot be empty"}

        if not re.match(r"^[A-Za-z0-9_-]{3,20}$", name):
            logger.info("update_profile rejected: invalid format user=%s", auth.user_id)
            return {
                "ok": False,
                "error": "Nickname must be 3-20 chars: letters, digits, _ or -",
            }

        if nick_name and not re.match(r"^[A-Za-z0-9_]{3,24}$", nick_name):
            logger.info("update_profile rejected: invalid game nick user=%s", auth.user_id)
            return {
                "ok": False,
                "error": "Nick_Name может содержать 3-24 латинских символа, цифры и подчёркивания",
            }

        existing_owner = await find_user_by_nick(r, name, skip_user_id=auth.user_id)
        if existing_owner:
            logger.info(
                "update_profile rejected: nickname taken user=%s requested=%s owner=%s",
                auth.user_id,
                name,
                existing_owner.get("user_id"),
            )
            return {"ok": False, "error": "Этот ник уже занят"}

        name_clean = sanitize_redis_string(name)
        username_clean = sanitize_redis_string(username)

        mapping = {"name": name_clean, "username": username_clean}
        if nick_name:
            mapping["Nick_Name"] = sanitize_redis_string(nick_name)
        await r.hset(key_profile(auth.user_id), mapping=mapping)
        logger.info(
            "update_profile saved: user=%s name=%s username=%s nick_name=%s",
            auth.user_id,
            name,
            username,
            nick_name,
        )
        return {"ok": True, "nick_name": nick_name}

    @app.get("/api/leaderboard")
    async def api_leaderboard(
        game: str = "all",
        sort: str = "points",
        limit: int = 100,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Gets the leaderboard."""
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

            name = profile.get("name", "")
            if not name:
                continue

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
                    "name": name,
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
        """Gets the positions of all users on the leaderboard."""
        r = await get_redis()

        raw = await r.zrevrange(USERS_ZSET, 0, -1, withscores=True)
        positions = {str(uid): pos + 1 for pos, (uid, _) in enumerate(raw)}
        return {"ok": True, "positions": positions}

    @app.get("/api/leaderboard/extended")
    async def api_leaderboard_extended(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        """Gets an extended leaderboard with user profiles."""
        r = await get_redis()

        raw = await r.zrevrange(USERS_ZSET, 0, -1, withscores=True)
        items = []
        for pos, (uid, score) in enumerate(raw, start=1):
            user_data = await r.hgetall(key_profile(int(uid)))
            items.append({"user_id": str(uid), "pos": pos, "score": int(score), "profile": user_data})
        return {"ok": True, "items": items}

    @app.get("/api/rpg/state")
    async def api_rpg_state(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        """Gets the current user's RPG state."""
        uid = auth.user_id
        st = await rpg_state(uid)
        return {"ok": True, "state": st}

    @app.post("/api/rpg/gather")
    async def api_rpg_gather(
        body: RpgGatherRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Gathers resources in the RPG."""
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
        cd_mult, yield_add, cap_add, extra_drops, _convert_bonus = rpg_calc_buffs(owned)

        gained = rpg_roll_gather(extra_drops)
        for k in gained:
            gained[k] = int(round(gained[k] * (1.0 + yield_add)))

        cur = await r.hgetall(key_rpg_res(uid))
        cur_int = {k: safe_int(v) for k, v in cur.items()}

        pipe = r.pipeline()
        for res_name in RPG_RESOURCES:
            max_cap = RPG_MAX + int(cap_add.get(res_name, 0))
            new_val = min(max_cap, cur_int.get(res_name, 0) + gained.get(res_name, 0))
            pipe.hset(key_rpg_res(uid), res_name, new_val)

        economy = await get_rpg_economy(r)
        base_cd = economy.get("base_cd", RPG_BASE_CD_DEFAULT)
        pipe.set(key_rpg_cd(uid), now + int(base_cd * cd_mult))
        pipe.incr(key_rpg_runs(uid), 1)
        await pipe.execute()

        st = await rpg_state(uid)
        return {"ok": True, "gained": gained, "state": st}

    @app.post("/api/rpg/buy")
    async def api_rpg_buy(
        body: RpgBuyRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Buys an item in the RPG."""
        uid = auth.user_id
        cat = (body.category or "").lower()
        item_id = (body.item_id or "").lower()

        if not cat or not item_id:
            return {"ok": False, "error": "bad data"}

        r = await get_redis()
        await ensure_user(uid)
        await rpg_ensure(uid)

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
        cost_resource = item.get("cost_resource")
        if cost_resource:
            if cost_resource not in RPG_RESOURCES:
                return {"ok": False, "error": "bad item"}

            res_raw = await r.hgetall(key_rpg_res(uid))
            res_int = {k: safe_int(v) for k, v in res_raw.items()}
            if res_int.get(cost_resource, 0) < cost:
                return {"ok": False, "error": "not enough resources"}

            pipe = r.pipeline()
            pipe.hincrby(key_rpg_res(uid), cost_resource, -cost)
            pipe.sadd(owned_key, item_id)
            await pipe.execute()
        else:
            bal = await get_balance(uid)
            if bal < cost:
                return {"ok": False, "error": "not enough points"}

            pipe = r.pipeline()
            pipe.incrby(key_balance(uid), -cost)
            pipe.zadd(USERS_ZSET, {uid: clamp_balance(bal - cost)})
            pipe.sadd(owned_key, item_id)
            await pipe.execute()

        st = await rpg_state(uid)
        return {"ok": True, "state": st}

    @app.post("/api/rpg/convert")
    async def api_rpg_convert(
        body: RpgConvertRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Converts resources in the RPG."""
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
        owned = await rpg_get_owned(uid)
        _cd_mult, _yield_add, _cap_add, _extra_drops, convert_bonus = rpg_calc_buffs(owned)
        economy = await get_rpg_economy(r)

        if to_r == "points":
            if from_r not in RPG_RESOURCES:
                return {"ok": False, "error": "bad from"}
            min_sell_idx = RPG_RESOURCES.index(RPG_SELL_MIN_RESOURCE)
            from_idx = RPG_RESOURCES.index(from_r)
            if from_idx < min_sell_idx:
                return {"ok": False, "error": "sell restricted"}
            need = amount
            if res_int.get(from_r, 0) < need:
                return {"ok": False, "error": "not enough resources"}
            value = RPG_SELL_VALUES.get(from_r, 1) * amount

            balance_now = await get_balance(uid)
            new_balance = clamp_balance(balance_now + value)

            pipe = r.pipeline()
            pipe.hincrby(key_rpg_res(uid), from_r, -need)
            pipe.set(key_balance(uid), new_balance)
            pipe.zadd(USERS_ZSET, {uid: new_balance})
            await pipe.execute()

            logger.info(
                f"Игрок с id {uid} получил {value} очков в игре rpg_convert "
                f"(новый баланс: {new_balance})"
            )

            st = await rpg_state(uid)
            return {"ok": True, "state": st}

        pair_ok = any(from_r == a and to_r == b for a, b in RPG_CHAIN)
        if not pair_ok:
            return {"ok": False, "error": "bad convert pair"}

        rate = economy.get("convert_rate", RPG_CONVERT_RATE_DEFAULT)
        need = amount * rate
        if res_int.get(from_r, 0) < need:
            return {"ok": False, "error": "not enough resources"}

        bonus_gain = max(0, int(amount * convert_bonus))
        final_gain = amount + bonus_gain

        pipe = r.pipeline()
        pipe.hincrby(key_rpg_res(uid), from_r, -need)
        pipe.hincrby(key_rpg_res(uid), to_r, final_gain)
        await pipe.execute()

        st = await rpg_state(uid)
        return {"ok": True, "state": st}

    @app.post("/api/rpg/auto")
    async def api_rpg_auto(
        body: RpgAutoRequest,
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Manages auto-miners in the RPG."""
        uid = auth.user_id
        action = (body.action or "").lower()
        miner_id = (body.miner_id or "").lower()

        cfg = next((m for m in RPG_AUTO_MINERS if m.get("id") == miner_id), None)
        if not action or not cfg:
            return {"ok": False, "error": "bad data"}

        r = await get_redis()
        await rpg_ensure(uid)
        owned = await rpg_get_owned(uid)
        _cd_mult, _yield_add, cap_add, _extra_drops, _convert_bonus = rpg_calc_buffs(owned)
        res_raw = await r.hgetall(key_rpg_res(uid))
        res_int = {k: safe_int(v) for k, v in res_raw.items()}

        raw_state = await r.hget(key_rpg_auto(uid), miner_id)
        state: Dict[str, Any] = {}
        if raw_state:
            try:
                state = json.loads(raw_state)
            except Exception:
                state = {}

        now = int(time.time())
        state, inv_cap, inv_amt = rpg_auto_refresh_state(state, now)

        levels = cfg.get("levels", []) or []
        max_level = len(levels)
        level = rpg_auto_state_level(state, max_level)
        missing_res, has_bag, next_cfg = rpg_auto_requirements(cfg, res_int, owned, level)
        storage_full = inv_amt >= inv_cap > 0

        if action == "upgrade":
            if not next_cfg:
                return {"ok": False, "error": "max_level"}
            if missing_res:
                return {"ok": False, "error": "requirements", "missing": missing_res}

            pipe = r.pipeline()
            for res_name, need in (next_cfg.get("cost") or {}).items():
                pipe.hincrby(key_rpg_res(uid), res_name, -int(need))
            state["level"] = level + 1
            state["active"] = bool(state.get("active"))
            state["last"] = int(time.time())
            pipe.hset(key_rpg_auto(uid), miner_id, json.dumps(state))
            await pipe.execute()
        elif action == "start":
            if level <= 0:
                return {"ok": False, "error": "upgrade_required"}
            if not has_bag:
                return {"ok": False, "error": "bag_required", "bag_req": cfg.get("bag_req")}
            if storage_full:
                return {"ok": False, "error": "storage_full"}

            state["active"] = True
            state["level"] = level
            state["last"] = now
            await r.hset(key_rpg_auto(uid), miner_id, json.dumps(state))
        elif action == "stop":
            state["active"] = False
            state["level"] = level
            state["last"] = now
            await r.hset(key_rpg_auto(uid), miner_id, json.dumps(state))
        elif action == "collect":
            res_name = cfg.get("resource")
            cap = RPG_MAX + int(cap_add.get(res_name, 0))
            cur_val = res_int.get(res_name, 0)
            free_space = max(0, cap - cur_val)
            transfer = min(inv_amt, free_space)
            if transfer <= 0:
                return {"ok": False, "error": "no_space"}

            pipe = r.pipeline()
            pipe.hincrby(key_rpg_res(uid), res_name, transfer)
            state["inv"] = max(0, inv_amt - transfer)
            state["last"] = now
            pipe.hset(key_rpg_auto(uid), miner_id, json.dumps(state))
            await pipe.execute()
        else:
            return {"ok": False, "error": "bad action"}

        st = await rpg_state(uid)
        return {"ok": True, "state": st}

    @app.post("/api/raffle/buy_ticket")
    async def api_raffle_buy_ticket(
        body: BuyRaffleTicketRequest = Body(default_factory=BuyRaffleTicketRequest),
        auth: AuthContext = Depends(get_current_auth),
    ) -> Dict[str, Any]:
        """Buys a raffle ticket."""
        uid = auth.user_id

        try:
            r = await get_redis()
            await ensure_user(uid)

            count = max(1, min(body.count or 1, 100))

            balance = await get_balance(uid)
            total_cost = RAFFLE_TICKET_PRICE * count

            if balance < total_cost:
                return {"ok": False, "error": "not_enough_points", "balance": balance}

            last_ticket = await r.incrby(key_ticket_counter(), count)
            first_ticket = last_ticket - count + 1
            bought_numbers = list(range(first_ticket, last_ticket + 1))

            new_balance = clamp_balance(balance - total_cost)
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
        """Gets the current user's cabinet data."""
        uid = auth.user_id
        r = await get_redis()
        await ensure_user(uid)

        bal = await get_balance(uid)
        tickets = await r.lrange(key_user_tickets(uid), 0, -1)

        return {
            "ok": True,
            "user_id": str(uid),
            "balance": bal,
            "tickets": tickets,
        }

    @app.get("/api/raffle/state")
    async def api_raffle_state(auth: AuthContext = Depends(get_current_auth)) -> Dict[str, Any]:
        """Gets the current state of the raffle."""
        r = await get_redis()
        status = await get_raffle_status(r)

        prizes_visible = bool(safe_int(await r.get(key_prizes_visible()), 0))

        result = {"ok": True, "status": status, "prizes": [], "prizes_visible": prizes_visible}
        
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

        if status == "active" and not prizes_visible:
            # Призы скрыты до публикации админом
            return result

        prize_rows = []
        for prize in prizes:
            pid = prize.get("id")
            winner = winners_by_prize.get(pid) if status == "finished" else None
            ticket_no = None
            winner_name = None
            if winner:
                ticket_no = safe_int(winner.get("ticket_no") or winner.get("ticket")) or None
                winner_name = await resolve_winner_name(r, safe_int(winner.get("user_id"))) or None

            if status == "finished" and not winner:
                # Приз не был разыгран (например, участников меньше чем призов)
                # — не показываем его в публичном списке итогов.
                continue

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
    async def api_admin_get_prizes(admin_token: str = Depends(require_admin)) -> Dict[str, Any]:
        """Gets the list of raffle prizes."""
        r = await get_redis()
        prizes = await get_prizes(r)
        visible = bool(safe_int(await r.get(key_prizes_visible()), 0))
        return {"ok": True, "items": prizes, "prizes_visible": visible}

    @app.post("/api/admin/raffle/prizes")
    async def api_admin_create_prize(
        body: AdminPrizeRequest, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Creates a new raffle prize."""
        r = await get_redis()
        prizes = await get_prizes(r)
        prizes_count = len(prizes)
        if prizes_count == 0:
            await r.delete(key_prize_counter())
        pid = await r.incr(key_prize_counter())
        next_order = max([p.get("order", 0) for p in prizes], default=0) + 1
        data = {
            "name": sanitize_redis_string(body.name),
            "description": "",
            "order": next_order,
        }
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
        admin_token: str = Depends(require_admin),
    ) -> Dict[str, Any]:
        """Updates a raffle prize."""
        r = await get_redis()
        exists = await r.sismember(key_prizes_set(), prize_id)
        if not exists:
            raise HTTPException(status_code=404, detail="prize not found")
        updates: Dict[str, Any] = {}
        if body.name is not None:
            updates["name"] = sanitize_redis_string(body.name)
        if updates:
            await r.hset(key_prize_item(prize_id), mapping=updates)
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.delete("/api/admin/raffle/prizes/{prize_id}")
    async def api_admin_delete_prize(
        prize_id: int, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Deletes a raffle prize."""
        r = await get_redis()
        pipe = r.pipeline()
        pipe.srem(key_prizes_set(), prize_id)
        pipe.delete(key_prize_item(prize_id))
        await pipe.execute()
        prizes = await get_prizes(r)
        return {"ok": True, "items": prizes}

    @app.post("/api/admin/raffle/publish_prizes")
    async def api_admin_publish_prizes(
        body: AdminPublishPrizesRequest, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Publishes or unpublishes the raffle prizes."""
        r = await get_redis()
        flag = "1" if body.visible else "0"
        await r.set(key_prizes_visible(), flag)
        return {"ok": True, "visible": body.visible}

    @app.get("/api/admin/raffle/winners")
    async def api_admin_winners(admin_token: str = Depends(require_admin)) -> Dict[str, Any]:
        """Gets the list of raffle winners."""
        r = await get_redis()
        status = await get_raffle_status(r)
        if status == "closed":
            return {"ok": True, "items": [], "status": status}

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
            profile = await r.hgetall(key_profile(uid)) if uid else {}
            enriched.append(
                {
                    **w,
                    "ticket_no": safe_int(w.get("ticket_no") or w.get("ticket")) or None,
                    "user_name": await resolve_winner_name(r, uid),
                    "winner_username": profile.get("username") or None,
                }
            )
        return {"ok": True, "items": enriched, "status": status}

    @app.post("/api/admin/raffle/draw")
    async def api_admin_draw(
        body: AdminDrawRequest,
        admin_token: str = Depends(require_admin),
    ) -> Dict[str, Any]:
        """Draws the raffle winners."""
        r = await get_redis()
        prizes = await get_prizes(r)
        if not prizes:
            return JSONResponse({"ok": False, "error": "no_prizes"}, status_code=400)
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
                    "prize_order": prize.get("order") or idx + 1,
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
    async def api_admin_finish_payout(admin_token: str = Depends(require_admin)) -> Dict[str, Any]:
        """Finishes the raffle payout and resets the raffle state."""
        r = await get_redis()
        winners = await r.lrange(key_raffle_winners(), 0, -1)
        owners = await r.hgetall(key_ticket_owners())

        affected_users = {safe_int(uid) for uid in owners.values() if safe_int(uid) > 0}

        pipe = r.pipeline()
        if winners:
            pipe.delete(key_last_raffle_winners())
            pipe.rpush(key_last_raffle_winners(), *winners)
            pipe.delete(key_raffle_winners())
        for uid in affected_users:
            pipe.delete(key_user_tickets(uid))
        pipe.delete(key_ticket_owners())
        pipe.delete(key_ticket_counter())
        pipe.set(key_raffle_status(), "closed")
        pipe.set(key_prizes_visible(), "0")
        await pipe.execute()

        logger.info(
            "raffle finish payout: cleared active winners and tickets, status closed, users=%s",
            len(affected_users),
        )

        return {"ok": True, "status": "closed"}

    @app.post("/api/admin/users/by_nickname")
    async def api_admin_user_by_nick(
        body: AdminFindUserRequest, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Finds a user by their nickname."""
        r = await get_redis()
        user = await find_user_by_nick(r, body.nickname)
        if not user:
            logger.info("admin find user: nickname=%s not found", body.nickname)
            return {"ok": False, "error": "User not found"}
        logger.info(
            "admin find user: nickname=%s user_id=%s balance=%s",
            body.nickname,
            user.get("user_id"),
            user.get("balance"),
        )
        return {"ok": True, **user}

    @app.post("/api/admin/users/set_points")
    async def api_admin_set_points(
        body: AdminSetPointsRequest, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Sets a user's points."""
        r = await get_redis()
        uid = body.user_id
        if (not uid or uid <= 0) and body.nickname:
            user = await find_user_by_nick(r, body.nickname)
            if user:
                uid = user.get("user_id")
        if not uid or uid <= 0:
            raise HTTPException(status_code=400, detail="user_id required")

        await ensure_user(uid)
        cur_balance = await get_balance(uid)

        if body.new_balance is not None:
            new_balance = clamp_balance(int(body.new_balance))
        elif body.points_delta is not None:
            new_balance = clamp_balance(cur_balance + int(body.points_delta))
        else:
            raise HTTPException(status_code=400, detail="no changes provided")

        pipe = r.pipeline()
        pipe.set(key_balance(uid), new_balance)
        pipe.zadd(USERS_ZSET, {uid: new_balance})
        await pipe.execute()

        profile = await r.hgetall(key_profile(uid))
        logger.info(
            f"Админ изменил баланс игрока с id {uid}: delta={new_balance - cur_balance}, "
            f"новый баланс: {new_balance}"
        )
        return {
            "ok": True,
            "user_id": uid,
            "balance": new_balance,
            "profile": profile,
        }

    @app.post("/api/admin/rpg/grant_resources")
    async def api_admin_grant_resources(
        body: AdminGrantResourcesRequest, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Grants RPG resources to a user."""
        r = await get_redis()
        uid = body.user_id
        if (not uid or uid <= 0) and body.nickname:
            user = await find_user_by_nick(r, body.nickname)
            if user:
                uid = user.get("user_id")

        if not uid or uid <= 0:
            raise HTTPException(status_code=400, detail="user_id required")

        res_name = (body.resource or "").lower()
        if res_name not in RPG_RESOURCES:
            raise HTTPException(status_code=400, detail="bad resource")

        amount = safe_int(body.amount)
        if amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive")

        await ensure_user(uid)
        await rpg_ensure(uid)

        pipe = r.pipeline()
        pipe.hincrby(key_rpg_res(uid), res_name, amount)
        await pipe.execute()

        res_raw = await r.hgetall(key_rpg_res(uid))
        res_int = {k: safe_int(v) for k, v in res_raw.items()}

        logger.info(
            "admin grant resource: user_id=%s resource=%s amount=%s", uid, res_name, amount
        )

        return {"ok": True, "user_id": uid, "resource": res_name, "amount": amount, "resources": res_int}

    @app.get("/api/admin/rpg/economy")
    async def api_admin_get_economy(
        admin_token: str = Depends(require_admin),
    ) -> Dict[str, Any]:
        """Gets the RPG economy settings."""
        economy = await get_rpg_economy()
        return {"ok": True, "economy": economy}

    @app.post("/api/admin/rpg/economy")
    async def api_admin_update_economy(
        body: AdminEconomyUpdateRequest, admin_token: str = Depends(require_admin)
    ) -> Dict[str, Any]:
        """Updates the RPG economy settings."""
        payload: Dict[str, Any] = {}
        if body.convert_rate is not None:
            payload["convert_rate"] = body.convert_rate
        if body.base_cd is not None:
            payload["base_cd"] = body.base_cd
        if not payload:
            raise HTTPException(status_code=400, detail="no changes provided")

        economy = await save_rpg_economy(payload)
        logger.info("admin update rpg economy: %s", payload)
        return {"ok": True, "economy": economy}

    @app.get("/api/check_region")
    async def api_check_region(request: Request) -> Dict[str, Any]:
        """Checks the user's region based on IP."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else ""

        # Localhost or empty
        if not ip or ip in ("127.0.0.1", "::1", "localhost"):
            return {"ok": True, "countryCode": "RU"}

        try:
            timeout = aiohttp.ClientTimeout(total=3.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"http://ipwho.is/{ip}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {"ok": True, "countryCode": data.get("country_code", "RU")}
        except Exception:
            # Fallback to RU on error to avoid blocking valid users
            pass

        return {"ok": True, "countryCode": "RU"}

    exposed_paths = {"/api/dice/award", "/api/check_region"}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in exposed_paths:
            route.include_in_schema = False

    return app
