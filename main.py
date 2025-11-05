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
from utils import send_reminder_about_ready_order
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
    
    # Запускаем фоновую задачу для отправки напоминаний
    async def reminder_task():
        """Фоновая задача для отправки напоминаний каждые 4 часа"""
        # Первая проверка сразу после запуска (через 1 минуту)
        await asyncio.sleep(60)
        
        while True:
            try:
                logger.info("Проверка заказов для отправки напоминаний...")
                
                # Получаем заказы, которым нужно отправить напоминание
                orders = await database.db.get_ready_orders_for_reminder(hours=4)
                
                for order in orders:
                    await send_reminder_about_ready_order(bot, order)
                
                if orders:
                    logger.info(f"Отправлено напоминаний: {len(orders)}")
                else:
                    logger.debug("Заказов для напоминаний не найдено")
                
                # Ждем 4 часа перед следующей проверкой
                await asyncio.sleep(4 * 3600)
                    
            except Exception as e:
                logger.error(f"Ошибка в задаче напоминаний: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед следующей попыткой
    
    # Запускаем фоновую задачу
    reminder_task_handle = asyncio.create_task(reminder_task())
    
    # Запуск бота
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        reminder_task_handle.cancel()
        try:
            await reminder_task_handle
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")

