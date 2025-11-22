import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings

settings = get_settings()
bot = Bot(token=settings.bot_token)
dp = Dispatcher()


@dp.message(CommandStart())
async def on_start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    web_app={"url": f"{settings.frontend_url}/?tgWebAppStartParam=confirm"},
                ),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="decline"),
            ]
        ]
    )
    await message.answer(
        "Запустить мини-приложение FirstGamble?", reply_markup=kb, disable_web_page_preview=True
    )


@dp.callback_query(F.data == "decline")
async def on_decline(callback_query):
    await callback_query.answer("Запуск отменён", show_alert=True)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
