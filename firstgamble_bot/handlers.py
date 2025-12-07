from aiogram import Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from .config import WEBAPP_URL
from .redis_utils import ensure_user, get_redis, key_confirmed


async def cmd_start(message: Message):
    """Handles the /start command.

    This function is called when a user sends the /start command to the bot.
    It sends a welcome message and asks the user to confirm that they agree
    to the terms of service.

    Args:
        message: The incoming message.
    """
    user = message.from_user
    user_id = user.id

    r = await get_redis()
    await ensure_user(user_id)

    confirmed = await r.get(key_confirmed(user_id))
    if confirmed == "1":
        webapp_button = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть приложение",
                        web_app=WebAppInfo(url=f"{WEBAPP_URL}/?uid={user_id}"),
                    )
                ]
            ]
        )
        await message.answer(
            "✅ Ты уже подтвердил запуск. Можно открыть мини-приложение:",
            reply_markup=webapp_button,
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data="decline")],
        ]
    )

    text = (
        "Добро пожаловать в FirstGamble / FirstClub!\n\n"
        "Перед использованием вы должны ознакомиться с условиями сервиса:\n"
        "https://telegra.ph/Terms-of-Service--FirstGamble-11-26\n\n"
        "Подтвердите, что вы согласны с правилами."
    )
    await message.answer(text, reply_markup=kb)


async def on_confirm(cb: CallbackQuery):
    """Handles the confirm callback query.

    This function is called when a user clicks the "confirm" button. It sets
    the user's confirmed status to "1" in Redis and sends a message with a
    button to open the web app.

    Args:
        cb: The incoming callback query.
    """
    user_id = cb.from_user.id
    r = await get_redis()

    await ensure_user(user_id)
    await r.set(key_confirmed(user_id), "1")

    webapp_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть приложение",
                    web_app=WebAppInfo(url=f"{WEBAPP_URL}/?uid={user_id}"),
                )
            ]
        ]
    )

    await cb.message.edit_text(
        "✅ Подтверждено! Теперь можно открыть мини-приложение:",
        reply_markup=webapp_button,
    )
    await cb.answer()


async def on_decline(cb: CallbackQuery):
    """Handles the decline callback query.

    This function is called when a user clicks the "decline" button. It edits
    the message to indicate that the user has declined to use the web app.

    Args:
        cb: The incoming callback query.
    """
    await cb.message.edit_text("❌ Вы отклонили запуск мини-приложения.")
    await cb.answer()


def register_handlers(dp: Dispatcher):
    """Registers the bot's handlers.

    Args:
        dp: The bot's dispatcher.
    """
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(on_confirm, F.data == "confirm")
    dp.callback_query.register(on_decline, F.data == "decline")
