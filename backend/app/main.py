from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import Base, engine, get_session
from .deps import get_current_user
from .games import (
    ensure_shop_seeded,
    get_cooldowns,
    leaderboard,
    play_blackjack,
    play_dice,
    play_slots,
)
from .models import GameType, ShopItem, User
from .schemas import (
    AuthRequest,
    BlackjackResult,
    CooldownResponse,
    DiceRequest,
    DiceResponse,
    ErrorResponse,
    LeaderboardResponse,
    ProfileResponse,
    ShopResponse,
    SlotsResponse,
)

settings = get_settings()

app = FastAPI(title="FirstGamble API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(bind=engine) as session:
        await ensure_shop_seeded(session)


@app.post("/auth/telegram", response_model=ProfileResponse, responses={401: {"model": ErrorResponse}})
async def auth_telegram(payload: AuthRequest, session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    if not settings.bot_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BOT_TOKEN is not configured")

    from .telegram import ensure_recent_auth, verify_init_data

    data = verify_init_data(payload.init_data, settings.bot_token)
    auth_date = int(data.get("auth_date", 0))
    ensure_recent_auth(auth_date)
    user_payload = data.get("user") or {}
    tg_id = int(user_payload.get("id"))

    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            tg_id=tg_id,
            username=user_payload.get("username"),
            first_name=user_payload.get("first_name"),
            last_name=user_payload.get("last_name"),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        user.username = user_payload.get("username") or user.username
        user.first_name = user_payload.get("first_name") or user.first_name
        user.last_name = user_payload.get("last_name") or user.last_name
        await session.commit()

    return ProfileResponse(
        tg_id=user.tg_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        points=user.points,
        created_at=user.created_at,
    )


@app.get("/profile", response_model=ProfileResponse)
async def profile(current_user: User = Depends(get_current_user)):
    return ProfileResponse(
        tg_id=current_user.tg_id,
        username=current_user.username,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        points=current_user.points,
        created_at=current_user.created_at,
    )


@app.get("/cooldowns", response_model=CooldownResponse)
async def cooldowns(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    items = await get_cooldowns(session, current_user)
    return CooldownResponse(cooldowns=items)


@app.post("/game/dice", response_model=DiceResponse, responses={429: {"model": ErrorResponse}})
async def game_dice(
    payload: DiceRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await play_dice(session, current_user, payload.dice_count)
    return DiceResponse(**result)


@app.post("/game/blackjack", response_model=BlackjackResult, responses={429: {"model": ErrorResponse}})
async def game_blackjack(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    result = await play_blackjack(session, current_user)
    return BlackjackResult(**result)


@app.post("/game/slots", response_model=SlotsResponse, responses={429: {"model": ErrorResponse}})
async def game_slots(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    result = await play_slots(session, current_user)
    return SlotsResponse(**result)


@app.get("/shop", response_model=ShopResponse)
async def shop(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    await ensure_shop_seeded(session)
    result = await session.execute(select(ShopItem))
    items = result.scalars().all()
    serialized = [
        {"title": item.title, "description": item.description, "price_points": item.price_points}
        for item in items
    ]
    return ShopResponse(balance=current_user.points, items=serialized)


@app.get("/leaderboard", response_model=LeaderboardResponse)
async def leaderboard_endpoint(session: AsyncSession = Depends(get_session), current_user: User = Depends(get_current_user)):
    top, me = await leaderboard(session, current_user)
    return LeaderboardResponse(top=top, me=me)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/games")
async def game_list():
    return {"games": [g.value for g in GameType]}
