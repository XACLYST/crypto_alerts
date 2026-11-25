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

# бесплатно: столько алертов "цена достигла уровня"
FREE_ALERT_LIMIT = 2
# премиум: общий потолок алертов (защита от злоупотреблений)
PREMIUM_ALERT_LIMIT = 50

# подписка в Telegram Stars (списывается раз в 30 дней)
PREMIUM_PRICE_STARS = 100  # подбери цену сам
SUBSCRIPTION_PERIOD = 30 * 24 * 60 * 60  # Telegram разрешает только 30 дней

# --- повторное "взведение" сработавшего алерта ---
# цена: цена должна отойти от порога минимум на 0.1%
REARM_HYSTERESIS = 0.001
# объём: на 2%
VOLUME_REARM_HYSTERESIS = 0.02
# фандинг: на 0.002 процентных пункта
FUNDING_REARM_ABS = 0.002
# алерт на %: изменение должно упасть ниже 80% от порога
PCT_REARM_RATIO = 0.2

# пауза между отправками уведомлений (сек), ~20 сообщений/сек при лимите Telegram ~30
SEND_DELAY = 0.05