import os
import logging
import redis
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

# Функция для чтения данных из tokens.txt
def load_tokens(filename="tokens.txt"):
    tokens = {}
    if os.path.exists(filename):
        with open(filename, "r") as file:
            for line in file:
                if line.strip() and "=" in line:
                    key, value = line.strip().split("=", 1)
                    tokens[key.strip()] = value.strip()
    return tokens

# Загружаем токены из файла
tokens = load_tokens()
API_TOKEN = tokens.get("API_TOKEN")
REDIS_HOST = tokens.get("REDIS_HOST", "localhost")
REDIS_PORT = int(tokens.get("REDIS_PORT", 6379))
REDIS_DB = int(tokens.get("REDIS_DB", 0))

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
        # Пользователь уже подтвердил
        await message.answer(f"Привет, {username}! Ты уже подтвердил доступ и можешь использовать мини‑приложение!")
    else:
        # Новый пользователь или не подтвержденный
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="Отклонить", callback_data="reject")]
        ])
        sent_message = await message.answer("Привет! Чтобы продолжить, нажмите кнопку ниже.", reply_markup=keyboard)

        # Удаляем сообщение через 5 секунд
        await asyncio.sleep(5)  # Задержка на 5 секунд перед удалением
        await sent_message.delete()

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
