import logging
import aiohttp

logger = logging.getLogger(__name__)

# Bybit V5 endpoint для получения тикеров
BYBIT_URL = "https://api.bybit.com/v5/market/tickers"


async def fetch_prices(symbols: list[str]) -> dict[str, float]:
    """Возвращает {symbol: price}. symbols — тикеры Bybit, напр. 'BTCUSDT', 'GRAMUSDT'."""
    if not symbols:
        return {}

    result: dict[str, float] = {}
    async with aiohttp.ClientSession() as session:
        for symbol in symbols:
            try:
                # Bybit требует указать категорию, для спота это "spot"
                async with session.get(
                    BYBIT_URL, 
                    params={"category": "spot", "symbol": symbol}, 
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Структура ответа Bybit: result -> list -> [0] -> lastPrice
                        if data.get("retCode") == 0:
                            ticker_list = data.get("result", {}).get("list", [])
                            if ticker_list:
                                price = ticker_list[0].get("lastPrice")
                                if price:
                                    result[symbol] = float(price)
                    else:
                        logger.warning(f"Bybit вернул {resp.status} для {symbol}")
            except Exception as e:
                logger.warning(f"Ошибка получения цены {symbol} с Bybit: {e}")
    return result


async def validate_symbol(symbol: str) -> bool:
    """Проверяет, существует ли торговая пара на Bybit (спот)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                BYBIT_URL, 
                params={"category": "spot", "symbol": symbol}, 
                timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("retCode") == 0 and len(data.get("result", {}).get("list", [])) > 0
                return False
    except Exception:
        return False