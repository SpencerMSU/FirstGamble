import os
import logging
import redis
import asyncio
import json
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

# ---------- загрузка tokens.txt ----------
def load_tokens(filename="tokens.txt"):
    tokens = {}
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    tokens[k.strip()] = v.strip()
    return tokens

tokens = load_tokens()

API_TOKEN  = tokens.get("API_TOKEN")
REDIS_HOST = tokens.get("REDIS_HOST", "localhost")
REDIS_PORT = int(tokens.get("REDIS_PORT", 6379))
REDIS_DB   = int(tokens.get("REDIS_DB", 0))
WEBAPP_URL = tokens.get("WEBAPP_URL")  # ссылка на Vercel

if not API_TOKEN:
    raise RuntimeError("Нет API_TOKEN в tokens.txt")
if not WEBAPP_URL or not WEBAPP_URL.startswith("https://"):
    raise RuntimeError("WEBAPP_URL должен быть в tokens.txt и начинаться с https://")

# ---------- логирование + редис ----------
logging.basicConfig(level=logging.INFO)

r = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# ---------- /start ----------
@dp.message(Command("start"))
async def cmd_start(message):
    user_id = str(message.from_user.id)
    username = message.from_user.username or "друг"
    points_key = f"points:{user_id}"
    if r.get(points_key) is None:
        r.set(points_key, 0)

    # если нет ключа — создаём
    if r.get(user_id) is None:
        r.set(user_id, "not_confirmed")

    if r.get(user_id) == "confirmed":
        # уже подтверждён
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Открыть мини-аппку",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ])
        await message.answer(
            f"Привет, {username}! Ты уже подтвердил доступ ✅\n"
            f"Жми кнопку ниже и заходи в мини-приложение:",
            reply_markup=keyboard
        )
    else:
        # ещё не подтверждён
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="Отклонить", callback_data="reject")]
        ])
        await message.answer(
            "Привет! Чтобы продолжить, нажми кнопку ниже:",
            reply_markup=keyboard
        )


# ---------- confirm ----------
@dp.callback_query(lambda c: c.data == "confirm")
async def on_confirm(callback_query):
    user_id = str(callback_query.from_user.id)

    # сохраняем подтверждение
    r.set(user_id, "confirmed")

    # ответ на нажатие (чтобы не крутилось колесо)
    await callback_query.answer("Доступ получен ✅")

    # удаляем старое сообщение с кнопками подтверждения
    try:
        await callback_query.message.delete()
    except Exception:
        pass  # если удалить не удалось — не критично

    # отправляем кнопку открытия миниаппа
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Открыть мини-аппку",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])

    await bot.send_message(
        callback_query.from_user.id,
        "Готово! Нажми кнопку ниже, чтобы открыть мини-приложение:",
        reply_markup=keyboard
    )

# ---------------- API для миниаппки ----------------
async def api_balance(request: web.Request):
    # CORS чтобы Vercel мог дергать
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    if request.method == "OPTIONS":
        return web.Response(status=200, headers=headers)

    user_id = request.query.get("user_id")
    if not user_id:
        return web.json_response({"error": "no user_id"}, status=400, headers=headers)

    points_key = f"points:{user_id}"
    bal = r.get(points_key)
    bal = int(bal) if bal is not None else 0

    return web.json_response({"user_id": user_id, "balance": bal}, headers=headers)


async def start_api_server():
    app = web.Application()
    app.router.add_route("GET", "/api/balance", api_balance)
    app.router.add_route("OPTIONS", "/api/balance", api_balance)
    app.router.add_route("POST", "/api/add_point", api_add_point)
    app.router.add_route("OPTIONS", "/api/add_point", api_add_point)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)  # порт можно другой
    await site.start()
    logging.info("API server started on port 8080")

# ---------- reject ----------
@dp.callback_query(lambda c: c.data == "reject")
async def on_reject(callback_query):
    await callback_query.answer("Доступ отклонён.")
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await bot.send_message(
        callback_query.from_user.id,
        "Ок, без подтверждения мини-аппка недоступна."
    )

# POST /api/add_point  body: {"user_id":"123","delta":1}
async def api_add_point(request: web.Request):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    if request.method == "OPTIONS":
        return web.Response(status=200, headers=headers)

    try:
        data = await request.json()
    except:
        data = {}

    user_id = str(data.get("user_id", "")).strip()
    delta = int(data.get("delta", 0))

    if not user_id or delta == 0:
        return web.json_response({"ok": False, "error": "bad data"}, status=400, headers=headers)

    key = f"points:{user_id}"
    bal = int(r.get(key) or 0) + delta
    r.set(key, bal)

    return web.json_response({"ok": True, "user_id": user_id, "balance": bal}, headers=headers)

async def main():
    await start_api_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
