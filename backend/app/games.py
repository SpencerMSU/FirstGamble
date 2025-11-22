import random
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Cooldown, GameResult, GameType, Outcome, ShopItem, User

COOLDOWN_SECONDS = 5 * 60


async def ensure_shop_seeded(session: AsyncSession) -> None:
    result = await session.execute(select(func.count(ShopItem.id)))
    count = result.scalar_one()
    if count == 0:
        session.add_all(
            [
                ShopItem(title="Товар 1", description="Тестовый предмет для магазина", price_points=5),
                ShopItem(title="Товар 2", description="Второй тестовый предмет", price_points=9),
            ]
        )
        await session.commit()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enforce_cooldown(session: AsyncSession, user: User, game_type: GameType) -> int:
    result = await session.execute(
        select(Cooldown).where(Cooldown.user_id == user.id, Cooldown.game_type == game_type)
    )
    cooldown = result.scalar_one_or_none()
    current_time = _now()

    if cooldown:
        delta = current_time - cooldown.last_played_at
        remaining = COOLDOWN_SECONDS - int(delta.total_seconds())
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"message": "Кулдаун ещё не закончился", "remaining_seconds": remaining},
            )
        cooldown.last_played_at = current_time
    else:
        cooldown = Cooldown(user_id=user.id, game_type=game_type, last_played_at=current_time)
        session.add(cooldown)

    return 0


async def update_points_and_log(
    session: AsyncSession, user: User, game_type: GameType, outcome: Outcome, payload: dict, points_awarded: int
) -> None:
    if outcome == Outcome.win and points_awarded:
        user.points += points_awarded

    session.add(
        GameResult(
            user_id=user.id,
            game_type=game_type,
            outcome=outcome,
            payload=payload,
            created_at=_now(),
        )
    )
    await session.commit()
    await session.refresh(user)


def roll_dice(count: int) -> list[int]:
    return [random.randint(1, 6) for _ in range(count)]


async def play_dice(session: AsyncSession, user: User, dice_count: int) -> dict:
    await enforce_cooldown(session, user, GameType.dice)

    player_rolls = roll_dice(dice_count)
    robot_rolls = roll_dice(dice_count)
    player_total = sum(player_rolls)
    robot_total = sum(robot_rolls)

    if player_total > robot_total:
        outcome = Outcome.win
    elif player_total < robot_total:
        outcome = Outcome.lose
    else:
        outcome = Outcome.draw

    points_awarded = 1 if outcome == Outcome.win else 0
    payload = {
        "player": player_rolls,
        "robot": robot_rolls,
        "player_total": player_total,
        "robot_total": robot_total,
    }
    await update_points_and_log(session, user, GameType.dice, outcome, payload, points_awarded)
    return {
        "player": {"values": player_rolls, "total": player_total},
        "robot": {"values": robot_rolls, "total": robot_total},
        "outcome": outcome,
        "points_awarded": points_awarded,
    }


SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def build_deck() -> list[str]:
    deck = [f"{rank}{suit}" for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def card_value(rank: str) -> int:
    if rank in {"J", "Q", "K"}:
        return 10
    if rank == "A":
        return 11
    return int(rank)


def hand_score(hand: list[str]) -> int:
    score = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        score += card_value(rank)
        if rank == "A":
            aces += 1
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score


async def play_blackjack(session: AsyncSession, user: User) -> dict:
    await enforce_cooldown(session, user, GameType.blackjack)

    deck = build_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    # Простая стратегия игрока: тянуть карты до 16
    while hand_score(player_hand) < 16:
        player_hand.append(deck.pop())

    while hand_score(dealer_hand) < 17:
        dealer_hand.append(deck.pop())

    player_score = hand_score(player_hand)
    dealer_score = hand_score(dealer_hand)

    if player_score > 21:
        outcome = Outcome.lose
    elif dealer_score > 21:
        outcome = Outcome.win
    elif dealer_score >= player_score:
        outcome = Outcome.lose
    else:
        outcome = Outcome.win

    points_awarded = 1 if outcome == Outcome.win else 0
    payload = {
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "player_score": player_score,
        "dealer_score": dealer_score,
    }
    await update_points_and_log(session, user, GameType.blackjack, outcome, payload, points_awarded)

    return {
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "player_score": player_score,
        "dealer_score": dealer_score,
        "outcome": outcome,
        "points_awarded": points_awarded,
    }


SYMBOLS = ["🍒", "🍋", "🔔", "⭐", "7️⃣"]


async def play_slots(session: AsyncSession, user: User) -> dict:
    await enforce_cooldown(session, user, GameType.slots)
    reels = [random.choice(SYMBOLS) for _ in range(3)]
    outcome = Outcome.win if len(set(reels)) == 1 else Outcome.lose
    points_awarded = 1 if outcome == Outcome.win else 0

    payload = {"reels": reels}
    await update_points_and_log(session, user, GameType.slots, outcome, payload, points_awarded)
    return {"reels": reels, "outcome": outcome, "points_awarded": points_awarded}


async def get_cooldowns(session: AsyncSession, user: User) -> list[dict]:
    result = await session.execute(select(Cooldown).where(Cooldown.user_id == user.id))
    cooldowns = result.scalars().all()
    current_time = _now()
    items: list[dict] = []
    for cd in cooldowns:
        delta = current_time - cd.last_played_at
        remaining = max(0, COOLDOWN_SECONDS - int(delta.total_seconds()))
        items.append({"game_type": cd.game_type, "remaining_seconds": remaining})
    return items


async def leaderboard(session: AsyncSession, user: User | None = None) -> tuple[list[dict], dict | None]:
    result = await session.execute(select(User).order_by(User.points.desc(), User.id).limit(20))
    top_users = result.scalars().all()
    top = [
        {
            "tg_id": u.tg_id,
            "username": u.username,
            "points": u.points,
            "rank": idx + 1,
        }
        for idx, u in enumerate(top_users)
    ]

    me_entry: dict | None = None
    if user:
        result = await session.execute(select(User).order_by(User.points.desc(), User.id))
        all_users = result.scalars().all()
        for idx, u in enumerate(all_users):
            if u.id == user.id:
                me_entry = {
                    "tg_id": u.tg_id,
                    "username": u.username,
                    "points": u.points,
                    "rank": idx + 1,
                }
                break
    return top, me_entry
