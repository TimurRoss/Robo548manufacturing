"""
Модуль для создания клавиатур бота
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню для пользователей"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Создать заказ"))
    builder.add(KeyboardButton(text="Мои заказы"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню для администраторов"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Админ-панель"))
    builder.add(KeyboardButton(text="Создать заказ"))
    builder.add(KeyboardButton(text="Мои заказы"))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders_menu"))
    builder.add(InlineKeyboardButton(text="🔧 Управление материалами", callback_data="admin_manage_materials"))
    builder.adjust(1, 1)
    return builder.as_markup()


def get_admin_orders_keyboard(stats: dict = None, archived_count: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для выбора фильтра заказов в админ-панели"""
    builder = InlineKeyboardBuilder()
    
    # Если статистика не передана, используем пустые значения
    if stats is None:
        stats = {}
    
    all_count = stats.get('all', 0)
    pending_count = stats.get('pending', 0)
    in_progress_count = stats.get('in_progress', 0)
    ready_count = stats.get('ready', 0)
    
    builder.add(InlineKeyboardButton(
        text=f"Все заказы ({all_count} шт)" if all_count > 0 else "Все заказы",
        callback_data="admin_orders:all"
    ))
    builder.add(InlineKeyboardButton(
        text=f"В ожидании ({pending_count} шт)" if pending_count > 0 else "В ожидании",
        callback_data="admin_orders:pending"
    ))
    builder.add(InlineKeyboardButton(
        text=f"В работе ({in_progress_count} шт)" if in_progress_count > 0 else "В работе",
        callback_data="admin_orders:in_progress"
    ))
    builder.add(InlineKeyboardButton(
        text=f"Готов ({ready_count} шт)" if ready_count > 0 else "Готов",
        callback_data="admin_orders:ready"
    ))
    builder.add(InlineKeyboardButton(
        text=f"📦 Архив ({archived_count} шт)" if archived_count > 0 else "📦 Архив",
        callback_data="admin_orders:archived"
    ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 2, 2, 1)
    return builder.as_markup()


def get_orders_list_keyboard(
    orders: list, 
    prefix: str = "order", 
    status_code: str = None,
    current_page: int = 0,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """Клавиатура со списком заказов с пагинацией"""
    builder = InlineKeyboardBuilder()
    
    # Добавляем заказы (в столбик - по 1 кнопке в ряд)
    for order in orders:
        order_id = order['id']
        status_name = order.get('status_name', 'Без статуса')
        text = f"Заказ №{order_id} ({status_name})"
        builder.add(InlineKeyboardButton(text=text, callback_data=f"{prefix}:{order_id}"))
    
    # Добавляем кнопки навигации если есть несколько страниц
    nav_buttons_count = 0
    if total_pages > 1:
        nav_buttons = []
        
        # Кнопка "Назад"
        if current_page > 0:
            callback_data = f"admin_orders_page:{status_code}:{current_page - 1}"
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data))
            nav_buttons_count += 1
        else:
            # Пустая кнопка для выравнивания
            nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            nav_buttons_count += 1
        
        # Информация о странице
        nav_buttons.append(InlineKeyboardButton(text=f"{current_page + 1}/{total_pages}", callback_data="noop"))
        nav_buttons_count += 1
        
        # Кнопка "Вперед"
        if current_page < total_pages - 1:
            callback_data = f"admin_orders_page:{status_code}:{current_page + 1}"
            nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=callback_data))
            nav_buttons_count += 1
        else:
            # Пустая кнопка для выравнивания
            nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            nav_buttons_count += 1
        
        builder.add(*nav_buttons)
    
    # Кнопка "Назад к списку"
    builder.add(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_orders"))
    
    # Настраиваем расположение: все заказы по 1 в ряд (столбик), навигация по 3 в ряд, кнопка "Назад" отдельно
    orders_count = len(orders)
    adjust_params = [1] * orders_count  # Каждый заказ по 1 кнопке в ряд
    if nav_buttons_count > 0:
        adjust_params.append(nav_buttons_count)  # Все кнопки навигации в один ряд
    adjust_params.append(1)  # Кнопка "Назад к списку" отдельно
    
    builder.adjust(*adjust_params)
    return builder.as_markup()


def get_order_detail_keyboard(order_id: int, current_status: str, is_admin: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра заказа"""
    builder = InlineKeyboardBuilder()
    
    # Для архивированных заказов показываем только кнопку "Назад"
    if current_status == "archived":
        if is_admin:
            builder.add(InlineKeyboardButton(text="Скачать модель", callback_data=f"download_model:{order_id}"))
            builder.add(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_orders"))
            builder.adjust(1, 1)
        else:
            builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="user_back_to_orders"))
            builder.adjust(1)
        return builder.as_markup()
    
    if is_admin:
        builder.add(InlineKeyboardButton(text="Скачать модель", callback_data=f"download_model:{order_id}"))
        
        if current_status == "pending":
            builder.add(InlineKeyboardButton(text="Принять в работу", callback_data=f"set_status:{order_id}:in_progress"))
            builder.add(InlineKeyboardButton(text="Отклонить", callback_data=f"reject_order:{order_id}"))
        elif current_status == "in_progress":
            builder.add(InlineKeyboardButton(text="Готов", callback_data=f"set_status:{order_id}:ready"))
            builder.add(InlineKeyboardButton(text="В ожидании", callback_data=f"set_status:{order_id}:pending"))
        elif current_status == "ready":
            builder.add(InlineKeyboardButton(text="В работу", callback_data=f"set_status:{order_id}:in_progress"))
            builder.add(InlineKeyboardButton(text="✅ Забрал", callback_data=f"admin_picked_up:{order_id}"))
        
        builder.add(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_orders"))
        builder.adjust(1, 2, 1)
    else:
        # Для пользователя
        if current_status == "ready":
            builder.add(InlineKeyboardButton(text="✅ Забрал", callback_data=f"user_picked_up:{order_id}"))
        builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="user_back_to_orders"))
        builder.adjust(1, 1)
    
    return builder.as_markup()


def get_materials_keyboard(materials: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора материала (цвет + тип)"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material['name'],
            callback_data=f"select_material:{material['id']}"
        ))
    builder.adjust(2)
    return builder.as_markup()


def get_confirm_order_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения заказа"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
    builder.adjust(2)
    return builder.as_markup()


def get_manage_materials_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для управления материалами"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Добавить материал", callback_data="admin_add_material"))
    builder.add(InlineKeyboardButton(text="Удалить материал", callback_data="admin_delete_material"))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(2, 1)
    return builder.as_markup()


def get_delete_materials_keyboard(materials: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора материала для удаления"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material['name'],
            callback_data=f"delete_material:{material['id']}"
        ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_materials"))
    builder.adjust(2, 1)
    return builder.as_markup()

