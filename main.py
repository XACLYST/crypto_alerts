import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import router
from monitor import monitor_prices
from storage import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    # 1. Инициализируем БД ДО старта бота
    await init_db()
    logger.info("База данных инициализирована")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    monitor_task = asyncio.create_task(monitor_prices(bot))

    try:
        print("Starting bot...")
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()
        await bot.session.close()
        print("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())