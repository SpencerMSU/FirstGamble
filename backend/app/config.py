from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(
        default="sqlite+aiosqlite:///./firstgamble.db",
        description="SQLAlchemy URL для базы данных",
    )
    bot_token: str = Field(default="", description="Токен Telegram-бота")
    frontend_url: str = Field(default="https://firstgamble.ru", description="URL фронтенда")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
