import asyncio
import logging
import redis
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from config import API_TOKEN, REDIS_HOST, REDIS_PORT, REDIS_DB  # или через tokens.txt

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Подключение к Redis
r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# Создание объекта бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command(commands=["start"]))
async def cmd_start(message):
    user_id = str(message.from_user.id)
    username = message.from_user.username

    # Добавляем пользователя, если его нет
    if r.get(user_id) is None:
        r.set(user_id, "not_confirmed")

    # Проверяем статус пользователя
    if r.get(user_id) == "confirmed":
        await message.answer("Вы уже подтвердили доступ и можете использовать мини‑приложение!")
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="Отклонить", callback_data="reject")]
        ])
        await message.answer("Привет! Чтобы продолжить, нажмите кнопку ниже.", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "confirm")
async def on_confirm(callback_query):
    user_id = str(callback_query.from_user.id)
    r.set(user_id, "confirmed")
    await callback_query.answer("Доступ к мини‑приложению получен!")
    await bot.send_message(callback_query.from_user.id, "Теперь ты можешь использовать мини‑приложение!")

@dp.callback_query(lambda c: c.data == "reject")
async def on_reject(callback_query):
    await callback_query.answer("Доступ отклонен.")
    await bot.send_message(callback_query.from_user.id, "Вы отклонили доступ.")

# Основная функция для запуска бота
async def main():
    await dp.start_polling(bot)

# Запуск бота
if __name__ == "__main__":
    asyncio.run(main())
