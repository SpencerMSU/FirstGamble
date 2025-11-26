from aiogram import Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from .config import WEBAPP_URL
from .redis_utils import ensure_user, get_redis, key_confirmed


async def cmd_start(message: Message):
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
    await cb.message.edit_text("❌ Вы отклонили запуск мини-приложения.")
    await cb.answer()


def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(on_confirm, F.data == "confirm")
    dp.callback_query.register(on_decline, F.data == "decline")
