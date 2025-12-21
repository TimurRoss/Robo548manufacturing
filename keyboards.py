"""
Модуль для создания клавиатур бота
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import config


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню для пользователей"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Создать заказ 3д печать"))
    builder.add(KeyboardButton(text="Создать заказ на лазерную резку"))
    builder.add(KeyboardButton(text="Мои заказы"))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню для администраторов"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Админ-панель"))
    builder.add(KeyboardButton(text="Создать заказ 3д печать"))
    builder.add(KeyboardButton(text="Создать заказ на лазерную резку"))
    builder.add(KeyboardButton(text="Мои заказы"))
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)


def get_admin_main_keyboard(orders_enabled: bool = True) -> InlineKeyboardMarkup:
    """Главное меню админ-панели"""
    builder = InlineKeyboardBuilder()
    toggle_text = "🟢 Приём заказов: открыт" if orders_enabled else "🔴 Приём заказов: закрыт"
    builder.add(InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders_menu"))
    builder.add(InlineKeyboardButton(text="🔧 Управление материалами", callback_data="admin_manage_materials"))
    builder.add(InlineKeyboardButton(text="📝 Шаблоны отклонения", callback_data="admin_manage_rejection_templates_menu"))
    builder.add(InlineKeyboardButton(text=toggle_text, callback_data="admin_toggle_orders"))
    builder.add(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    builder.adjust(1, 1, 1, 1, 1)
    return builder.as_markup()


def get_admin_new_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура уведомления о новом заказе"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="▶️ Раскрыть заказ", callback_data=f"admin_expand_order:{order_id}"))
    builder.adjust(1)
    return builder.as_markup()


def get_broadcast_cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для отмены или выхода из режима рассылки"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_broadcast_cancel"))
    builder.adjust(1)
    return builder.as_markup()


def get_order_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа заказа для пользователя"""
    builder = InlineKeyboardBuilder()
    for order_type, title in config.ORDER_TYPES.items():
        builder.add(InlineKeyboardButton(text=title, callback_data=f"select_order_type:{order_type}"))
    builder.adjust(1)
    return builder.as_markup()


def get_quantity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества деталей"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="1 шт.", callback_data="select_quantity:1"))
    builder.add(InlineKeyboardButton(text="2 шт.", callback_data="select_quantity:2"))
    builder.add(InlineKeyboardButton(text="3 шт.", callback_data="select_quantity:3"))
    builder.add(InlineKeyboardButton(text="5 шт.", callback_data="select_quantity:5"))
    builder.adjust(2, 2)
    return builder.as_markup()


def get_admin_order_types_keyboard(order_stats: dict, archived_counts: dict) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа заказов для админ-панели"""
    builder = InlineKeyboardBuilder()
    for order_type, title in config.ORDER_TYPES.items():
        orders_total = order_stats.get(order_type, {}).get("all", 0)
        archived_total = archived_counts.get(order_type, 0)
        total = orders_total + archived_total
        button_text = f"{title} ({total} шт)" if total > 0 else title
        builder.add(InlineKeyboardButton(text=button_text, callback_data=f"admin_orders_type:{order_type}"))
    builder.add(InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order"))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()


def get_admin_orders_keyboard(stats: dict, archived_count: int, order_type: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора раздела заказов внутри конкретного типа"""
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(
        text="🔍 По материалу",
        callback_data=f"admin_orders_materials:{order_type}"
    ))

    all_count = stats.get("all", 0)
    pending_count = stats.get("pending", 0)
    in_progress_count = stats.get("in_progress", 0)
    ready_count = stats.get("ready", 0)

    builder.add(InlineKeyboardButton(
        text=f"Все заказы ({all_count} шт)" if all_count > 0 else "Все заказы",
        callback_data=f"admin_orders:{order_type}:all"
    ))
    builder.add(InlineKeyboardButton(
        text=f"В ожидании ({pending_count} шт)" if pending_count > 0 else "В ожидании",
        callback_data=f"admin_orders:{order_type}:pending"
    ))
    builder.add(InlineKeyboardButton(
        text=f"В работе ({in_progress_count} шт)" if in_progress_count > 0 else "В работе",
        callback_data=f"admin_orders:{order_type}:in_progress"
    ))
    builder.add(InlineKeyboardButton(
        text=f"Готов ({ready_count} шт)" if ready_count > 0 else "Готов",
        callback_data=f"admin_orders:{order_type}:ready"
    ))
    builder.add(InlineKeyboardButton(
        text=f"📦 Архив ({archived_count} шт)" if archived_count > 0 else "📦 Архив",
        callback_data=f"admin_orders:{order_type}:archived"
    ))
    builder.add(InlineKeyboardButton(text="⬅️ К типам заказов", callback_data="admin_back_to_order_types"))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 1, 2, 2, 1, 1)
    return builder.as_markup()


def get_orders_list_keyboard(
    orders: list,
    prefix: str = "order",
    status_code: str | None = None,
    current_page: int = 0,
    total_pages: int = 1,
    order_type: str | None = None,
    back_callback: str | None = None,
    back_text: str = "⬅️ Назад",
    show_archive_button: bool = False,
    show_back_button: bool = True
) -> InlineKeyboardMarkup:
    """Клавиатура со списком заказов с пагинацией"""
    builder = InlineKeyboardBuilder()

    for order in orders:
        order_id = order["id"]
        status_name = order.get("status_name", "Без статуса")
        text = f"Заказ №{order_id} ({status_name})"

        if prefix == "admin_order":
            callback_data = f"admin_order:{order_type}:{status_code}:{order_id}:{current_page}"
        elif prefix == "user_archived_order":
            callback_data = f"user_archived_order:{order_id}:{current_page}"
        else:
            callback_data = f"{prefix}:{order_id}"

        builder.add(InlineKeyboardButton(text=text, callback_data=callback_data))

    nav_buttons_count = 0
    if total_pages > 1:
        nav_buttons = []

        if current_page > 0:
            if prefix == "admin_order":
                callback_data = f"admin_orders_page:{order_type}:{status_code}:{current_page - 1}"
            elif prefix == "user_archived_order":
                callback_data = f"user_archived_orders_page:{current_page - 1}"
            else:
                callback_data = "noop"
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data))
            nav_buttons_count += 1
        else:
            nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            nav_buttons_count += 1

        nav_buttons.append(InlineKeyboardButton(text=f"{current_page + 1}/{total_pages}", callback_data="noop"))
        nav_buttons_count += 1

        if current_page < total_pages - 1:
            if prefix == "admin_order":
                callback_data = f"admin_orders_page:{order_type}:{status_code}:{current_page + 1}"
            elif prefix == "user_archived_order":
                callback_data = f"user_archived_orders_page:{current_page + 1}"
            else:
                callback_data = "noop"
            nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=callback_data))
            nav_buttons_count += 1
        else:
            nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="noop"))
            nav_buttons_count += 1

        builder.add(*nav_buttons)

    if prefix == "admin_order":
        if back_callback:
            builder.add(InlineKeyboardButton(text=back_text, callback_data=back_callback))
    elif show_back_button and back_callback:
        # Для пользовательских заказов добавляем кнопку "Назад" только если явно указано (для архива)
        builder.add(InlineKeyboardButton(text=back_text, callback_data=back_callback))
    
    # Добавляем кнопку "Архив" если нужно
    if show_archive_button:
        builder.add(InlineKeyboardButton(text="📦 Архив", callback_data="user_archived_orders:0"))

    orders_count = len(orders)
    
    # Формируем параметры для adjust
    adjust_params = []
    
    # Добавляем кнопки заказов (по одной на строку)
    if orders_count > 0:
        adjust_params.extend([1] * orders_count)
    
    # Добавляем навигационные кнопки (все в одной строке)
    if nav_buttons_count > 0:
        adjust_params.append(nav_buttons_count)
    
    # Добавляем кнопку "Назад" (в одной строке) для админов и для архива пользователей
    if (prefix == "admin_order" and back_callback) or (show_back_button and back_callback):
        adjust_params.append(1)
    
    # Добавляем кнопку "Архив" (в одной строке), если нужно
    if show_archive_button:
        adjust_params.append(1)

    # Если adjust_params пуст (не должно быть, но на всякий случай), добавляем хотя бы один элемент
    if not adjust_params:
        adjust_params = [1]

    builder.adjust(*adjust_params)
    return builder.as_markup()


def get_order_detail_keyboard(
    order_id: int,
    current_status: str,
    is_admin: bool = True,
    order_type: str | None = None,
    list_status: str | None = None,
    current_page: int | None = None,
    show_list_back: bool = True,
    extra_buttons: list[tuple[str, str]] | None = None
) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра заказа"""
    builder = InlineKeyboardBuilder()

    back_status = list_status or current_status
    page_token = current_page if current_page is not None else 0

    if current_status == "archived":
        if is_admin:
            builder.row(InlineKeyboardButton(text="Скачать модель", callback_data=f"download_model:{order_id}"))
            if show_list_back:
                if order_type:
                    builder.row(InlineKeyboardButton(
                        text="⬅️ Назад к списку",
                        callback_data=f"admin_back_to_orders:{order_type}:{back_status}:{page_token}"
                    ))
                else:
                    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_orders"))
        # Для пользователей не добавляем кнопку "Назад" в архивных заказах

        if extra_buttons:
            for text, callback in extra_buttons:
                builder.row(InlineKeyboardButton(text=text, callback_data=callback))
        return builder.as_markup()

    if is_admin:
        builder.row(InlineKeyboardButton(text="Скачать модель", callback_data=f"download_model:{order_id}"))

        if current_status == "pending":
            reject_callback = f"reject_order:{order_id}"
            if order_type and show_list_back:
                reject_callback = f"reject_order:{order_id}:{order_type}:{back_status}:{page_token}"
            builder.row(
                InlineKeyboardButton(text="Принять в работу", callback_data=f"set_status:{order_id}:in_progress"),
                InlineKeyboardButton(text="Отклонить", callback_data=reject_callback)
            )
        elif current_status == "in_progress":
            builder.row(
                InlineKeyboardButton(text="Готов", callback_data=f"set_status:{order_id}:ready"),
                InlineKeyboardButton(text="В ожидании", callback_data=f"set_status:{order_id}:pending")
            )
        elif current_status == "ready":
            builder.row(
                InlineKeyboardButton(text="В работу", callback_data=f"set_status:{order_id}:in_progress"),
                InlineKeyboardButton(text="✅ Забрал", callback_data=f"admin_picked_up:{order_id}")
            )

        if show_list_back:
            if order_type:
                builder.row(InlineKeyboardButton(
                    text="⬅️ Назад к списку",
                    callback_data=f"admin_back_to_orders:{order_type}:{back_status}:{page_token}"
                ))
            else:
                builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_orders"))
    else:
        # Для пользователей добавляем кнопки в зависимости от статуса
        if current_status == "pending":
            builder.row(InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"user_cancel_order:{order_id}"))
        elif current_status == "ready":
            builder.row(InlineKeyboardButton(text="✅ Забрал", callback_data=f"user_picked_up:{order_id}"))
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="user_back_to_orders"))

    if extra_buttons:
        for text, callback in extra_buttons:
            builder.row(InlineKeyboardButton(text=text, callback_data=callback))

    return builder.as_markup()


def get_materials_keyboard(materials: list) -> InlineKeyboardMarkup:
    """Клавиатура для выбора материала"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material["name"],
            callback_data=f"select_material:{material['id']}"
        ))
    builder.adjust(2)
    return builder.as_markup()


def get_skip_comment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пропуска комментария"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Пропустить", callback_data="skip_comment"))
    builder.adjust(1)
    return builder.as_markup()


def get_confirm_order_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения заказа"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
    builder.adjust(2)
    return builder.as_markup()


def get_admin_materials_type_keyboard(material_counts: dict) -> InlineKeyboardMarkup:
    """Клавиатура выбора типа материалов"""
    builder = InlineKeyboardBuilder()
    laser_count = material_counts.get("laser_cut", 0)
    print_count = material_counts.get("3d_print", 0)

    builder.add(InlineKeyboardButton(
        text=f"Для 3D печати ({print_count})" if print_count > 0 else "Для 3D печати",
        callback_data="admin_materials_type:3d_print"
    ))
    builder.add(InlineKeyboardButton(
        text=f"Для лазерной резки ({laser_count})" if laser_count > 0 else "Для лазерной резки",
        callback_data="admin_materials_type:laser_cut"
    ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_manage_materials_keyboard(material_type: str) -> InlineKeyboardMarkup:
    """Клавиатура управления материалами для выбранного типа"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Добавить материал", callback_data=f"admin_add_material:{material_type}"))
    builder.add(InlineKeyboardButton(text="Удалить материал", callback_data=f"admin_delete_material:{material_type}"))
    builder.add(InlineKeyboardButton(text="Вернуть доступ", callback_data=f"admin_restore_material:{material_type}"))
    builder.add(InlineKeyboardButton(text="⬅️ К выбору типа", callback_data="admin_back_to_material_types"))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 1, 1, 1, 1)
    return builder.as_markup()


def get_admin_orders_materials_keyboard(materials: list, order_type: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора материала для фильтрации заказов"""
    builder = InlineKeyboardBuilder()

    for material in materials:
        name = material["name"]
        if not material.get("is_available", 1):
            name = f"{name} (недоступен)"
        builder.add(InlineKeyboardButton(
            text=name,
            callback_data=f"admin_orders_material:{order_type}:{material['id']}"
        ))

    back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_back_to_statuses:{order_type}")
    builder.add(back_button)

    if materials:
        builder.adjust(2, 1)
    else:
        builder.adjust(1, 1)

    return builder.as_markup()


def get_delete_materials_keyboard(materials: list, material_type: str) -> InlineKeyboardMarkup:
    """Клавиатура для удаления материалов выбранного типа"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material["name"],
            callback_data=f"delete_material:{material_type}:{material['id']}"
        ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_materials_back:{material_type}"))
    builder.adjust(1)
    return builder.as_markup()


def get_restore_materials_keyboard(materials: list, material_type: str) -> InlineKeyboardMarkup:
    """Клавиатура для восстановления материалов выбранного типа"""
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.add(InlineKeyboardButton(
            text=material["name"],
            callback_data=f"restore_material:{material_type}:{material['id']}"
        ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_materials_back:{material_type}"))
    builder.adjust(1)
    return builder.as_markup()


def get_rejection_templates_keyboard(templates: list, order_id: int, order_type: str, list_status: str = None, list_page: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для выбора шаблонного комментария отклонения"""
    builder = InlineKeyboardBuilder()
    
    list_status_str = list_status if list_status else ''
    
    for template in templates:
        # Обрезаем текст шаблона для кнопки (максимум 50 символов)
        template_text = template["text"]
        if len(template_text) > 50:
            template_text = template_text[:47] + "..."
        builder.add(InlineKeyboardButton(
            text=template_text,
            callback_data=f"use_rejection_template:{order_id}:{template['id']}:{order_type}:{list_status_str}:{list_page}"
        ))
    
    builder.add(InlineKeyboardButton(
        text="✏️ Ввести свой комментарий",
        callback_data=f"reject_order_custom:{order_id}:{order_type}:{list_status_str}:{list_page}"
    ))
    builder.adjust(1)
    return builder.as_markup()


def get_rejection_template_management_keyboard(order_type: str) -> InlineKeyboardMarkup:
    """Клавиатура управления шаблонами отклонения для типа заказа"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="➕ Добавить шаблон",
        callback_data=f"admin_add_rejection_template:{order_type}"
    ))
    builder.add(InlineKeyboardButton(
        text="🗑️ Удалить шаблон",
        callback_data=f"admin_delete_rejection_template:{order_type}"
    ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_delete_rejection_templates_keyboard(templates: list, order_type: str) -> InlineKeyboardMarkup:
    """Клавиатура для удаления шаблонов отклонения"""
    builder = InlineKeyboardBuilder()
    for template in templates:
        # Обрезаем текст шаблона для кнопки (максимум 50 символов)
        template_text = template["text"]
        if len(template_text) > 50:
            template_text = template_text[:47] + "..."
        builder.add(InlineKeyboardButton(
            text=template_text,
            callback_data=f"delete_rejection_template:{order_type}:{template['id']}"
        ))
    builder.add(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=f"admin_manage_rejection_templates:{order_type}"
    ))
    builder.adjust(1)
    return builder.as_markup()


def get_rejection_template_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа заказа для управления шаблонами отклонения"""
    builder = InlineKeyboardBuilder()
    for order_type, title in config.ORDER_TYPES.items():
        builder.add(InlineKeyboardButton(
            text=title,
            callback_data=f"admin_manage_rejection_templates:{order_type}"
        ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_rejected_order_notification_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для уведомления об отклонении заказа"""
    # Клавиатура без кнопок - пользователь может использовать команду "Мои заказы" из меню
    builder = InlineKeyboardBuilder()
    return builder.as_markup()
