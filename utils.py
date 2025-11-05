"""
Вспомогательные функции
"""
from aiogram import Bot
from loguru import logger
import keyboards
import database


async def notify_user_order_status_changed(bot: Bot, order: dict, status_name: str):
    """Отправить уведомление пользователю об изменении статуса заказа"""
    try:
        user_id = order['user_id']
        order_id = order['id']
        
        # Формируем сообщение в зависимости от статуса
        if status_name == "Готов":
            message = (
                f"✅ Ваш заказ №{order_id} готов к выдаче!\n\n"
                "Не забудьте забрать ваш заказ. Пожалуйста, нажмите кнопку 'Забрал' после получения."
            )
            # Добавляем кнопку "Забрал" для готовых заказов
            await bot.send_message(
                user_id, 
                message,
                reply_markup=keyboards.get_order_detail_keyboard(order_id, "ready", is_admin=False)
            )
        elif status_name == "Отклонен":
            rejection_reason = order.get('rejection_reason', 'Не указана')
            message = (
                f"❌ Ваш заказ №{order_id} отклонен.\n\n"
                f"Причина отклонения: {rejection_reason}"
            )
            await bot.send_message(user_id, message)
        else:
            message = f"📋 Ваш заказ №{order_id} переведен в статус '{status_name}'."
            await bot.send_message(user_id, message)
        
        logger.info(f"Уведомление отправлено пользователю {user_id} о заказе №{order_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления: {e}")


async def send_reminder_about_ready_order(bot: Bot, order: dict):
    """Отправить напоминание пользователю о готовом заказе"""
    try:
        user_id = order['user_id']
        order_id = order['id']
        
        message = (
            f"🔔 Напоминание: Ваш заказ №{order_id} готов к выдаче!\n\n"
            "Не забудьте забрать ваш заказ. Пожалуйста, нажмите кнопку 'Забрал' после получения."
        )
        
        await bot.send_message(
            user_id,
            message,
            reply_markup=keyboards.get_order_detail_keyboard(order_id, "ready", is_admin=False)
        )
        
        # Обновляем время последнего напоминания
        await database.db.update_last_reminder_time(order_id)
        
        logger.info(f"Напоминание отправлено пользователю {user_id} о заказе №{order_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания: {e}")

