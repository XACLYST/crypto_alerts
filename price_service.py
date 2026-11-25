import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

BYBIT_URL = "https://api.bybit.com/v5/market/tickers"
TIMEOUT = aiohttp.ClientTimeout(total=10)


@dataclass(frozen=True)
class Ticker:
    price: float
    turnover24h: float     # оборот за 24ч в валюте котировки (для BTCUSDT — в USDT)
    change24h_pct: float   # изменение за 24ч, в процентах


def fmt_price(price: float) -> str:
    """Красивый вывод числа: без экспоненты и без лишних нулей."""
    text = f"{price:.4f}" if abs(price) >= 1 else f"{price:.8f}"
    return text.rstrip("0").rstrip(".")


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _get_tickers(category: str, symbol: str | None = None) -> list[dict]:
    params = {"category": category}
    if symbol:
        params["symbol"] = symbol
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.get(BYBIT_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit error: {data.get('retMsg')}")
    return data.get("result", {}).get("list", [])


async def fetch_spot() -> dict[str, Ticker]:
    """Все спот-пары одним запросом: цена, оборот за 24ч, изменение за 24ч."""
    result: dict[str, Ticker] = {}
    for t in await _get_tickers("spot"):
        price = _f(t.get("lastPrice"))
        if not price:
            continue
        result[t["symbol"]] = Ticker(
            price=price,
            turnover24h=_f(t.get("turnover24h")) or 0.0,
            change24h_pct=(_f(t.get("price24hPcnt")) or 0.0) * 100,
        )
    return result


async def fetch_funding() -> dict[str, float]:
    """Ставки фандинга бессрочных контрактов (linear) в ПРОЦЕНТАХ, одним запросом."""
    result: dict[str, float] = {}
    for t in await _get_tickers("linear"):
        rate = _f(t.get("fundingRate"))
        if rate is not None:
            result[t["symbol"]] = rate * 100
    return result


async def validate_symbol(symbol: str, kind: str = "price") -> bool:
    """Есть ли пара на Bybit: спот для price/pct/volume, бессрочный контракт для funding."""
    category = "linear" if kind == "funding" else "spot"
    try:
        items = await _get_tickers(category, symbol)
    except Exception as e:
        logger.warning("Ошибка проверки пары %s: %s", symbol, e)
        return False
    if not items:
        return False
    if kind == "funding":
        return _f(items[0].get("fundingRate")) is not None
    return True