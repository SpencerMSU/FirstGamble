from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import User
from .telegram import ensure_recent_auth, verify_init_data


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    x_telegram_init_data: str | None = Header(default=None, convert_underscores=False),
):
    settings = get_settings()
    if not settings.bot_token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="BOT_TOKEN is not set")

    if not x_telegram_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Header X-Telegram-Init-Data is required")

    data = verify_init_data(x_telegram_init_data, settings.bot_token)
    auth_date = int(data.get("auth_date", 0))
    ensure_recent_auth(auth_date)

    user_payload = data.get("user") or {}
    tg_id = int(user_payload.get("id"))
    username = user_payload.get("username")
    first_name = user_payload.get("first_name")
    last_name = user_payload.get("last_name")

    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            tg_id=tg_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        user.username = username or user.username
        user.first_name = first_name or user.first_name
        user.last_name = last_name or user.last_name
        await session.commit()

    return user
