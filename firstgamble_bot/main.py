import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from logging_setup import configure_logging

configure_logging(service_name="firstgamble-bot", env=os.getenv("FG_ENV", "prod"))

from .config import BOT_TOKEN
from .handlers import register_handlers
from .redis_utils import get_redis, rds
from .routes import routes

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


async def on_startup(app: web.Application):
    """Initializes the Redis connection on startup."""
    await get_redis()
    logging.info("Redis connected")


async def on_cleanup(app: web.Application):
    """Closes the Redis connection on cleanup."""
    if rds:
        await rds.close()


async def start_http(dp: Dispatcher):
    """Starts the HTTP server and the bot.

    Args:
        dp: The bot's dispatcher.
    """
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
    """The main function of the bot."""
    register_handlers(dp)
    await start_http(dp)


__all__ = ["main", "bot", "dp"]
