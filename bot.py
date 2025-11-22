import logging
import redis
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

# Функция для чтения токенов и других данных из tokens.txt
def load_tokens(filename="tokens.txt"):
    tokens = {}
    if os.path.exists(filename):
        with open(filename, "r") as file:
            for line in file:
                if line.strip() and "=" in line:
                    key, value = line.strip().split("=", 1)
                    tokens[key.strip()] = value.strip()
    return tokens

# Загружаем токены и настройки
tokens = load_tokens()
API_TOKEN = tokens.get("API_TOKEN")
REDIS_HOST = tokens.get("REDIS_HOST", "localhost")
REDIS_PORT = int(tokens.get("REDIS_PORT", 6379))
REDIS_DB = int(tokens.get("REDIS_DB", 0))

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Подключение к Redis
r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# Создание бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    user_id = str(message.from_user.id)  # Используем строковый тип для Redis
    username = message.from_user.username

    # Добавляем пользователя в Redis, если его нет
    if r.get(user_id) is None:
        r.set(user_id, 'not_confirmed')

    # Проверяем статус пользователя
    if r.get(user_id) == 'confirmed':
        await message.answer("Вы уже подтвердили доступ и можете использовать мини-приложение!")
    else:
        # Отправляем инлайн кнопки
        keyboard = InlineKeyboardMarkup(row_width=2)
        confirm_button = InlineKeyboardButton("Подтвердить", callback_data="confirm")
        reject_button = InlineKeyboardButton("Отклонить", callback_data="reject")
        keyboard.add(confirm_button, reject_button)

        await message.answer("Привет! Чтобы продолжить, нажмите кнопку ниже.", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == 'confirm')
async def process_confirm(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)

    # Подтверждаем пользователя в Redis
    r.set(user_id, 'confirmed')

    await bot.answer_callback_query(callback_query.id, text="Доступ к мини-приложению получен!")
    await bot.send_message(callback_query.from_user.id, "Теперь ты можешь использовать мини-приложение!")

@dp.callback_query_handler(lambda c: c.data == 'reject')
async def process_reject(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="Доступ отклонен.")
    await bot.send_message(callback_query.from_user.id, "Вы отклонили доступ.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
