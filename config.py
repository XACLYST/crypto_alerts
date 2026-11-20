from os import getenv
from pathlib import Path

from dotenv import load_dotenv

# ищем .env рядом с config.py, а не в текущей директории
load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")

# интервал опроса цен (секунды)
PRICE_CHECK_INTERVAL = 10

# сколько алертов можно создать бесплатно
FREE_ALERT_LIMIT = 2

# цена снятия лимита в Telegram Stars
PREMIUM_PRICE_STARS = 50