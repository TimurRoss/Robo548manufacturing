"""
Обработчики для администраторов
"""
from aiogram import Router, F
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
        "Выберите действие:",
        reply_markup=keyboards.get_admin_orders_keyboard()
    )


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
    else:
        orders = await database.db.get_orders_by_status(status_code)
        status_text = config.ORDER_STATUSES.get(status_code, status_code)
    
    if not orders:
        await callback.message.edit_text(f"Заказов со статусом '{status_text}' не найдено.")
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
    
    await callback.message.edit_text(
        "🔧 Панель администратора\n\n"
        "Выберите действие:",
        reply_markup=keyboards.get_admin_orders_keyboard()
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
    color_name = order.get('color_name', 'Не указан')
    
    # Формируем текст с информацией о заказе
    order_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {order['created_at']}\n"
        f"👤 Заказчик: {order['first_name']} {order['last_name']}\n"
        f"🆔 Telegram ID: {order['user_id']}\n"
        f"📦 Название детали: {order['part_name']}\n"
        f"🧪 Тип пластика: {material_name}\n"
        f"🎨 Цвет: {color_name}\n"
        f"📊 Статус: {status_name}\n"
    )
    
    if order.get('photo_caption'):
        order_text += f"📝 Подпись к фото: {order['photo_caption']}\n"
    
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
                reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code)
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            await callback.message.edit_text(order_text)
            # Отправляем клавиатуру отдельным сообщением
            await callback.bot.send_message(
                callback.message.chat.id,
                "Выберите действие:",
                reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code)
            )
    else:
        await callback.message.edit_text(order_text)
        # Отправляем клавиатуру отдельным сообщением
        await callback.bot.send_message(
            callback.message.chat.id,
            "Выберите действие:",
            reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code)
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
    
    # Обновляем сообщение с заказом - получаем обновленный заказ и показываем его
    if order:
        # Используем обновленные данные из заказа
        current_status_code = order.get('status_code', 'unknown')
        current_status_name = order.get('status_name', 'Неизвестно')
        material_name = order.get('material_name', 'Не указан')
        color_name = order.get('color_name', 'Не указан')
        
        order_text = (
            f"📋 Заказ №{order['id']}\n\n"
            f"📅 Дата создания: {order['created_at']}\n"
            f"👤 Заказчик: {order['first_name']} {order['last_name']}\n"
            f"🆔 Telegram ID: {order['user_id']}\n"
            f"📦 Название детали: {order['part_name']}\n"
            f"🧪 Тип пластика: {material_name}\n"
            f"🎨 Цвет: {color_name}\n"
            f"📊 Статус: {current_status_name}\n"
        )
        
        if order.get('photo_caption'):
            order_text += f"📝 Подпись к фото: {order['photo_caption']}\n"
        
        # Отправляем обновленное сообщение
        await callback.message.edit_text(
            f"✅ Статус изменен на '{current_status_name}'\n\n{order_text}"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=keyboards.get_order_detail_keyboard(order_id, current_status_code)
        )
    
    await callback.answer(f"Статус изменен на '{status_name}'")


@router.callback_query(F.data == "admin_manage_materials")
async def manage_materials(callback: CallbackQuery):
    """Управление материалами"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔧 Управление материалами\n\n"
        "Выберите действие:",
        reply_markup=keyboards.get_manage_materials_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_menu")
async def back_to_admin_menu(callback: CallbackQuery):
    """Вернуться в главное меню админки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔧 Панель администратора\n\n"
        "Выберите действие:",
        reply_markup=keyboards.get_admin_orders_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_material")
async def add_material_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("Введите название нового типа пластика:")
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
        await message.answer("Пожалуйста, введите корректное название:")
        return
    
    success = await database.db.add_material(material_name)
    
    if success:
        await message.answer(f"✅ Тип пластика '{material_name}' добавлен!")
    else:
        await message.answer(f"❌ Тип пластика '{material_name}' уже существует!")
    
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
        "Выберите тип пластика для удаления:",
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
        await callback.message.edit_text("✅ Тип пластика удален!")
    else:
        await callback.message.edit_text("❌ Ошибка при удалении!")
    
    await callback.answer()


@router.callback_query(F.data == "admin_add_color")
async def add_color_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление цвета"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("Введите название нового цвета:")
    await state.set_state(states.MaterialManagementStates.waiting_for_color_name)
    await callback.answer()


@router.message(states.MaterialManagementStates.waiting_for_color_name)
async def add_color_process(message: Message, state: FSMContext):
    """Обработка добавления цвета"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    color_name = message.text.strip()
    if not color_name:
        await message.answer("Пожалуйста, введите корректное название:")
        return
    
    success = await database.db.add_color(color_name)
    
    if success:
        await message.answer(f"✅ Цвет '{color_name}' добавлен!")
    else:
        await message.answer(f"❌ Цвет '{color_name}' уже существует!")
    
    await state.clear()


@router.callback_query(F.data == "admin_delete_color")
async def delete_color_start(callback: CallbackQuery):
    """Начать удаление цвета"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    colors = await database.db.get_all_colors()
    
    if not colors:
        await callback.message.edit_text("Нет цветов для удаления.")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "Выберите цвет для удаления:",
        reply_markup=keyboards.get_delete_colors_keyboard(colors)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_color:"))
async def delete_color_process(callback: CallbackQuery):
    """Обработка удаления цвета"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    color_id = int(callback.data.split(":")[1])
    success = await database.db.delete_color(color_id)
    
    if success:
        await callback.message.edit_text("✅ Цвет удален!")
    else:
        await callback.message.edit_text("❌ Ошибка при удалении!")
    
    await callback.answer()

