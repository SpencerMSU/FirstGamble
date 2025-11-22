import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class GameType(str, enum.Enum):
    dice = "dice"
    blackjack = "blackjack"
    slots = "slots"


class Outcome(str, enum.Enum):
    win = "win"
    lose = "lose"
    draw = "draw"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(64))
    last_name: Mapped[Optional[str]] = mapped_column(String(64))
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    cooldowns: Mapped[list["Cooldown"]] = relationship(back_populates="user", cascade="all, delete")
    game_results: Mapped[list["GameResult"]] = relationship(back_populates="user", cascade="all, delete")


class Cooldown(Base):
    __tablename__ = "cooldowns"
    __table_args__ = (UniqueConstraint("user_id", "game_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_type: Mapped[GameType] = mapped_column(Enum(GameType, name="gametype"), nullable=False)
    last_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="cooldowns")


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_type: Mapped[GameType] = mapped_column(Enum(GameType, name="gametype", create_type=False), nullable=False)
    outcome: Mapped[Outcome] = mapped_column(Enum(Outcome, name="outcome"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="game_results")


class ShopItem(Base):
    __tablename__ = "shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    price_points: Mapped[int] = mapped_column(Integer, nullable=False)
