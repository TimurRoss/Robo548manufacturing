"""
Обработчики для администраторов
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from pathlib import Path
from loguru import logger

import config
import database
import keyboards
import states
from utils import notify_user_order_status_changed


router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in config.ADMIN_IDS


@router.message(Command("admin"))
@router.message(F.text == "Админ-панель")
async def cmd_admin(message: Message):
    """Обработчик команды админ-панели"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к админ-панели.")
        return
    
    await message.answer(
        "🔧 Панель администратора\n\n"
        "Выберите раздел:",
        reply_markup=keyboards.get_admin_main_keyboard()
    )


@router.callback_query(F.data == "admin_orders_menu")
async def show_orders_menu(callback: CallbackQuery):
    """Показать меню фильтров заказов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    # Получаем статистику по заказам
    stats = await database.db.get_orders_statistics()
    
    # Получаем количество заказов в архиве
    archived_orders = await database.db.get_archived_orders()
    archived_count = len(archived_orders)
    
    # Формируем текст со статистикой
    stats_text = "📊 Статистика:\n"
    stats_text += f"• Все заказы: {stats.get('all', 0)} шт\n"
    stats_text += f"• В ожидании: {stats.get('pending', 0)} шт\n"
    stats_text += f"• В работе: {stats.get('in_progress', 0)} шт\n"
    stats_text += f"• Готов: {stats.get('ready', 0)} шт\n"
    stats_text += f"• Архив: {archived_count} шт\n"
    
    await callback.message.edit_text(
        f"📦 Заказы\n\n{stats_text}\nВыберите фильтр:",
        reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_orders:"))
async def show_orders_by_status(callback: CallbackQuery):
    """Показать заказы по статусу"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    status_code = callback.data.split(":")[1]
    
    if status_code == "all":
        orders = await database.db.get_orders_by_status(None)
        status_text = "Все заказы"
    elif status_code == "archived":
        orders = await database.db.get_archived_orders()
        status_text = "Архив"
    else:
        orders = await database.db.get_orders_by_status(status_code)
        status_text = config.ORDER_STATUSES.get(status_code, status_code)
    
    if not orders:
        stats = await database.db.get_orders_statistics()
        archived_orders = await database.db.get_archived_orders()
        archived_count = len(archived_orders)
        await callback.message.edit_text(
            f"Заказов со статусом '{status_text}' не найдено.",
            reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count)
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"📋 {status_text} ({len(orders)} заказов):\n\n"
        "Выберите заказ для просмотра:",
        reply_markup=keyboards.get_orders_list_keyboard(orders, prefix="admin_order")
    )
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_orders")
async def back_to_orders_list(callback: CallbackQuery):
    """Вернуться к списку заказов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    # Получаем статистику по заказам
    stats = await database.db.get_orders_statistics()
    
    # Получаем количество заказов в архиве
    archived_orders = await database.db.get_archived_orders()
    archived_count = len(archived_orders)
    
    # Формируем текст со статистикой
    stats_text = "📊 Статистика:\n"
    stats_text += f"• Все заказы: {stats.get('all', 0)} шт\n"
    stats_text += f"• В ожидании: {stats.get('pending', 0)} шт\n"
    stats_text += f"• В работе: {stats.get('in_progress', 0)} шт\n"
    stats_text += f"• Готов: {stats.get('ready', 0)} шт\n"
    stats_text += f"• Архив: {archived_count} шт\n"
    
    await callback.message.edit_text(
        f"📦 Заказы\n\n{stats_text}\nВыберите фильтр:",
        reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_main")
async def back_to_admin_main(callback: CallbackQuery):
    """Вернуться в главное меню админ-панели"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔧 Панель администратора\n\n"
        "Выберите раздел:",
        reply_markup=keyboards.get_admin_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_order:"))
async def show_order_detail(callback: CallbackQuery):
    """Показать детали заказа администратору"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    status_code = order.get('status_code', 'unknown')
    status_name = order.get('status_name', 'Неизвестно')
    material_name = order.get('material_name', 'Не указан')
    
    # Формируем информацию о пользователе
    user_info = f"{order['first_name']} {order['last_name']}"
    if order.get('username'):
        user_info += f" (@{order['username']})"
    user_info += f"\n🆔 Telegram ID: {order['user_id']}"
    
    # Формируем текст с информацией о заказе
    order_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {order['created_at']}\n"
        f"👤 Заказчик: {user_info}\n"
        f"📦 Название детали: {order['part_name']}\n"
        f"🧪 Материал: {material_name}\n"
        f"📊 Статус: {status_name}\n"
    )
    
    if order.get('photo_caption'):
        order_text += f"📝 Подпись к фото: {order['photo_caption']}\n"
    
    if order.get('rejection_reason'):
        order_text += f"\n❌ Причина отклонения: {order['rejection_reason']}\n"
    
    # Отправляем фото, если есть, иначе редактируем текст
    if order.get('photo_path') and Path(order['photo_path']).exists():
        try:
            photo_file = FSInputFile(order['photo_path'])
            await callback.message.delete()  # Удаляем старое сообщение
            await callback.bot.send_photo(
                callback.message.chat.id,
                photo_file,
                caption=order_text
            )
            # Отправляем клавиатуру отдельным сообщением
            await callback.bot.send_message(
                callback.message.chat.id,
                "Выберите действие:",
                reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code, is_admin=True)
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            await callback.message.edit_text(order_text)
            # Отправляем клавиатуру отдельным сообщением
            await callback.bot.send_message(
                callback.message.chat.id,
                "Выберите действие:",
                reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code, is_admin=True)
            )
    else:
        await callback.message.edit_text(order_text)
        # Отправляем клавиатуру отдельным сообщением
        await callback.bot.send_message(
            callback.message.chat.id,
            "Выберите действие:",
            reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code, is_admin=True)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("download_model:"))
async def download_model(callback: CallbackQuery):
    """Скачать модель с переименованием"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    model_path = Path(order['model_path'])
    if not model_path.exists():
        await callback.answer("Файл модели не найден", show_alert=True)
        return
    
    # Формируем новое имя файла по шаблону
    # {НомерЗаказа}_{Фамилия}_{Имя}_{НазваниеДетали}.stp (или .stl)
    file_extension = model_path.suffix
    part_name = order['part_name'] or order['original_filename'].replace(file_extension, '')
    new_filename = f"{order['id']}_{order['last_name']}_{order['first_name']}_{part_name}{file_extension}"
    
    try:
        # Создаем временный файл с новым именем
        temp_file = Path("temp") / new_filename
        temp_file.parent.mkdir(exist_ok=True)
        
        # Копируем файл с новым именем
        import shutil
        shutil.copy2(model_path, temp_file)
        
        # Отправляем файл
        file_to_send = FSInputFile(temp_file, filename=new_filename)
        await callback.bot.send_document(
            callback.message.chat.id,
            file_to_send,
            caption=f"Модель для заказа №{order_id}"
        )
        
        # Удаляем временный файл
        temp_file.unlink()
        
        await callback.answer("Файл отправлен")
        logger.info(f"Администратор {callback.from_user.id} скачал модель для заказа №{order_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании модели: {e}")
        await callback.answer("Ошибка при отправке файла", show_alert=True)


@router.callback_query(F.data.startswith("reject_order:"))
async def reject_order_start(callback: CallbackQuery, state: FSMContext):
    """Начать процесс отклонения заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split(":")[1])
    
    # Сохраняем order_id в состоянии
    await state.update_data(order_id=order_id)
    
    await callback.message.edit_text(
        "❌ Отклонение заказа\n\n"
        "Пожалуйста, укажите причину отклонения заказа:"
    )
    await state.set_state(states.OrderRejectionStates.waiting_for_rejection_reason)
    await callback.answer()


@router.message(states.OrderRejectionStates.waiting_for_rejection_reason)
async def reject_order_process(message: Message, state: FSMContext):
    """Обработка комментария отклонения"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    rejection_reason = message.text.strip()
    if not rejection_reason:
        await message.answer("Пожалуйста, укажите причину отклонения:")
        return
    
    data = await state.get_data()
    order_id = data.get('order_id')
    
    if not order_id:
        await message.answer("Ошибка: не найден ID заказа")
        await state.clear()
        return
    
    # Получаем заказ перед архивированием для отправки уведомления
    order = await database.db.get_order(order_id)
    
    # Перемещаем заказ в архив с причиной отклонения
    success = await database.db.archive_order(order_id, rejection_reason)
    
    if not success:
        await message.answer("Ошибка при отклонении заказа")
        await state.clear()
        return
    
    # Обновляем заказ для отправки уведомления
    order = await database.db.get_order(order_id)
    order['rejection_reason'] = rejection_reason
    
    # Отправляем уведомление пользователю с причиной отклонения
    await notify_user_order_status_changed(message.bot, order, "Отклонен")
    
    # Получаем статистику для обновления меню
    stats = await database.db.get_orders_statistics()
    archived_orders = await database.db.get_archived_orders()
    archived_count = len(archived_orders)
    
    stats_text = "📊 Статистика:\n"
    stats_text += f"• Все заказы: {stats.get('all', 0)} шт\n"
    stats_text += f"• В ожидании: {stats.get('pending', 0)} шт\n"
    stats_text += f"• В работе: {stats.get('in_progress', 0)} шт\n"
    stats_text += f"• Готов: {stats.get('ready', 0)} шт\n"
    stats_text += f"• Архив: {archived_count} шт\n"
    
    await message.answer(
        f"✅ Заказ №{order_id} отклонен и перемещен в архив.\n\n"
        f"Причина: {rejection_reason}\n\n"
        f"{stats_text}\nВыберите фильтр:",
        reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count)
    )
    
    await state.clear()


@router.callback_query(F.data.startswith("set_status:"))
async def set_order_status(callback: CallbackQuery):
    """Изменить статус заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    _, order_id, status_code = callback.data.split(":")
    order_id = int(order_id)
    
    
    # Обновляем статус
    success = await database.db.update_order_status(order_id, status_code)
    
    if not success:
        await callback.answer("Ошибка при изменении статуса", show_alert=True)
        return
    
    # Получаем обновленный заказ
    order = await database.db.get_order(order_id)
    status_name = config.ORDER_STATUSES.get(status_code, status_code)
    
    # Отправляем уведомление пользователю
    await notify_user_order_status_changed(callback.bot, order, status_name)
    
    # Показываем обновленную информацию о заказе
    await show_order_detail_after_update(callback.bot, callback.message.chat.id, order_id)
    
    await callback.answer(f"Статус изменен на '{status_name}'")


@router.callback_query(F.data.startswith("admin_picked_up:"))
async def admin_picked_up_order(callback: CallbackQuery):
    """Обработка нажатия кнопки 'Забрал' администратором"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    if order.get('status_code') != 'ready':
        await callback.answer("Заказ не в статусе 'Готов'", show_alert=True)
        return
    
    # Перемещаем заказ в архив
    success = await database.db.archive_order(order_id)
    
    if success:
        # Получаем статистику для обновления меню
        stats = await database.db.get_orders_statistics()
        archived_orders = await database.db.get_archived_orders()
        archived_count = len(archived_orders)
        
        stats_text = "📊 Статистика:\n"
        stats_text += f"• Все заказы: {stats.get('all', 0)} шт\n"
        stats_text += f"• В ожидании: {stats.get('pending', 0)} шт\n"
        stats_text += f"• В работе: {stats.get('in_progress', 0)} шт\n"
        stats_text += f"• Готов: {stats.get('ready', 0)} шт\n"
        stats_text += f"• Архив: {archived_count} шт\n"
        
        await callback.message.edit_text(
            f"✅ Заказ №{order_id} перемещен в архив.\n\n"
            f"{stats_text}\nВыберите фильтр:",
            reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count)
        )
        logger.info(f"Администратор {callback.from_user.id} пометил заказ №{order_id} как полученный (перемещен в архив)")
    else:
        await callback.answer("Ошибка при архивировании заказа", show_alert=True)
    
    await callback.answer()


async def show_order_detail_after_update(bot: Bot, chat_id: int, order_id: int):
    """Показать обновленную информацию о заказе после изменения статуса"""
    order = await database.db.get_order(order_id)
    
    if not order:
        return
    
    status_code = order.get('status_code', 'unknown')
    status_name = order.get('status_name', 'Неизвестно')
    material_name = order.get('material_name', 'Не указан')
    
    # Формируем информацию о пользователе
    user_info = f"{order['first_name']} {order['last_name']}"
    if order.get('username'):
        user_info += f" (@{order['username']})"
    user_info += f"\n🆔 Telegram ID: {order['user_id']}"
    
    order_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {order['created_at']}\n"
        f"👤 Заказчик: {user_info}\n"
        f"📦 Название детали: {order['part_name']}\n"
        f"🧪 Материал: {material_name}\n"
        f"📊 Статус: {status_name}\n"
    )
    
    if order.get('photo_caption'):
        order_text += f"📝 Подпись к фото: {order['photo_caption']}\n"
    
    if order.get('rejection_reason'):
        order_text += f"\n❌ Причина отклонения: {order['rejection_reason']}\n"
    
    # Отправляем обновленное сообщение
    await bot.send_message(
        chat_id,
        f"✅ Статус изменен на '{status_name}'\n\n{order_text}"
    )
    await bot.send_message(
        chat_id,
        "Выберите действие:",
        reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code, is_admin=True)
    )


@router.callback_query(F.data == "admin_manage_materials")
async def manage_materials(callback: CallbackQuery):
    """Управление материалами"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    # Получаем материалы со статистикой использования
    materials = await database.db.get_materials_with_usage_count()
    
    # Формируем текст со списком материалов
    if materials:
        materials_text = "📋 Доступные материалы:\n\n"
        for material in materials:
            usage_count = material.get('usage_count', 0)
            materials_text += f"• {material['name']}"
            if usage_count > 0:
                materials_text += f" (использован {usage_count} раз"
                if usage_count == 1:
                    materials_text += ")"
                elif usage_count < 5:
                    materials_text += "а)"
                else:
                    materials_text += ")"
            materials_text += "\n"
        materials_text += f"\nВсего материалов: {len(materials)}"
    else:
        materials_text = "📋 Доступные материалы:\n\nМатериалы не добавлены."
    
    await callback.message.edit_text(
        f"🔧 Управление материалами\n\n{materials_text}\n\nВыберите действие:",
        reply_markup=keyboards.get_manage_materials_keyboard()
    )
    await callback.answer()




@router.callback_query(F.data == "admin_add_material")
async def add_material_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "Введите название материала в формате: \"цвет тип\"\n\n"
        "Примеры:\n"
        "• зеленый PETG\n"
        "• синий PLA\n"
        "• красный ABS"
    )
    await state.set_state(states.MaterialManagementStates.waiting_for_material_name)
    await callback.answer()


@router.message(states.MaterialManagementStates.waiting_for_material_name)
async def add_material_process(message: Message, state: FSMContext):
    """Обработка добавления материала"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    material_name = message.text.strip()
    if not material_name:
        await message.answer("Пожалуйста, введите корректное название в формате \"цвет тип\":")
        return
    
    success = await database.db.add_material(material_name)
    
    if success:
        # Получаем обновленный список материалов со статистикой
        materials = await database.db.get_materials_with_usage_count()
        
        # Формируем текст со списком материалов
        if materials:
            materials_text = "📋 Доступные материалы:\n\n"
            for material in materials:
                usage_count = material.get('usage_count', 0)
                materials_text += f"• {material['name']}"
                if usage_count > 0:
                    materials_text += f" (использован {usage_count} раз"
                    if usage_count == 1:
                        materials_text += ")"
                    elif usage_count < 5:
                        materials_text += "а)"
                    else:
                        materials_text += ")"
                materials_text += "\n"
            materials_text += f"\nВсего материалов: {len(materials)}"
        else:
            materials_text = "📋 Доступные материалы:\n\nМатериалы не добавлены."
        
        await message.answer(
            f"✅ Материал '{material_name}' добавлен!\n\n"
            f"{materials_text}\n\n"
            "Выберите действие:",
            reply_markup=keyboards.get_manage_materials_keyboard()
        )
    else:
        await message.answer(f"❌ Материал '{material_name}' уже существует!")
    
    await state.clear()


@router.callback_query(F.data == "admin_delete_material")
async def delete_material_start(callback: CallbackQuery):
    """Начать удаление материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    materials = await database.db.get_all_materials()
    
    if not materials:
        await callback.message.edit_text("Нет материалов для удаления.")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "Выберите материал для удаления:",
        reply_markup=keyboards.get_delete_materials_keyboard(materials)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_material:"))
async def delete_material_process(callback: CallbackQuery):
    """Обработка удаления материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    material_id = int(callback.data.split(":")[1])
    success = await database.db.delete_material(material_id)
    
    if success:
        # Получаем обновленный список материалов со статистикой
        materials = await database.db.get_materials_with_usage_count()
        
        # Формируем текст со списком материалов
        if materials:
            materials_text = "📋 Доступные материалы:\n\n"
            for material in materials:
                usage_count = material.get('usage_count', 0)
                materials_text += f"• {material['name']}"
                if usage_count > 0:
                    materials_text += f" (использован {usage_count} раз"
                    if usage_count == 1:
                        materials_text += ")"
                    elif usage_count < 5:
                        materials_text += "а)"
                    else:
                        materials_text += ")"
                materials_text += "\n"
            materials_text += f"\nВсего материалов: {len(materials)}"
        else:
            materials_text = "📋 Доступные материалы:\n\nМатериалы не добавлены."
        
        await callback.message.edit_text(
            f"✅ Материал удален!\n\n{materials_text}\n\nВыберите действие:",
            reply_markup=keyboards.get_manage_materials_keyboard()
        )
    else:
        await callback.message.edit_text("❌ Ошибка при удалении!")
    
    await callback.answer()

