import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import HTTPException, status


class TelegramAuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def parse_init_data(init_data: str) -> Dict[str, Any]:
    pairs = parse_qsl(init_data, keep_blank_values=True)
    data: Dict[str, Any] = {}
    for key, value in pairs:
        if key == "auth_date":
            data[key] = int(value)
        elif key == "user":
            data[key] = json.loads(value)
        else:
            data[key] = value
    return data


def verify_init_data(init_data: str, bot_token: str) -> Dict[str, Any]:
    data = parse_init_data(init_data)
    if "hash" not in data:
        raise TelegramAuthError("hash is missing in initData")

    received_hash = data.pop("hash")
    payload = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, calculated_hash):
        raise TelegramAuthError("initData signature is invalid")

    return data


def ensure_recent_auth(auth_date: int, max_age_seconds: int = 86400) -> None:
    now = datetime.utcnow().timestamp()
    if now - auth_date > max_age_seconds:
        raise TelegramAuthError("initData is too old, refresh the Telegram WebApp session")
