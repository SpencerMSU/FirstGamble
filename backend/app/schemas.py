from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from .models import GameType, Outcome


class TelegramUserPayload(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class AuthRequest(BaseModel):
    init_data: str = Field(..., description="Строка initData из Telegram WebApp")


class ProfileResponse(BaseModel):
    tg_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    points: int
    created_at: datetime


class CooldownInfo(BaseModel):
    game_type: GameType
    remaining_seconds: int


class CooldownResponse(BaseModel):
    cooldowns: list[CooldownInfo]


class DiceRequest(BaseModel):
    dice_count: int = Field(ge=1, le=5, description="Количество кубиков от 1 до 5")


class DiceRollResult(BaseModel):
    values: list[int]
    total: int


class DiceResponse(BaseModel):
    player: DiceRollResult
    robot: DiceRollResult
    outcome: Outcome
    points_awarded: int


class BlackjackResult(BaseModel):
    player_hand: list[str]
    dealer_hand: list[str]
    player_score: int
    dealer_score: int
    outcome: Outcome
    points_awarded: int


class SlotsResponse(BaseModel):
    reels: list[str]
    outcome: Outcome
    points_awarded: int


class ShopItemSchema(BaseModel):
    title: str
    description: str
    price_points: int


class ShopResponse(BaseModel):
    balance: int
    items: list[ShopItemSchema]


class LeaderboardEntry(BaseModel):
    tg_id: int
    username: str | None
    points: int
    rank: int


class LeaderboardResponse(BaseModel):
    top: list[LeaderboardEntry]
    me: LeaderboardEntry | None


class TelegramStartPayload(BaseModel):
    start_url: HttpUrl
    confirm_button_text: str = "Подтвердить"
    decline_button_text: str = "Отклонить"
    message: str = "Запустить мини-приложение?"


class ErrorResponse(BaseModel):
    detail: Any
