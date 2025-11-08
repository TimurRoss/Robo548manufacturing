"""
Обработчики для пользователей
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from pathlib import Path
from loguru import logger
from typing import Union

import config
import database
import keyboards
import states
from utils import notify_user_order_status_changed


router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Проверяем, зарегистрирован ли пользователь
    is_registered = await database.db.is_user_registered(user_id)
    
    if not is_registered:
        # Начинаем процесс регистрации
        await message.answer(
            "Добро пожаловать! Для начала работы необходимо зарегистрироваться.\n\n"
            "Введите вашу фамилию:"
        )
        await state.set_state(states.RegistrationStates.waiting_for_first_name)
    else:
        # Пользователь уже зарегистрирован - обновляем username если изменился
        await database.db.get_or_create_user(
            user_id, 
            message.from_user.first_name or "", 
            message.from_user.last_name or "", 
            username
        )
        user = await database.db.get_user(user_id)
        keyboard = keyboards.get_admin_menu_keyboard() if user_id in config.ADMIN_IDS else keyboards.get_main_menu_keyboard()
        await message.answer(
            f"Здравствуйте, {user['first_name']} {user['last_name']}!\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
        await state.clear()


@router.message(states.RegistrationStates.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    """Обработка фамилии при регистрации"""
    first_name = message.text.strip()
    if not first_name:
        await message.answer("Пожалуйста, введите корректную фамилию:")
        return
    
    await state.update_data(first_name=first_name)
    await message.answer("Введите ваше имя:")
    await state.set_state(states.RegistrationStates.waiting_for_last_name)


@router.message(states.RegistrationStates.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    """Обработка имени при регистрации"""
    last_name = message.text.strip()
    if not last_name:
        await message.answer("Пожалуйста, введите корректное имя:")
        return
    
    data = await state.get_data()
    first_name = data.get("first_name")
    
    # Сохраняем пользователя
    user_id = message.from_user.id
    username = message.from_user.username  # Получаем username из Telegram
    await database.db.get_or_create_user(user_id, first_name, last_name, username)
    
    keyboard = keyboards.get_admin_menu_keyboard() if user_id in config.ADMIN_IDS else keyboards.get_main_menu_keyboard()
    await message.answer(
        f"Регистрация завершена! Добро пожаловать, {first_name} {last_name}!\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )
    await state.clear()


@router.message(Command("new_order"))
@router.message(F.text == "Создать заказ")
async def cmd_new_order(message: Message, state: FSMContext):
    """Обработчик команды создания заказа"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Проверяем регистрацию и обновляем username
    if not await database.db.is_user_registered(user_id):
        await message.answer("Пожалуйста, сначала зарегистрируйтесь через /start")
        return
    
    # Обновляем username при создании заказа
    await database.db.get_or_create_user(
        user_id,
        message.from_user.first_name or "",
        message.from_user.last_name or "",
        username
    )
    
    await message.answer(
        "Начинаем создание заказа.\n\n"
        "Загрузите фото вашей модели (скриншот, чертеж):"
    )
    await state.set_state(states.OrderCreationStates.waiting_for_photo)


@router.message(states.OrderCreationStates.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработка загруженного фото"""
    photo = message.photo[-1]  # Берем фото с наибольшим разрешением
    
    # Скачиваем фото
    photo_path = config.PHOTOS_DIR / f"{message.from_user.id}_{photo.file_id}.jpg"
    photo_file = await message.bot.get_file(photo.file_id)
    await message.bot.download_file(photo_file.file_path, photo_path)
    
    photo_caption = message.caption if message.caption else None
    
    await state.update_data(
        photo_path=str(photo_path),
        photo_caption=photo_caption
    )
    
    data = await state.get_data()
    order_type = data.get("order_type", "3d_print")
    if order_type == "laser_cut":
        model_prompt = (
            "Фото получено!\n\n"
            "Теперь загрузите файл модели для лазерной резки в формате DXF:"
        )
    else:
        allowed = ", ".join(sorted(ext.upper().lstrip(".") for ext in config.ALLOWED_MODEL_EXTENSIONS))
        model_prompt = (
            "Фото получено!\n\n"
            f"Теперь загрузите файл 3D-модели в формате {allowed}:"
        )
    
    await message.answer(model_prompt)
    await state.set_state(states.OrderCreationStates.waiting_for_model)


@router.message(states.OrderCreationStates.waiting_for_photo)
async def process_photo_invalid(message: Message):
    """Обработка неверного формата фото"""
    await message.answer("Пожалуйста, загрузите фото (изображение):")


@router.message(states.OrderCreationStates.waiting_for_model, F.document)
async def process_model(message: Message, state: FSMContext):
    """Обработка загруженной 3D-модели"""
    document = message.document
    file_extension = Path(document.file_name).suffix.lower()
    
    data = await state.get_data()
    order_type = data.get("order_type", "3d_print")
    if order_type == "laser_cut":
        allowed_extensions = config.LASER_ALLOWED_MODEL_EXTENSIONS
    else:
        allowed_extensions = config.ALLOWED_MODEL_EXTENSIONS
    
    if file_extension not in allowed_extensions:
        allowed_readable = ", ".join(sorted(ext.upper().lstrip(".") for ext in allowed_extensions))
        allowed_with_dot = ", ".join(sorted(ext for ext in allowed_extensions))
        await message.answer(
            "Неверный формат файла.\n\n"
            f"Допустимы только файлы формата: {allowed_readable}.\n\n"
            f"Пожалуйста, загрузите файл с расширением {allowed_with_dot}:"
        )
        return
    
    # Скачиваем файл модели
    model_path = config.MODELS_DIR / f"{message.from_user.id}_{document.file_id}{file_extension}"
    file = await message.bot.get_file(document.file_id)
    await message.bot.download_file(file.file_path, model_path)
    
    original_filename = Path(document.file_name).stem
    
    await state.update_data(
        model_path=str(model_path),
        original_filename=document.file_name,
        file_extension=file_extension
    )
    
    await message.answer("Файл модели получен!\n\nВведите название детали:")
    await state.set_state(states.OrderCreationStates.waiting_for_part_name)


@router.message(states.OrderCreationStates.waiting_for_model)
async def process_model_invalid(message: Message, state: FSMContext):
    """Обработка неверного формата файла модели"""
    data = await state.get_data()
    order_type = data.get("order_type", "3d_print")
    
    if order_type == "laser_cut":
        await message.answer("Пожалуйста, загрузите файл модели для лазерной резки (DXF):")
        return
    
    allowed = ", ".join(sorted(ext.upper().lstrip(".") for ext in config.ALLOWED_MODEL_EXTENSIONS))
    await message.answer(f"Пожалуйста, загрузите файл 3D-модели ({allowed}):")


@router.message(states.OrderCreationStates.waiting_for_part_name)
async def process_part_name(message: Message, state: FSMContext):
    """Обработка названия детали"""
    part_name = message.text.strip()
    if not part_name:
        await message.answer("Пожалуйста, введите название детали:")
        return
    
    await state.update_data(part_name=part_name)
    
    # Получаем список материалов
    data = await state.get_data()
    order_type = data.get('order_type', '3d_print')
    materials = await database.db.get_all_materials(order_type)
    if not materials:
        await message.answer("К сожалению, материалы временно недоступны. Обратитесь к администратору.")
        await state.clear()
        return
    
    await message.answer(
        "Выберите материал (цвет + тип пластика):",
        reply_markup=keyboards.get_materials_keyboard(materials)
    )
    await state.set_state(states.OrderCreationStates.waiting_for_material)


@router.callback_query(F.data.startswith("select_material:"), states.OrderCreationStates.waiting_for_material)
async def process_material_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора материала (цвет + тип)"""
    material_id = int(callback.data.split(":")[1])
    await state.update_data(material_id=material_id)
    
    await callback.message.edit_text(
        "Хотите добавить комментарий к заказу?\n\n"
        "Напишите ваш комментарий или нажмите кнопку 'Пропустить':",
        reply_markup=keyboards.get_skip_comment_keyboard()
    )
    await state.set_state(states.OrderCreationStates.waiting_for_comment)
    await callback.answer()


@router.message(states.OrderCreationStates.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext):
    """Обработка комментария к заказу"""
    comment = message.text.strip()
    if not comment:
        await message.answer("Пожалуйста, введите комментарий или нажмите кнопку 'Пропустить':")
        return
    
    await state.update_data(comment=comment)
    await _show_order_summary(message, state)


@router.callback_query(F.data == "skip_comment", states.OrderCreationStates.waiting_for_comment)
async def skip_comment(callback: CallbackQuery, state: FSMContext):
    """Пропустить комментарий"""
    await state.update_data(comment=None)
    await _show_order_summary(callback.message, state)
    await callback.answer()


async def _show_order_summary(message_or_callback, state: FSMContext):
    """Показать сводку заказа для подтверждения"""
    data = await state.get_data()
    
    if isinstance(message_or_callback, CallbackQuery):
        callback = message_or_callback
        message = callback.message
        user_obj = callback.from_user
    else:
        message = message_or_callback
        user_obj = message.from_user

    user_id = user_obj.id
    first_name = user_obj.first_name or ""
    last_name = user_obj.last_name or ""
    username = user_obj.username

    user = await database.db.get_user(user_id)
    if not user:
        user = await database.db.get_or_create_user(user_id, first_name, last_name, username)
    
    order_type = data.get('order_type', '3d_print')
    material_id = data['material_id']
    materials = await database.db.get_all_materials(order_type)
    material_name = next((m['name'] for m in materials if m['id'] == material_id), "Не указан")

    order_type_name = config.ORDER_TYPES.get(order_type, order_type)

    summary = (
        f"📋 Проверьте данные заказа:\n\n"
        f"⚙️ Тип: {order_type_name}\n"
        f"👤 Заказчик: {user['first_name']} {user['last_name']}\n"
        f"📦 Название детали: {data['part_name']}\n"
        f"🧪 Материал: {material_name}\n"
        f"📷 Фото: прикреплено\n"
        f"📁 Модель: {data['original_filename']}\n"
    )

    if data.get('comment'):
        summary += f"💬 Комментарий: {data['comment']}\n"

    summary += "\nВсё верно?"

    if isinstance(message_or_callback, CallbackQuery):
        await message.edit_text(
            summary,
            reply_markup=keyboards.get_confirm_order_keyboard()
        )
    else:
        await message.answer(
            summary,
            reply_markup=keyboards.get_confirm_order_keyboard()
        )

    await state.set_state(states.OrderCreationStates.waiting_for_confirm)


@router.callback_query(F.data == "confirm_order", states.OrderCreationStates.waiting_for_confirm)
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    """Подтверждение создания заказа"""
    data = await state.get_data()
    user_id = callback.from_user.id
    
    try:
        # Создаем заказ в БД
        order_id = await database.db.create_order(
            user_id=user_id,
            material_id=data['material_id'],
            part_name=data['part_name'],
            photo_path=data['photo_path'],
            model_path=data['model_path'],
            photo_caption=data.get('photo_caption'),
            original_filename=data['original_filename'],
            comment=data.get('comment'),
            order_type=data.get('order_type', '3d_print')
        )

        # Уведомляем администраторов о новом заказе
        user = await database.db.get_user(user_id)
        material = await database.db.get_material(data['material_id'])
        material_name = material['name'] if material else "Не указан"
        order_type = data.get('order_type', '3d_print')
        order_type_name = config.ORDER_TYPES.get(order_type, "3D-печать")

        admin_message = (
            f"🆕 Новый заказ №{order_id}\n\n"
            f"⚙️ Тип: {order_type_name}\n"
            f"📦 Деталь: {data['part_name']}\n"
            f"🧪 Материал: {material_name}\n"
            f"👤 Клиент: {user['first_name']} {user['last_name']} (ID: {user['user_id']})\n"
        )

        comment = data.get('comment')
        if comment:
            admin_message += f"💬 Комментарий: {comment}\n"

        admin_message += "\nПерейдите в /admin, чтобы обработать заказ."

        for admin_id in config.ADMIN_IDS:
            if admin_id == user_id:
                continue
            try:
                await callback.bot.send_message(admin_id, admin_message)
            except Exception as notify_error:
                logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {notify_error}")
 
        await callback.message.edit_text(
            f"✅ Ваш заказ №{order_id} создан и принят в очередь!\n"
            f"Статус: 'В ожидании'.\n\n"
            f"Вы будете уведомлены об изменении статуса заказа."
        )
        
        logger.info(f"Заказ №{order_id} создан пользователем {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при создании заказа. Попробуйте позже."
        )
    
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cancel_order", states.OrderCreationStates.waiting_for_confirm)
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    """Отмена создания заказа"""
    await callback.message.edit_text("❌ Создание заказа отменено.")
    await state.clear()
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    contacts_text = "📞 Контакты технических специалистов:\n\n"
    
    for i, contact in enumerate(config.TECH_SUPPORT_CONTACTS, 1):
        contacts_text += f"{i}. {contact['name']}\n"
        contacts_text += f"   {contact['role']}\n"
        contacts_text += f"   {contact['contact']}\n\n"
    
    contacts_text += "Если у вас возникли проблемы, обратитесь к одному из специалистов."
    
    await message.answer(contacts_text)


@router.message(Command("my_orders"))
@router.message(F.text == "Мои заказы")
async def cmd_my_orders(message: Message):
    """Обработчик команды просмотра заказов пользователя"""
    user_id = message.from_user.id
    
    if not await database.db.is_user_registered(user_id):
        await message.answer("Пожалуйста, сначала зарегистрируйтесь через /start")
        return
    
    orders = await database.db.get_user_orders(user_id)
    
    if not orders:
        await message.answer("У вас пока нет заказов.")
        return
    
    await message.answer(
        "Ваши заказы:\n\n"
        "Выберите заказ для просмотра:",
        reply_markup=keyboards.get_orders_list_keyboard(orders, prefix="my_order")
    )


@router.callback_query(F.data.startswith("my_order:"))
async def show_user_order_detail(callback: CallbackQuery):
    """Показать детали заказа пользователю"""
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order or order['user_id'] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    status_name = order.get('status_name', 'Неизвестно')
    material_name = order.get('material_name', 'Не указан')
    status_code = order.get('status_code', 'unknown')
    
    order_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {order['created_at']}\n"
        f"📦 Название детали: {order['part_name']}\n"
        f"🧪 Материал: {material_name}\n"
        f"📊 Статус: {status_name}\n"
    )
    
    if order.get('comment'):
        order_text += f"💬 Комментарий: {order['comment']}\n"
    
    await callback.message.edit_text(
        order_text,
        reply_markup=keyboards.get_order_detail_keyboard(order_id, status_code, is_admin=False)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user_picked_up:"))
async def user_picked_up_order(callback: CallbackQuery):
    """Обработка нажатия кнопки 'Забрал' пользователем"""
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order or order['user_id'] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    if order.get('status_code') != 'ready':
        await callback.answer("Заказ еще не готов к выдаче", show_alert=True)
        return
    
    # Перемещаем заказ в архив
    success = await database.db.archive_order(order_id)
    
    if success:
        await callback.message.edit_text(
            f"✅ Заказ №{order_id} помечен как полученный и перемещен в архив.\n\n"
            "Спасибо за использование нашего сервиса! 🎉"
        )
        logger.info(f"Пользователь {callback.from_user.id} пометил заказ №{order_id} как полученный (перемещен в архив)")
    else:
        await callback.answer("Ошибка при архивировании заказа", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "user_back_to_orders")
async def user_back_to_orders(callback: CallbackQuery):
    """Вернуться к списку заказов пользователя"""
    user_id = callback.from_user.id
    
    orders = await database.db.get_user_orders(user_id)
    
    if not orders:
        await callback.message.edit_text("У вас пока нет заказов.")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "Ваши заказы:\n\n"
        "Выберите заказ для просмотра:",
        reply_markup=keyboards.get_orders_list_keyboard(orders, prefix="my_order")
    )
    await callback.answer()

