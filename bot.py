import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

# ---------- utils ----------
def load_token(path="Tokens.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

BOT_TOKEN = load_token()

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ---------- keyboards ----------
def terms_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="terms_accept"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data="terms_decline"),
        ]
    ])

def open_app_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🚀 Открыть FirstClub",
                web_app=WebAppInfo(url="https://firstgamble.ru")
            )
        ]
    ])

# ---------- handlers ----------
@dp.message(CommandStart())
async def start(message: Message):
    text = (
        "🎲 <b>FirstClub</b>\n\n"
        "Перед использованием мини-приложения нужно принять правила.\n"
        "Нажми <b>Подтвердить</b>, чтобы продолжить."
    )
    await message.answer(text, reply_markup=terms_kb())

@dp.callback_query(F.data == "terms_accept")
async def terms_accept(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "✅ Правила приняты.\n\n"
        "Теперь можешь открыть мини-приложение:",
        reply_markup=open_app_kb()
    )

@dp.callback_query(F.data == "terms_decline")
async def terms_decline(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "❌ Без принятия правил доступ к мини-приложению закрыт.\n"
        "Если передумаешь — нажми /start."
    )

# ---------- main ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
