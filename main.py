import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN
from handlers import router
from monitor import monitor_prices
from storage import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def setup_commands(bot: Bot) -> None:
    """Меню команд рядом с полем ввода в Telegram."""
    await bot.set_my_commands([
        BotCommand(command="alert", description="Создать алерт: /alert BTC > 70000"),
        BotCommand(command="alerts", description="Мои алерты"),
        BotCommand(command="premium", description="Премиум-подписка"),
        BotCommand(command="help", description="Как пользоваться"),
        BotCommand(command="start", description="Запуск и меню"),
    ])


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

    try:
        await setup_commands(bot)
    except Exception:
        logger.exception("Не удалось установить меню команд")

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