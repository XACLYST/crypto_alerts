import asyncio
import logging
import time
from collections import deque
from typing import NamedTuple

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from alert_types import (
    KIND_FUNDING,
    KIND_PCT,
    KIND_PRICE,
    KIND_VOLUME,
    allowed_alert_ids,
    notification_text,
)
from config import (
    FUNDING_REARM_ABS,
    PCT_REARM_RATIO,
    PRICE_CHECK_INTERVAL,
    REARM_HYSTERESIS,
    SEND_DELAY,
    VOLUME_REARM_HYSTERESIS,
)
from price_service import Ticker, fetch_funding, fetch_spot
from storage import (
    delete_all_user_alerts,
    get_all_alerts,
    get_premium_user_ids,
    update_triggered,
)

logger = logging.getLogger(__name__)

DAY = 86400


class Reading(NamedTuple):
    value: float
    direction: str        # "above" | "below" — единое условие для всех типов
    threshold: float
    margin: float         # на сколько значение должно отойти, чтобы алерт взвёлся заново
    price: float | None   # для текста уведомления


class PriceHistory:
    """Короткая история цен в памяти — только для символов с алертами на %.

    После перезапуска бота история пуста, и алерты на % за 1 час начнут
    работать не сразу, а когда накопится нужный период.
    """

    def __init__(self) -> None:
        self._data: dict[str, deque[tuple[float, float]]] = {}

    def update(self, spot: dict[str, Ticker], windows: dict[str, int], now: float) -> None:
        for sym in [s for s in self._data if s not in windows]:
            del self._data[sym]
        for sym, window in windows.items():
            ticker = spot.get(sym)
            if ticker is None:
                continue
            dq = self._data.setdefault(sym, deque())
            dq.append((now, ticker.price))
            cutoff = now - window - 3 * PRICE_CHECK_INTERVAL
            # оставляем один "якорный" отсчёт старше окна
            while len(dq) > 1 and dq[1][0] <= cutoff:
                dq.popleft()

    def reference(self, symbol: str, window: int, now: float) -> float | None:
        dq = self._data.get(symbol)
        if not dq:
            return None
        target = now - window
        for ts, price in reversed(dq):
            if ts <= target:
                return price
        oldest_ts, oldest_price = dq[0]
        if oldest_ts <= target + 2 * PRICE_CHECK_INTERVAL:  # почти накопилось
            return oldest_price
        return None  # истории ещё не хватает


_history = PriceHistory()


def read_alert(
    a, spot: dict[str, Ticker], funding: dict[str, float], now: float
) -> Reading | None:
    """Приводит любой тип алерта к виду: значение / условие / порог / запас."""
    ticker = spot.get(a.symbol)
    price = ticker.price if ticker else None

    if a.kind == KIND_FUNDING:
        rate = funding.get(a.symbol)
        if rate is None:
            return None
        return Reading(rate, a.direction, a.threshold, FUNDING_REARM_ABS, price)

    if ticker is None:
        return None

    if a.kind == KIND_PRICE:
        return Reading(ticker.price, a.direction, a.threshold,
                       abs(a.threshold) * REARM_HYSTERESIS, price)

    if a.kind == KIND_VOLUME:
        return Reading(ticker.turnover24h, a.direction, a.threshold,
                       abs(a.threshold) * VOLUME_REARM_HYSTERESIS, price)

    if a.kind == KIND_PCT:
        if a.window_sec >= DAY:
            change = ticker.change24h_pct  # Bybit уже считает скользящие 24ч
        else:
            ref = _history.reference(a.symbol, a.window_sec, now)
            if not ref:
                return None
            change = (ticker.price - ref) / ref * 100
        margin = a.threshold * PCT_REARM_RATIO
        if a.direction == "up":
            return Reading(change, "above", a.threshold, margin, price)
        return Reading(change, "below", -a.threshold, margin, price)

    return None


def condition_met(r: Reading) -> bool:
    return r.value > r.threshold if r.direction == "above" else r.value < r.threshold


def can_rearm(r: Reading) -> bool:
    if r.direction == "above":
        return r.value < r.threshold - r.margin
    return r.value > r.threshold + r.margin


async def check_once(bot: Bot) -> None:
    alerts = await get_all_alerts()  # один SELECT на весь цикл
    if not alerts:
        _history.update({}, {}, time.time())
        return

    premium_ids = await get_premium_user_ids()
    allowed = allowed_alert_ids(alerts, premium_ids)
    active = [a for a in alerts if a.id in allowed]  # остальные на паузе
    if not active:
        return

    spot: dict[str, Ticker] = {}
    funding: dict[str, float] = {}
    if any(a.kind != KIND_FUNDING for a in active):
        try:
            spot = await fetch_spot()  # один запрос на все пары
        except Exception:
            logger.exception("Не удалось получить споты Bybit")
    if any(a.kind == KIND_FUNDING for a in active):
        try:
            funding = await fetch_funding()  # один запрос на все контракты
        except Exception:
            logger.exception("Не удалось получить фандинг Bybit")

    now = time.time()
    windows: dict[str, int] = {}
    for a in active:
        if a.kind == KIND_PCT and a.window_sec < DAY:
            windows[a.symbol] = max(windows.get(a.symbol, 0), a.window_sec)
    _history.update(spot, windows, now)

    blocked_users: set[int] = set()

    for a in active:
        if a.user_id in blocked_users:
            continue
        reading = read_alert(a, spot, funding, now)
        if reading is None:
            continue

        if condition_met(reading) and not a.triggered:
            text = notification_text(a, reading.value, reading.price)
            try:
                await bot.send_message(a.chat_id, text)
                # помечаем сработавшим ТОЛЬКО после успешной отправки
                await update_triggered(a.id, True)
            except TelegramForbiddenError:
                blocked_users.add(a.user_id)
                await delete_all_user_alerts(a.user_id)
                logger.info("Пользователь %s заблокировал бота, алерты удалены", a.user_id)
            except TelegramRetryAfter as e:
                logger.warning("Лимит Telegram, жду %s сек", e.retry_after)
                await asyncio.sleep(e.retry_after)
            except Exception:
                logger.exception("Не удалось отправить алерт id=%s", a.id)
            await asyncio.sleep(SEND_DELAY)

        elif a.triggered and can_rearm(reading):
            await update_triggered(a.id, False)


async def monitor_prices(bot: Bot) -> None:
    """Фоновый цикл: раз в N секунд проверяет все активные алерты."""
    logger.info("Monitor started")
    while True:
        try:
            await check_once(bot)
        except Exception:
            logger.exception("Ошибка в мониторинге")
        await asyncio.sleep(PRICE_CHECK_INTERVAL)