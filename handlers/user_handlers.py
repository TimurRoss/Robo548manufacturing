"""
Обработчики для пользователей
"""
import html

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
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
        
        # Отправляем фото с подсказкой к меню
        menu_help_photo_path = Path("files/menu_help.png")
        help_text = (
            f"Здравствуйте, {user['first_name']} {user['last_name']}!\n\n"
            "📋 <b>Подсказка по использованию меню:</b>\n\n"
            "• <b>Создать заказ</b> - начать новый заказ на 3D печать или лазерную резку\n"
            "• <b>Мои заказы</b> - просмотреть все ваши заказы и их статусы\n"
        )
        
        if user_id in config.ADMIN_IDS:
            help_text += "• <b>Админ-панель</b> - управление заказами и настройками\n"
            help_text += "• <b>Рассылка</b> - отправка сообщений всем пользователям\n"
        
        help_text += "\nВыберите действие из меню ниже:"
        
        try:
            if menu_help_photo_path.exists():
                photo_file = FSInputFile(menu_help_photo_path)
                await message.answer_photo(
                    photo_file,
                    caption=help_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                # Если фото нет, отправляем только текст
                await message.answer(
                    help_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото подсказки: {e}")
            # В случае ошибки отправляем только текст
            await message.answer(
                help_text,
                reply_markup=keyboard,
                parse_mode="HTML"
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
    
    if user_id not in config.ADMIN_IDS:
        orders_enabled = await database.db.is_orders_enabled()
        if not orders_enabled:
            await message.answer(
                "Приём новых заказов временно закрыт.\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
            return

    # Обновляем username при создании заказа
    await database.db.get_or_create_user(
        user_id,
        message.from_user.first_name or "",
        message.from_user.last_name or "",
        username
    )
    
    await state.clear()
    await state.set_state(states.OrderCreationStates.waiting_for_order_type)
    await message.answer(
        "Начинаем создание заказа.\n\n"
        "Пожалуйста, выберите тип заказа:",
        reply_markup=keyboards.get_order_type_keyboard()
    )


@router.callback_query(F.data.startswith("select_order_type"), states.OrderCreationStates.waiting_for_order_type)
async def process_order_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа заказа"""
    order_type = callback.data.split(":")[1]
    order_type_name = config.ORDER_TYPES.get(order_type, "3D-печать")
    
    await state.update_data(order_type=order_type)
    
    if order_type == "laser_cut":
        prompt = (
            f"Вы выбрали: {order_type_name}.\n\n"
            "Загрузите фото вашей заготовки или схемы (скриншот, чертеж):"
        )
    else:
        prompt = (
            f"Вы выбрали: {order_type_name}.\n\n"
            "Загрузите фото вашей модели (скриншот, чертеж):"
        )
    
    await callback.message.edit_text(prompt)
    await state.set_state(states.OrderCreationStates.waiting_for_photo)
    await callback.answer()


@router.message(states.OrderCreationStates.waiting_for_order_type)
async def process_order_type_text(message: Message):
    """Подсказываем выбрать тип заказа через кнопки"""
    await message.answer(
        "Пожалуйста, выберите тип заказа, используя кнопки ниже:",
        reply_markup=keyboards.get_order_type_keyboard()
    )


@router.message(states.OrderCreationStates.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработка загруженного фото"""
    data = await state.get_data()
    order_type = data.get("order_type")
    if not order_type:
        await message.answer(
            "Пожалуйста, сначала выберите тип заказа:",
            reply_markup=keyboards.get_order_type_keyboard()
        )
        await state.set_state(states.OrderCreationStates.waiting_for_order_type)
        return
    
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
    
    if order_type == "laser_cut":
        material_prompt = "Выберите материал для лазерной резки:"
    else:
        material_prompt = "Выберите материал (цвет + тип пластика):"

    await message.answer(
        material_prompt,
        reply_markup=keyboards.get_materials_keyboard(materials)
    )
    await state.set_state(states.OrderCreationStates.waiting_for_material)


@router.callback_query(F.data.startswith("select_material:"), states.OrderCreationStates.waiting_for_material)
async def process_material_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора материала (цвет + тип)"""
    material_id = int(callback.data.split(":")[1])
    await state.update_data(material_id=material_id)
    
    await callback.message.edit_text(
        "Выберите количество деталей:\n\n"
        "Вы можете выбрать из предложенных вариантов или ввести количество вручную сообщением.",
        reply_markup=keyboards.get_quantity_keyboard()
    )
    await state.set_state(states.OrderCreationStates.waiting_for_quantity)
    await callback.answer()


@router.callback_query(F.data.startswith("select_quantity:"), states.OrderCreationStates.waiting_for_quantity)
async def process_quantity_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора количества через кнопки"""
    quantity = int(callback.data.split(":")[1])
    await state.update_data(quantity=quantity)
    
    await callback.message.edit_text(
        "Хотите добавить комментарий к заказу?\n\n"
        "Напишите ваш комментарий или нажмите кнопку 'Пропустить':",
        reply_markup=keyboards.get_skip_comment_keyboard()
    )
    await state.set_state(states.OrderCreationStates.waiting_for_comment)
    await callback.answer()


@router.message(states.OrderCreationStates.waiting_for_quantity)
async def process_quantity_text(message: Message, state: FSMContext):
    """Обработка ввода количества вручную"""
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            await message.answer("Количество должно быть больше нуля. Введите количество деталей:")
            return
        if quantity > 100:
            await message.answer("Количество не может превышать 100. Введите количество деталей:")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите число. Выберите количество из кнопок или введите число сообщением:")
        return
    
    await state.update_data(quantity=quantity)
    
    await message.answer(
        "Хотите добавить комментарий к заказу?\n\n"
        "Напишите ваш комментарий или нажмите кнопку 'Пропустить':",
        reply_markup=keyboards.get_skip_comment_keyboard()
    )
    await state.set_state(states.OrderCreationStates.waiting_for_comment)


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

    order_type_name_html = html.escape(order_type_name)
    user_full_name_html = html.escape(f"{user['first_name']} {user['last_name']}".strip())
    part_name_html = html.escape(data['part_name'])
    material_name_html = html.escape(material_name)
    original_filename_html = html.escape(data['original_filename'])
    quantity = data.get('quantity', 1)
    comment_text = data.get('comment')
    comment_html = html.escape(comment_text) if comment_text else None

    summary = (
        "📋 Проверьте данные заказа:\n\n"
        f"⚙️ Тип: {order_type_name_html}\n"
        f"👤 Заказчик: {user_full_name_html}\n"
        f"📦 Название детали: {part_name_html}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"📷 Фото: прикреплено\n"
        f"📁 Модель: {original_filename_html}\n"
        "\n"
        f"<b>Материал:</b>\n{material_name_html}"
    )

    if comment_html:
        summary += f"\n\n<b>Комментарий:</b>\n{comment_html}"

    summary += "\n\nВсё верно?"

    if isinstance(message_or_callback, CallbackQuery):
        await message.edit_text(
            summary,
            reply_markup=keyboards.get_confirm_order_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            summary,
            reply_markup=keyboards.get_confirm_order_keyboard(),
            parse_mode="HTML"
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
            order_type=data.get('order_type', '3d_print'),
            quantity=data.get('quantity', 1)
        )

        # Уведомляем администраторов о новом заказе
        user = await database.db.get_user(user_id)
        material = await database.db.get_material(data['material_id'])
        material_name = material['name'] if material else "Не указан"
        order_type = data.get('order_type', '3d_print')
        order_type_name = config.ORDER_TYPES.get(order_type, "3D-печать")

        quantity = data.get('quantity', 1)
        admin_message = (
            f"🆕 Новый заказ №{order_id}\n\n"
            f"⚙️ Тип: {order_type_name}\n"
            f"📦 Деталь: {data['part_name']}\n"
            f"🔢 Количество: {quantity} шт.\n"
            f"🧪 Материал: {material_name}\n"
            f"👤 Клиент: {user['first_name']} {user['last_name']} (ID: {user['user_id']})\n"
        )

        comment = data.get('comment')
        if comment:
            admin_message += f"💬 Комментарий: {comment}\n"

        admin_message += "\nНажмите «Раскрыть заказ», чтобы просмотреть детали. При необходимости перейдите в /admin."

        for admin_id in config.ADMIN_IDS:
            if admin_id == user_id:
                continue
            try:
                await callback.bot.send_message(
                    admin_id,
                    admin_message,
                    reply_markup=keyboards.get_admin_new_order_keyboard(order_id)
                )
            except Exception as notify_error:
                logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {notify_error}")
 
        # Формируем сообщение для пользователя с информацией о заказе
        user_message = (
            f"✅ Ваш заказ №{order_id} создан и принят в очередь!\n\n"
            f"📋 Заказ №{order_id}\n\n"
            f"⚙️ Тип обработки: {order_type_name}\n"
            f"🧪 Материал: {material_name}\n"
            f"🔢 Количество: {quantity} шт.\n\n"
            f"Статус: 'В ожидании'.\n\n"
            f"Вы будете уведомлены об изменении статуса заказа."
        )
        
        # Добавляем кнопку для просмотра заказа
        keyboard = keyboards.get_order_detail_keyboard(order_id, "pending", is_admin=False)
        
        # Проверяем наличие фото и отправляем его, если есть
        photo_path = data.get('photo_path')
        if photo_path and Path(photo_path).exists():
            try:
                photo_file = FSInputFile(photo_path)
                # Удаляем старое сообщение и отправляем новое с фото
                try:
                    await callback.message.delete()
                except Exception:
                    pass  # Игнорируем ошибки при удалении
                
                await callback.bot.send_photo(
                    callback.message.chat.id,
                    photo_file,
                    caption=user_message,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке фото после создания заказа: {e}")
                # Если не удалось отправить фото, отправляем просто текст
                try:
                    await callback.message.edit_text(
                        user_message,
                        reply_markup=keyboard
                    )
                except TelegramBadRequest:
                    # Если сообщение не содержит текста, удаляем и отправляем новое
                    try:
                        await callback.message.delete()
                    except Exception:
                        pass
                    await callback.bot.send_message(
                        callback.message.chat.id,
                        user_message,
                        reply_markup=keyboard
                    )
        else:
            # Если фото нет, редактируем сообщение как обычно
            try:
                await callback.message.edit_text(
                    user_message,
                    reply_markup=keyboard
                )
            except TelegramBadRequest:
                # Если сообщение не содержит текста, удаляем и отправляем новое
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.bot.send_message(
                    callback.message.chat.id,
                    user_message,
                    reply_markup=keyboard
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
    archived_count = await database.db.count_user_archived_orders(user_id)
    
    if not orders and archived_count == 0:
        await message.answer("У вас пока нет заказов.")
        return
    
    text = "Ваши заказы:\n\n"
    if orders:
        text += "Выберите заказ для просмотра:"
    else:
        text += "У вас нет активных заказов."
    
    await message.answer(
        text,
        reply_markup=keyboards.get_orders_list_keyboard(orders, prefix="my_order", show_archive_button=archived_count > 0, show_back_button=False)
    )


@router.callback_query(F.data.startswith("my_order:"))
async def show_user_order_detail(callback: CallbackQuery):
    """Показать детали заказа пользователю"""
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order or order['user_id'] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    extra_buttons: list[tuple[str, str]] | None = None
    if callback.from_user.id in config.ADMIN_IDS:
        extra_buttons = [("🔧 Открыть админские действия", f"admin_view_from_user:{order_id}")]

    status_name = order.get('status_name') or 'Неизвестно'
    material_name = order.get('material_name') or 'Не указан'
    status_code = order.get('status_code', 'unknown')
    order_type_code = order.get('order_type', '3d_print')
    order_type_name = config.ORDER_TYPES.get(order_type_code, order_type_code)
    
    # Безопасное экранирование с проверкой на None
    created_at = order.get('created_at') or 'Не указана'
    part_name = order.get('part_name') or 'Не указано'
    quantity = order.get('quantity', 1)
    
    order_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {html.escape(str(created_at))}\n"
        f"⚙️ Тип: {html.escape(order_type_name)}\n"
        f"📦 Название детали: {html.escape(str(part_name))}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"📊 Статус: {html.escape(str(status_name))}\n"
        "\n"
        f"<b>Материал:</b>\n{html.escape(str(material_name))}"
    )
    
    if order.get('comment'):
        order_text += f"\n\n<b>Комментарий:</b>\n{html.escape(str(order['comment']))}"
    
    keyboard = keyboards.get_order_detail_keyboard(
        order_id,
        status_code,
        is_admin=False,
        extra_buttons=extra_buttons
    )
    
    # Проверяем наличие фото и отправляем его, если есть
    photo_path = order.get('photo_path')
    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            # Удаляем старое сообщение и отправляем новое с фото
            try:
                await callback.message.delete()
            except Exception:
                pass  # Игнорируем ошибки при удалении
            
            await callback.bot.send_photo(
                callback.message.chat.id,
                photo_file,
                caption=order_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото в деталях заказа: {e}")
            # Если не удалось отправить фото, редактируем сообщение как обычно
            try:
                await callback.message.edit_text(
                    order_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except TelegramBadRequest:
                # Если сообщение не содержит текста, удаляем и отправляем новое
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.bot.send_message(
                    callback.message.chat.id,
                    order_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
    else:
        # Если фото нет, редактируем сообщение как обычно
        try:
            await callback.message.edit_text(
                order_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            # Если сообщение не содержит текста, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.bot.send_message(
                callback.message.chat.id,
                order_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    
    await callback.answer()


@router.callback_query(F.data.startswith("user_cancel_order:"))
async def user_cancel_order(callback: CallbackQuery):
    """Обработка отмены заказа пользователем"""
    order_id = int(callback.data.split(":")[1])
    order = await database.db.get_order(order_id)
    
    if not order or order['user_id'] != callback.from_user.id:
        try:
            await callback.answer("Заказ не найден", show_alert=True)
        except Exception:
            pass
        return
    
    if order.get('status_code') != 'pending':
        try:
            await callback.answer("Отменить можно только заказы в статусе 'В ожидании'", show_alert=True)
        except Exception:
            pass
        return
    
    # Отвечаем на callback перед долгими операциями
    try:
        await callback.answer("Заказ отменен", show_alert=False)
    except Exception:
        pass  # Игнорируем ошибки при ответе на callback
    
    # Перемещаем заказ в архив с причиной "Отменен пользователем"
    success = await database.db.archive_order(order_id, "Отменен пользователем")
    
    if not success:
        logger.error(f"Ошибка при отмене заказа №{order_id}")
        return
    
    # Обновляем заказ и возвращаемся к списку заказов
    orders = await database.db.get_user_orders(callback.from_user.id)
    archived_count = await database.db.count_user_archived_orders(callback.from_user.id)
    
    text = "Ваши заказы:\n\n"
    if orders:
        text += "Выберите заказ для просмотра:"
    else:
        text += "У вас нет активных заказов."
    
    keyboard = keyboards.get_orders_list_keyboard(orders, prefix="my_order", show_archive_button=archived_count > 0, show_back_button=False)
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard
        )
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "no text in the message to edit" in error_text or "there is no text in the message to edit" in error_text:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.bot.send_message(
                callback.message.chat.id,
                text,
                reply_markup=keyboard
            )
        else:
            logger.warning(f"Ошибка при редактировании сообщения в user_cancel_order: {exc}")
    except Exception as exc:
        logger.error(f"Неожиданная ошибка в user_cancel_order: {exc}")


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
    """Вернуться к списку заказов пользователя (используется из архива)"""
    # Отвечаем на callback как можно раньше, чтобы избежать истечения таймаута
    try:
        await callback.answer()
    except Exception:
        pass  # Игнорируем ошибки при ответе на callback
    
    user_id = callback.from_user.id
    
    orders = await database.db.get_user_orders(user_id)
    archived_count = await database.db.count_user_archived_orders(user_id)
    
    if not orders and archived_count == 0:
        try:
            await callback.message.edit_text("У вас пока нет заказов.")
        except Exception as e:
            logger.warning(f"Ошибка при редактировании сообщения в user_back_to_orders: {e}")
        return
    
    text = "Ваши заказы:\n\n"
    if orders:
        text += "Выберите заказ для просмотра:"
    else:
        text += "У вас нет активных заказов."
    
    keyboard = keyboards.get_orders_list_keyboard(orders, prefix="my_order", show_archive_button=archived_count > 0, show_back_button=False)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard
        )
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        # Если сообщение не изменилось, просто игнорируем ошибку
        if "message is not modified" in error_text:
            return
        # Если сообщение не содержит текста (например, это фото), удаляем и отправляем новое
        if "no text in the message to edit" in error_text or "there is no text in the message to edit" in error_text:
            try:
                await callback.message.delete()
            except Exception:
                pass
            try:
                await callback.bot.send_message(
                    callback.message.chat.id,
                    text,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения в user_back_to_orders: {e}")
        else:
            # Для других ошибок просто логируем
            logger.warning(f"Ошибка при редактировании сообщения в user_back_to_orders: {exc}")
    except TelegramNetworkError as exc:
        # Сетевые ошибки - логируем и пытаемся отправить новое сообщение
        logger.warning(f"Сетевая ошибка в user_back_to_orders: {exc}")
        try:
            await callback.bot.send_message(
                callback.message.chat.id,
                text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения после сетевой ошибки в user_back_to_orders: {e}")
    except Exception as exc:
        logger.error(f"Неожиданная ошибка в user_back_to_orders: {exc}")
        try:
            await callback.bot.send_message(
                callback.message.chat.id,
                text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения после ошибки в user_back_to_orders: {e}")


async def _show_user_archived_orders_page(callback: CallbackQuery, page: int = 0, orders_per_page: int = 6):
    """Показать страницу с архивными заказами пользователя"""
    user_id = callback.from_user.id
    
    total_count = await database.db.count_user_archived_orders(user_id)
    
    if total_count == 0:
        orders = await database.db.get_user_orders(user_id)
        archived_count = await database.db.count_user_archived_orders(user_id)
        
        text = "📦 Архив\n\nУ вас нет архивных заказов.\n\nВаши заказы:\n\n"
        if orders:
            text += "Выберите заказ для просмотра:"
        else:
            text += "У вас нет активных заказов."
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.get_orders_list_keyboard(orders, prefix="my_order", show_archive_button=archived_count > 0, show_back_button=False)
        )
        await callback.answer("Архив пуст")
        return
    
    total_pages = (total_count + orders_per_page - 1) // orders_per_page if total_count > 0 else 1
    page = min(page, max(total_pages - 1, 0))
    offset = page * orders_per_page
    
    orders = await database.db.get_user_archived_orders(user_id, limit=orders_per_page, offset=offset)
    
    if not orders and page > 0:
        # Если после удаления заказов текущая страница опустела, пробуем предыдущую
        await _show_user_archived_orders_page(callback, page=page - 1, orders_per_page=orders_per_page)
        return
    
    start_num = page * orders_per_page + 1
    end_num = min((page + 1) * orders_per_page, total_count)
    
    orders_text = (
        f"📦 Архив\n\n"
        f"Заказы {start_num}-{end_num} из {total_count}\n"
        f"Страница {page + 1} из {total_pages}\n\n"
        "Выберите заказ для просмотра:"
    )
    
    orders_keyboard = keyboards.get_orders_list_keyboard(
        orders,
        prefix="user_archived_order",
        current_page=page,
        total_pages=total_pages,
        back_callback="user_back_to_orders",
        back_text="⬅️ К заказам",
        show_back_button=True
    )
    
    try:
        await callback.message.edit_text(
            orders_text,
            reply_markup=orders_keyboard
        )
    except TelegramBadRequest as exc:
        error_text = str(exc)
        if "message is not modified" in error_text:
            await callback.answer("Эта страница уже открыта.")
            return
        if "no text in the message to edit" in error_text or "there is no text in the message to edit" in error_text:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.bot.send_message(
                callback.message.chat.id,
                orders_text,
                reply_markup=orders_keyboard
            )
        else:
            raise


@router.callback_query(F.data.startswith("user_archived_orders:"))
async def show_user_archived_orders(callback: CallbackQuery):
    """Показать архивные заказы пользователя (первая страница)"""
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        page = 0
    
    await _show_user_archived_orders_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("user_archived_orders_page:"))
async def show_user_archived_orders_page(callback: CallbackQuery):
    """Показать конкретную страницу с архивными заказами пользователя"""
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        page = 0
    
    await _show_user_archived_orders_page(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("user_archived_order:"))
async def show_user_archived_order_detail(callback: CallbackQuery):
    """Показать детали архивного заказа пользователю"""
    try:
        parts = callback.data.split(":")
        order_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    
    order = await database.db.get_order(order_id)
    
    if not order or order['user_id'] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    if order.get('status_code') != 'archived':
        await callback.answer("Этот заказ не в архиве", show_alert=True)
        return
    
    extra_buttons: list[tuple[str, str]] | None = None
    if callback.from_user.id in config.ADMIN_IDS:
        extra_buttons = [("🔧 Открыть админские действия", f"admin_view_from_user:{order_id}")]

    status_name = order.get('status_name') or 'Неизвестно'
    material_name = order.get('material_name') or 'Не указан'
    status_code = order.get('status_code', 'unknown')
    order_type_code = order.get('order_type', '3d_print')
    order_type_name = config.ORDER_TYPES.get(order_type_code, order_type_code)
    
    # Безопасное экранирование с проверкой на None
    created_at = order.get('created_at') or 'Не указана'
    part_name = order.get('part_name') or 'Не указано'
    quantity = order.get('quantity', 1)
    
    order_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {html.escape(str(created_at))}\n"
        f"⚙️ Тип: {html.escape(order_type_name)}\n"
        f"📦 Название детали: {html.escape(str(part_name))}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"📊 Статус: {html.escape(str(status_name))}\n"
        "\n"
        f"<b>Материал:</b>\n{html.escape(str(material_name))}"
    )
    
    if order.get('photo_caption'):
        order_text += f"\n\n📝 Подпись к фото: {html.escape(str(order['photo_caption']))}"
    
    if order.get('comment'):
        order_text += f"\n\n<b>Комментарий:</b>\n{html.escape(str(order['comment']))}"
    
    if order.get('rejection_reason'):
        order_text += f"\n\n❌ Причина отклонения: {html.escape(str(order['rejection_reason']))}"
    
    keyboard = keyboards.get_order_detail_keyboard(
        order_id,
        status_code,
        is_admin=False,
        show_list_back=True,
        extra_buttons=[("⬅️ К архиву", f"user_archived_orders:{page}")] + (extra_buttons or [])
    )
    
    photo_path = order.get('photo_path')
    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            # Удаляем старое сообщение и отправляем новое с фото
            try:
                await callback.message.delete()
            except Exception:
                pass  # Игнорируем ошибки при удалении
            
            await callback.bot.send_photo(
                callback.message.chat.id,
                photo_file,
                caption=order_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото в деталях архивного заказа: {e}")
            # Если не удалось отправить фото, редактируем сообщение как обычно
            try:
                await callback.message.edit_text(
                    order_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except TelegramBadRequest:
                # Если сообщение не содержит текста, удаляем и отправляем новое
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                await callback.bot.send_message(
                    callback.message.chat.id,
                    order_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
    else:
        # Если фото нет, редактируем сообщение как обычно
        try:
            await callback.message.edit_text(
                order_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            # Если сообщение не содержит текста, удаляем и отправляем новое
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.bot.send_message(
                callback.message.chat.id,
                order_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    
    await callback.answer()

