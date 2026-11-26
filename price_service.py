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


@dataclass(frozen=True)
class SymbolInfo:
    """Текущие данные по одной паре — чтобы показать их при создании алерта."""
    price: float
    change24h_pct: float | None = None   # спот
    turnover24h: float | None = None     # спот, в валюте котировки
    funding: float | None = None         # бессрочный контракт, в процентах


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


async def get_spot_price(symbol: str) -> float | None:
    """Текущая цена спот-пары или None, если пары нет / Bybit недоступен."""
    try:
        items = await _get_tickers("spot", symbol)
    except Exception as e:
        logger.debug("Нет спот-пары %s: %s", symbol, e)
        return None
    return _f(items[0].get("lastPrice")) if items else None


async def resolve_symbol(raw: str, kind: str) -> tuple[str, float | None] | None:
    """Подбирает тикер: сначала как ввёл пользователь, затем с добавлением USDT
    (BTC -> BTCUSDT). Возвращает (тикер, текущая цена) или None."""
    candidates = [raw]
    if not raw.endswith(("USDT", "USDC")):
        candidates.append(raw + "USDT")
    for symbol in candidates:
        if kind == "funding":
            if await validate_symbol(symbol, "funding"):
                return symbol, await get_spot_price(symbol)
        else:
            price = await get_spot_price(symbol)
            if price is not None:
                return symbol, price
    return None


async def get_symbol_info(symbol: str, kind: str = "price") -> SymbolInfo | None:
    """Текущая цена и сопутствующие данные пары. None — пары нет или Bybit недоступен."""
    category = "linear" if kind == "funding" else "spot"
    try:
        items = await _get_tickers(category, symbol)
    except Exception as e:
        logger.debug("Нет данных по %s (%s): %s", symbol, category, e)
        return None
    if not items:
        return None

    t = items[0]
    price = _f(t.get("lastPrice"))
    if price is None:
        return None
    if kind == "funding":
        rate = _f(t.get("fundingRate"))
        if rate is None:
            return None
        return SymbolInfo(price=price, funding=rate * 100)

    change = _f(t.get("price24hPcnt"))
    return SymbolInfo(
        price=price,
        change24h_pct=change * 100 if change is not None else None,
        turnover24h=_f(t.get("turnover24h")),
    )