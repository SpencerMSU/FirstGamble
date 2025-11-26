import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher

from .config import BOT_TOKEN
from .handlers import register_handlers
from .redis_utils import get_redis, rds
from .routes import routes

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()


async def on_startup(app: web.Application):
    await get_redis()
    logging.info("Redis connected")


async def on_cleanup(app: web.Application):
    if rds:
        await rds.close()


async def start_http(dp: Dispatcher):
    app = web.Application()
    app.add_routes(routes)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"HTTP server started on 0.0.0.0:{port}")

    await dp.start_polling(bot)


async def main():
    register_handlers(dp)
    await start_http(dp)


__all__ = ["main", "bot", "dp"]
