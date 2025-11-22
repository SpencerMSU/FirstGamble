import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings

settings = get_settings()
bot = Bot(token=settings.bot_token)
dp = Dispatcher()


@dp.message(CommandStart())
async def on_start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтверждаю", callback_data="confirm"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="decline"),
            ]
        ]
    )
    await message.answer(
        (
            "Перед запуском мини-приложения подтвердите условия:\n"
            "1) Вы старше 18 лет.\n"
            "2) Вы принимаете правила и соглашение проекта."
        ),
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@dp.callback_query(F.data == "confirm")
async def on_confirm(callback_query: CallbackQuery):
    await callback_query.answer("Условия подтверждены", show_alert=False)

    web_app_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть FirstGamble", 
                    web_app={"url": f"{settings.frontend_url}/?tgWebAppStartParam=confirm"},
                )
            ]
        ]
    )
    await callback_query.message.answer(
        "Отлично! Теперь можно открыть мини-приложение.",
        reply_markup=web_app_kb,
        disable_web_page_preview=True,
    )


@dp.callback_query(F.data == "decline")
async def on_decline(callback_query: CallbackQuery):
    await callback_query.answer("Запуск отменён", show_alert=True)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
