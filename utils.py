"""
Вспомогательные функции
"""
from aiogram import Bot
from aiogram.types import FSInputFile
from pathlib import Path
from loguru import logger
import keyboards
import database
import config


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
            order_type_code = order.get('order_type', '3d_print')
            order_type_name = config.ORDER_TYPES.get(order_type_code, order_type_code)
            material_name = order.get('material_name') or "Не указан"
            part_name = order.get('part_name') or "Не указано"
            comment = order.get('comment')
            
            # Формируем сообщение с минимальными данными о заказе
            message = (
                f"❌ Заказ №{order_id} отклонен\n\n"
                f"⚙️ Тип: {order_type_name}\n"
                f"📦 Деталь: {part_name}\n"
                f"🧪 Материал: {material_name}\n"
            )
            
            if comment:
                message += f"💬 Комментарий: {comment}\n"
            
            message += f"\n❌ Причина отклонения: {rejection_reason}"
            
            # Создаем клавиатуру с кнопкой перехода в "Мои заказы"
            keyboard = keyboards.get_rejected_order_notification_keyboard()
            
            # Проверяем наличие фото
            photo_path = order.get('photo_path')
            if photo_path and Path(photo_path).exists():
                try:
                    photo_file = FSInputFile(photo_path)
                    await bot.send_photo(
                        user_id,
                        photo_file,
                        caption=message,
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке фото в уведомлении об отклонении: {e}")
                    # Если не удалось отправить фото, отправляем просто текст
                    await bot.send_message(user_id, message, reply_markup=keyboard)
            else:
                # Если фото нет, отправляем просто текстовое сообщение
                await bot.send_message(user_id, message, reply_markup=keyboard)
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

