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


def get_admin_orders_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора фильтра заказов в админ-панели"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="В ожидании", callback_data="admin_orders:pending"))
    builder.add(InlineKeyboardButton(text="В работе", callback_data="admin_orders:in_progress"))
    builder.add(InlineKeyboardButton(text="Готов", callback_data="admin_orders:ready"))
    builder.add(InlineKeyboardButton(text="Отклонен", callback_data="admin_orders:rejected"))
    builder.add(InlineKeyboardButton(text="Все заказы", callback_data="admin_orders:all"))
    builder.add(InlineKeyboardButton(text="Управление материалами", callback_data="admin_manage_materials"))
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_orders_list_keyboard(orders: list, prefix: str = "order") -> InlineKeyboardMarkup:
    """Клавиатура со списком заказов"""
    builder = InlineKeyboardBuilder()
    for order in orders:
        order_id = order['id']
        status_name = order.get('status_name', 'Без статуса')
        text = f"Заказ №{order_id} ({status_name})"
        builder.add(InlineKeyboardButton(text=text, callback_data=f"{prefix}:{order_id}"))
    builder.adjust(1)
    return builder.as_markup()


def get_order_detail_keyboard(order_id: int, current_status: str) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра заказа администратором"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Скачать модель", callback_data=f"download_model:{order_id}"))
    
    if current_status == "pending":
        builder.add(InlineKeyboardButton(text="Принять в работу", callback_data=f"set_status:{order_id}:in_progress"))
        builder.add(InlineKeyboardButton(text="Отклонить", callback_data=f"set_status:{order_id}:rejected"))
    elif current_status == "in_progress":
        builder.add(InlineKeyboardButton(text="Готов", callback_data=f"set_status:{order_id}:ready"))
        builder.add(InlineKeyboardButton(text="В ожидании", callback_data=f"set_status:{order_id}:pending"))
    elif current_status == "ready":
        builder.add(InlineKeyboardButton(text="В работу", callback_data=f"set_status:{order_id}:in_progress"))
    
    builder.add(InlineKeyboardButton(text="Назад к списку", callback_data="admin_back_to_orders"))
    builder.adjust(1, 2, 1)
    return builder.as_markup()


def get_materials_keyboard(materials: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа материала"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material['name'],
            callback_data=f"select_material:{material['id']}"
        ))
    builder.adjust(2)
    return builder.as_markup()


def get_colors_keyboard(colors: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора цвета"""
    builder = InlineKeyboardBuilder()
    for color in colors:
        builder.add(InlineKeyboardButton(
            text=color['name'],
            callback_data=f"select_color:{color['id']}"
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
    builder.add(InlineKeyboardButton(text="Добавить тип пластика", callback_data="admin_add_material"))
    builder.add(InlineKeyboardButton(text="Удалить тип пластика", callback_data="admin_delete_material"))
    builder.add(InlineKeyboardButton(text="Добавить цвет", callback_data="admin_add_color"))
    builder.add(InlineKeyboardButton(text="Удалить цвет", callback_data="admin_delete_color"))
    builder.add(InlineKeyboardButton(text="Назад", callback_data="admin_back_to_menu"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_delete_materials_keyboard(materials: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора материала для удаления"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material['name'],
            callback_data=f"delete_material:{material['id']}"
        ))
    builder.add(InlineKeyboardButton(text="Назад", callback_data="admin_manage_materials"))
    builder.adjust(2, 1)
    return builder.as_markup()


def get_delete_colors_keyboard(colors: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора цвета для удаления"""
    builder = InlineKeyboardBuilder()
    for color in colors:
        builder.add(InlineKeyboardButton(
            text=color['name'],
            callback_data=f"delete_color:{color['id']}"
        ))
    builder.add(InlineKeyboardButton(text="Назад", callback_data="admin_manage_materials"))
    builder.adjust(2, 1)
    return builder.as_markup()

