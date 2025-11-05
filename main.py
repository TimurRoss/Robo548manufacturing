"""
Главный файл для запуска Telegram-бота 3DPrintQueue
"""
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
import sys

import config
import database
from handlers import user_handlers, admin_handlers
from pathlib import Path


# Создаем директорию для логов
Path("logs").mkdir(exist_ok=True)

# Настройка логирования
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/bot_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    level="DEBUG"
)


async def main():
    """Главная функция запуска бота"""
    # Проверка токена
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Установите переменную окружения BOT_TOKEN или добавьте её в config.py")
        return
    
    # Инициализация бота и диспетчера
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация роутеров
    dp.include_router(user_handlers.router)
    dp.include_router(admin_handlers.router)
    
    # Инициализация базы данных
    await database.db.init_db()
    logger.info("База данных инициализирована")
    
    # Проверка администраторов
    if not config.ADMIN_IDS:
        logger.warning("ADMIN_IDS не установлен! Админ-функции будут недоступны.")
    else:
        logger.info(f"Зарегистрировано администраторов: {len(config.ADMIN_IDS)}")
    
    logger.info("Бот запущен и готов к работе")
    
    # Запуск бота
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

