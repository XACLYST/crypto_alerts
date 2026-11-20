import asyncio
import logging

from aiogram import Bot

from config import PRICE_CHECK_INTERVAL
from price_service import fetch_prices
from storage import get_alerts_for_symbol, get_all_symbols, update_triggered

logger = logging.getLogger(__name__)


async def monitor_prices(bot: Bot) -> None:
    logger.info("Monitor started")
    """Фоновый цикл: раз в N секунд проверяет цены по всем активным алертам."""
    while True:
        try:
            symbols = list(await get_all_symbols())
            logger.info(f"Checking symbols: {symbols}")
            if symbols:
                prices = await fetch_prices(symbols)
                logger.info(f"Got prices: {prices}")
                for symbol in symbols:
                    price = prices.get(symbol)
                    if price is None:
                        continue
                    for alert in await get_alerts_for_symbol(symbol):
                        condition_met = (
                            alert.direction == "below" and price < alert.threshold
                        ) or (
                            alert.direction == "above" and price > alert.threshold
                        )
                        logger.info(
                            f"Alert id={alert.id} {alert.symbol} {alert.direction} "
                            f"{alert.threshold} | price={price} | triggered={alert.triggered} "
                            f"| condition_met={condition_met}"
                        )

                        if condition_met and not alert.triggered:
                            await update_triggered(alert.id, True)
                            await bot.send_message(
                                alert.chat_id,
                                f"🚩🚩🚩 {alert.symbol} сейчас {price:.3f}$ 🚩🚩🚩" #🚨🚨🚨
                                f"({'ниже' if alert.direction == 'below' else 'выше'} "
                                f"{alert.threshold}$)",
                            )
                        elif not condition_met and alert.triggered:
                            await update_triggered(alert.id, False)
        except Exception as e:
            logger.exception(f"Ошибка в мониторинге: {e}")

        await asyncio.sleep(PRICE_CHECK_INTERVAL)