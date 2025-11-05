"""
Вспомогательные функции
"""
from aiogram import Bot
from loguru import logger


async def notify_user_order_status_changed(bot: Bot, order: dict, status_name: str):
    """Отправить уведомление пользователю об изменении статуса заказа"""
    try:
        user_id = order['user_id']
        order_id = order['id']
        
        # Формируем сообщение в зависимости от статуса
        if status_name == "Готов":
            message = f"✅ Ваш заказ №{order_id} готов к выдаче!"
        else:
            message = f"📋 Ваш заказ №{order_id} переведен в статус '{status_name}'."
        
        await bot.send_message(user_id, message)
        logger.info(f"Уведомление отправлено пользователю {user_id} о заказе №{order_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления: {e}")

