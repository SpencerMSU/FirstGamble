import logging
import logging
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent.parent
TOKENS_FILE = BASE_DIR / "tokens.txt"

if not TOKENS_FILE.exists():
    raise SystemExit("tokens.txt not found")


def load_config() -> Dict[str, str]:
    """Loads configuration from tokens.txt.

    Reads the tokens.txt file in the base directory and parses it into a
    dictionary. Lines that are empty, start with '#', or do not contain '='
    are ignored.

    Returns:
        A dictionary containing the configuration keys and values.
    """
    config: Dict[str, str] = {}
    with TOKENS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


config = load_config()

BOT_TOKEN = config.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is missing in tokens.txt")

CONSERVE_AUTH_TOKEN = config.get("ConServeAuthToken") or config.get("CONSERVE_AUTH_TOKEN")
if not CONSERVE_AUTH_TOKEN:
    logging.warning(
        "ConServeAuthToken is not set in tokens.txt; external SAMP access will be disabled."
    )

REDIS_HOST = config.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(config.get("REDIS_PORT", "6379"))
REDIS_DB = int(config.get("REDIS_DB", "0"))

WEBAPP_URL = config.get("WEBAPP_URL", "").rstrip("/")
if not WEBAPP_URL:
    raise SystemExit("WEBAPP_URL is missing in tokens.txt")

logging.info(f"WEBAPP_URL = {WEBAPP_URL}")
