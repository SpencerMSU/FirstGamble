import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logging_setup import configure_logging

configure_logging(service_name="firstgamble-api", env=os.getenv("FG_ENV", "prod"))

app = FastAPI(
    title="FirstGamble API",
    description="HTTP API для мини-приложения, бота и внешних игр.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

from .routes import register_routes  # noqa: E402

register_routes(app)

__all__ = ["app"]
