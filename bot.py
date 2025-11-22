import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
import redis.asyncio as redis
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# ========= tokens.txt loader =========
def load_tokens(path: str = "tokens.txt") -> Dict[str, str]:
    p = Path(path)
    data: Dict[str, str] = {}
    if not p.exists():
        raise FileNotFoundError(f"{path} not found")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data

TOKENS = load_tokens("tokens.txt")
API_TOKEN = TOKENS.get("API_TOKEN")
REDIS_HOST = TOKENS.get("REDIS_HOST", "localhost")
REDIS_PORT = int(TOKENS.get("REDIS_PORT", "6379"))
REDIS_DB = int(TOKENS.get("REDIS_DB", "0"))
WEBAPP_URL = TOKENS.get("WEBAPP_URL", "https://firstgamble.ru/").rstrip("/") + "/"

if not API_TOKEN or API_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
    raise RuntimeError("API_TOKEN is missing in tokens.txt")

# ========= Redis keys =========
def key_confirmed(user_id: int) -> str:
    return f"user:{user_id}:confirmed"

def key_balance(user_id: int) -> str:
    return f"user:{user_id}:balance"

# ========= globals =========
rds: Optional[redis.Redis] = None

# ========= Telegram bot =========
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data="confirm_no")
        ]
    ])

def kb_open_webapp(user_id: int) -> InlineKeyboardMarkup:
    # Fallback uid in URL, even if initData is empty.
    url = f"{WEBAPP_URL}?uid={user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть мини-аппку", web_app=WebAppInfo(url=url))]
    ])

@dp.message(CommandStart())
async def start_cmd(message: Message):
    user_id = message.from_user.id
    name = message.from_user.full_name

    confirmed = await rds.get(key_confirmed(user_id))
    if confirmed == "1":
        await message.answer(
            f"Привет, {name}! Доступ уже подтверждён ✅\nЖми кнопку ниже:",
            reply_markup=kb_open_webapp(user_id)
        )
        return

    await message.answer(
        "Привет! Чтобы продолжить и получить доступ к мини‑аппке, нужно подтвердить согласие.",
        reply_markup=kb_start()
    )

@dp.callback_query(F.data == "confirm_yes")
async def confirm_yes(call: CallbackQuery):
    user_id = call.from_user.id
    name = call.from_user.full_name

    # Mark confirmed
    await rds.set(key_confirmed(user_id), "1")
    # Ensure balance key exists
    bal = await rds.get(key_balance(user_id))
    if bal is None:
        await rds.set(key_balance(user_id), "0")

    # Remove old message (so "Привет чтобы продолжить" disappears)
    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer(
        f"Спасибо, {name}! Доступ подтверждён ✅",
        reply_markup=kb_open_webapp(user_id)
    )
    await call.answer()

@dp.callback_query(F.data == "confirm_no")
async def confirm_no(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer("Ок, без подтверждения доступ к мини‑аппке закрыт.")
    await call.answer()

# ========= HTTP API (aiohttp) =========
routes = web.RouteTableDef()

def json_error(msg: str, status: int = 400):
    return web.json_response({"ok": False, "error": msg}, status=status)

@routes.get("/api/balance")
async def api_balance(request: web.Request):
    user_id = request.query.get("user_id")
    if not user_id:
        return json_error("user_id required")
    bal = await rds.get(key_balance(int(user_id)))
    if bal is None:
        bal = "0"
        await rds.set(key_balance(int(user_id)), bal)
    return web.json_response({"user_id": str(user_id), "balance": int(bal)})

@routes.post("/api/add_point")
async def api_add_point(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return json_error("bad json")

    user_id = data.get("user_id")
    delta = data.get("delta", 0)

    if user_id is None:
        return json_error("user_id required")
    try:
        uid_int = int(user_id)
        delta_int = int(delta)
    except Exception:
        return json_error("bad data")

    # Ensure confirmed users only (optional gate)
    confirmed = await rds.get(key_confirmed(uid_int))
    if confirmed != "1":
        return json_error("not confirmed", status=403)

    new_bal = await rds.incrby(key_balance(uid_int), delta_int)
    return web.json_response({"ok": True, "user_id": str(uid_int), "balance": int(new_bal)})

async def run_api(app_host="0.0.0.0", app_port=8080):
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, app_host, app_port)
    await site.start()
    logging.info(f"API started on http://{app_host}:{app_port}")

async def main():
    global rds
    rds = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    # Start API in background task in same process
    await run_api()

    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
