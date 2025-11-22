import os
import asyncio
import logging
import redis
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)

# =========================
#  LOAD TOKENS.TXT
# =========================
def load_tokens(filename="tokens.txt"):
    tokens = {}
    if not os.path.exists(filename):
        raise RuntimeError(f"Файл {filename} не найден рядом с bot.py")

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip()
    return tokens


tokens = load_tokens("tokens.txt")

API_TOKEN  = tokens.get("API_TOKEN")
REDIS_HOST = tokens.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(tokens.get("REDIS_PORT", 6379))
REDIS_DB   = int(tokens.get("REDIS_DB", 0))
WEBAPP_URL = tokens.get("WEBAPP_URL")  # ссылка на Vercel миниаппки

if not API_TOKEN:
    raise RuntimeError("В tokens.txt нет API_TOKEN=...")
if not WEBAPP_URL or not WEBAPP_URL.startswith("https://"):
    raise RuntimeError("В tokens.txt нет WEBAPP_URL=https://... (обязательно https)")

# =========================
#  LOGGING + REDIS
# =========================
logging.basicConfig(level=logging.INFO)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# =========================
#  AIOHTTP API (8080)
# =========================

# ---- GET /api/balance?user_id=123
async def api_balance(request: web.Request):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    if request.method == "OPTIONS":
        return web.Response(status=200, headers=headers)

    user_id = request.query.get("user_id", "").strip()
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400, headers=headers)

    key = f"points:{user_id}"
    balance = int(r.get(key) or 0)

    return web.json_response({"user_id": user_id, "balance": balance}, headers=headers)


# ---- POST /api/add_point  body: {"user_id":"123","delta":1}
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
    delta   = int(data.get("delta", 0))

    if not user_id or delta == 0:
        return web.json_response(
            {"ok": False, "error": "bad data"},
            status=400,
            headers=headers
        )

    key = f"points:{user_id}"
    balance = int(r.get(key) or 0) + delta
    r.set(key, balance)

    return web.json_response(
        {"ok": True, "user_id": user_id, "balance": balance},
        headers=headers
    )


async def start_api_server():
    app = web.Application()

    app.router.add_route("GET", "/api/balance", api_balance)
    app.router.add_route("OPTIONS", "/api/balance", api_balance)

    app.router.add_route("POST", "/api/add_point", api_add_point)
    app.router.add_route("OPTIONS", "/api/add_point", api_add_point)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    logging.info("API started on http://0.0.0.0:8080")


# =========================
#  TELEGRAM BOT LOGIC
# =========================

confirm_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data="confirm")],
        [InlineKeyboardButton(text="Отклонить", callback_data="reject")]
    ]
)

def user_confirm_key(user_id: str) -> str:
    return f"user_confirmed:{user_id}"

def user_points_key(user_id: str) -> str:
    return f"points:{user_id}"


@dp.message(CommandStart())
async def cmd_start(msg: Message):
    user_id = str(msg.from_user.id)
    username = msg.from_user.username or "друг"

    # если нет баланса — создаём 0
    pkey = user_points_key(user_id)
    if r.get(pkey) is None:
        r.set(pkey, 0)

    ckey = user_confirm_key(user_id)

    # если уже подтвердил — сразу даём кнопку MiniApp
    if r.get(ckey) == "1":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть мини-аппку", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
        await msg.answer(
            f"Привет, {username}! Доступ уже подтверждён ✅\n"
            f"Жми кнопку ниже:",
            reply_markup=kb
        )
        return

    # иначе просим подтверждение
    await msg.answer(
        "Привет! Чтобы продолжить, подтверди условия:",
        reply_markup=confirm_kb
    )


@dp.callback_query(F.data == "confirm")
async def on_confirm(call):
    user_id = str(call.from_user.id)
    ckey = user_confirm_key(user_id)

    r.set(ckey, "1")

    await call.answer("Доступ получен ✅")

    # удаляем старое сообщение с кнопками
    try:
        await call.message.delete()
    except Exception:
        pass

    # шлём кнопку открытия мини-аппки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть мини-аппку", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

    await bot.send_message(
        call.from_user.id,
        "Готово! Нажми кнопку ниже, чтобы открыть мини-приложение:",
        reply_markup=kb
    )


@dp.callback_query(F.data == "reject")
async def on_reject(call):
    await call.answer("Доступ отклонён.")
    try:
        await call.message.delete()
    except Exception:
        pass

    await bot.send_message(call.from_user.id, "Ок, без подтверждения мини-аппка недоступна.")


# =========================
#  MAIN
# =========================
async def main():
    # запускаем API и бота вместе
    api_task = asyncio.create_task(start_api_server())
    bot_task = asyncio.create_task(dp.start_polling(bot))
    await asyncio.gather(api_task, bot_task)


if __name__ == "__main__":
    asyncio.run(main())
