"""
Обработчики для администраторов
"""
import asyncio
import html

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup
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


def _build_admin_new_order_summary(order: dict) -> str:
    """Краткое описание заказа для уведомления"""
    order_type_code = order.get('order_type', '3d_print')
    order_type_name = config.ORDER_TYPES.get(order_type_code, order_type_code)
    material_name = order.get('material_name') or "Не указан"
    first_name = (order.get('first_name') or "").strip()
    last_name = (order.get('last_name') or "").strip()
    full_name = f"{first_name} {last_name}".strip() or "Не указан"
    username = order.get('username')
    if username:
        customer = f"{full_name} (@{username})"
    else:
        customer = full_name

    summary = (
        f"🆕 Заказ №{order['id']}\n\n"
        f"⚙️ Тип: {order_type_name}\n"
        f"📦 Деталь: {order.get('part_name', '—')}\n"
        f"🧪 Материал: {material_name}\n"
        f"👤 Клиент: {customer} (ID: {order.get('user_id')})\n"
    )

    comment = order.get('comment')
    if comment:
        summary += f"💬 Комментарий: {comment}\n"

    summary += "\nНажмите «Раскрыть заказ», чтобы посмотреть подробности."
    return summary


def _build_admin_order_detail_payload(
    order: dict,
    *,
    order_type: str | None = None,
    list_status: str | None = None,
    current_page: int | None = None,
    show_list_back: bool = True,
    extra_buttons: list[tuple[str, str]] | None = None
) -> tuple[str, InlineKeyboardMarkup, str | None, str]:
    """Подготовить подробное описание заказа и клавиатуру"""
    status_code = order.get('status_code', 'unknown')
    status_name = order.get('status_name', 'Неизвестно')
    material_name = order.get('material_name') or "Не указан"
    order_type_code = order.get('order_type', order_type or '3d_print')
    order_type_name = config.ORDER_TYPES.get(order_type_code, order_type_code)

    full_name = f"{order.get('first_name', '')} {order.get('last_name', '')}".strip()
    full_name_html = html.escape(full_name) if full_name else "—"
    username_value = order.get('username')
    if username_value:
        user_line = f"{full_name_html} (@{html.escape(username_value)})"
    else:
        user_line = full_name_html
    user_info = f"{user_line}\n🆔 Telegram ID: {order['user_id']}"

    detail_text = (
        f"📋 Заказ №{order['id']}\n\n"
        f"📅 Дата создания: {html.escape(order.get('created_at', '—'))}\n"
        f"👤 Заказчик: {user_info}\n"
        f"⚙️ Тип: {html.escape(order_type_name)}\n"
        f"📦 Название детали: {html.escape(order.get('part_name', '—'))}\n"
        f"📊 Статус: {html.escape(status_name)}\n"
    )

    if order.get('photo_caption'):
        detail_text += f"📝 Подпись к фото: {html.escape(order['photo_caption'])}\n"

    material_display = material_name or "Не указан"
    detail_text += (
        "\n"
        f"<b>Материал:</b>\n{html.escape(material_display)}"
    )

    if order.get('comment'):
        detail_text += f"\n\n<b>Комментарий:</b>\n{html.escape(order['comment'])}"

    if order.get('rejection_reason'):
        detail_text += f"\n\n❌ Причина отклонения: {html.escape(order['rejection_reason'])}\n"

    back_order_type = order_type if show_list_back else None
    if show_list_back and back_order_type is None:
        back_order_type = order_type_code

    keyboard = keyboards.get_order_detail_keyboard(
        order['id'],
        status_code,
        is_admin=True,
        order_type=back_order_type,
        list_status=list_status,
        current_page=current_page,
        show_list_back=show_list_back,
        extra_buttons=extra_buttons
    )

    photo_path = order.get('photo_path')
    return detail_text, keyboard, photo_path, status_name


@router.callback_query(F.data.startswith("admin_materials_back:"))
async def materials_back_to_list(callback: CallbackQuery, state: FSMContext):
    """Вернуться к списку материалов после действий"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    material_type = callback.data.split(":")[1]
    await state.update_data(material_management_type=material_type)

    materials = await database.db.get_materials_with_usage_count(material_type)
    if material_type == "laser_cut":
        header = "Материалы для лазерной резки"
    else:
        header = "Материалы для 3D печати"

    if materials:
        materials_text = f"📋 {header}:\n\n"
        for material in materials:
            usage_count = material.get('usage_count', 0)
            availability_suffix = "" if material.get('is_available', 1) else " (недоступен)"
            materials_text += f"• {material['name']}{availability_suffix}"
            if usage_count > 0:
                suffix = "раз"
                materials_text += f" (использован {usage_count} {suffix})"
            materials_text += "\n"
        materials_text += f"\nВсего материалов: {len(materials)}"
    else:
        materials_text = f"📋 {header}:\n\nМатериалы не добавлены."

    await callback.message.edit_text(
        f"{materials_text}\n\nВыберите действие:",
        reply_markup=keyboards.get_manage_materials_keyboard(material_type)
    )
    await callback.answer()

@router.callback_query(F.data == "admin_back_to_material_types")
async def back_to_material_types(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору типов материалов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    await state.update_data(material_management_type=None)

    print_materials = await database.db.get_materials_with_usage_count('3d_print')
    laser_materials = await database.db.get_materials_with_usage_count('laser_cut')

    summary = (
        "📋 Материалы по категориям:\n\n"
        f"• Для 3D печати: {len(print_materials)} шт\n"
        f"• Для лазерной резки: {len(laser_materials)} шт\n"
    )

    await callback.message.edit_text(
        f"🔧 Управление материалами\n\n{summary}\nВыберите категорию:",
        reply_markup=keyboards.get_admin_materials_type_keyboard({
            "3d_print": len(print_materials),
            "laser_cut": len(laser_materials)
        })
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_materials_type:"))
async def show_materials_for_type(callback: CallbackQuery, state: FSMContext):
    """Показать материалы выбранного типа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    material_type = callback.data.split(":")[1]
    await state.update_data(material_management_type=material_type)

    materials = await database.db.get_materials_with_usage_count(material_type)
    if material_type == "laser_cut":
        header = "Материалы для лазерной резки"
    else:
        header = "Материалы для 3D печати"

    if materials:
        materials_text = f"📋 {header}:\n\n"
        for material in materials:
            usage_count = material.get('usage_count', 0)
            availability_suffix = "" if material.get('is_available', 1) else " (недоступен)"
            materials_text += f"• {material['name']}{availability_suffix}"
            if usage_count > 0:
                suffix = "раз"
                if usage_count % 10 == 1 and usage_count % 100 != 11:
                    suffix = "раз"
                materials_text += f" (использован {usage_count} {suffix})"
            materials_text += "\n"
        materials_text += f"\nВсего материалов: {len(materials)}"
    else:
        materials_text = f"📋 {header}:\n\nМатериалы не добавлены."

    await callback.message.edit_text(
        f"{materials_text}\n\nВыберите действие:",
        reply_markup=keyboards.get_manage_materials_keyboard(material_type)
    )
    await callback.answer()

@router.callback_query(F.data == "admin_back_to_order_types")
async def back_to_order_types(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору типов заказов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    await state.update_data(admin_order_type=None, admin_order_status=None, admin_orders_page=0)

    order_stats: dict[str, dict] = {}
    archived_counts: dict[str, int] = {}
    summary_lines = []

    for order_type, title in config.ORDER_TYPES.items():
        stats = await database.db.get_orders_statistics(order_type)
        archived = await database.db.count_archived_orders(order_type)
        order_stats[order_type] = stats
        archived_counts[order_type] = archived

        total = stats.get("all", 0) + archived
        summary_lines.append(
            f"{title}: {total} шт (ожидание — {stats.get('pending', 0)}, "
            f"в работе — {stats.get('in_progress', 0)}, готов — {stats.get('ready', 0)}, "
            f"архив — {archived})"
        )

    stats_text = "\n".join(summary_lines) if summary_lines else "Нет заказов."

    await callback.message.edit_text(
        "📦 Заказы\n\n"
        f"{stats_text}\n\n"
        "Выберите тип заказов:",
        reply_markup=keyboards.get_admin_order_types_keyboard(order_stats, archived_counts)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_back_to_statuses:"))
async def back_to_statuses(callback: CallbackQuery, state: FSMContext):
    """Вернуться к списку статусов для выбранного типа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    order_type = callback.data.split(":")[1]
    await _render_orders_overview(callback.message, order_type, state)
    await callback.answer()

async def _render_orders_overview(message: Message, order_type: str, state: FSMContext):
    """Помощник для отображения статистики и разделов по типу заказов"""
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)
    stats = await database.db.get_orders_statistics(order_type)
    archived_count = await database.db.count_archived_orders(order_type)

    await state.update_data(admin_order_type=order_type, admin_order_status=None, admin_orders_page=0)

    stats_text = (
        f"• В ожидании: {stats.get('pending', 0)} шт\n"
        f"• В работе: {stats.get('in_progress', 0)} шт\n"
        f"• Готов: {stats.get('ready', 0)} шт\n"
        f"• Архив: {archived_count} шт\n"
        f"• Всего (без архива): {stats.get('all', 0)} шт"
    )

    text = (
        f"📦 Заказы — {order_type_name}\n\n"
        f"{stats_text}\n\n"
        "Выберите раздел:"
    )
    keyboard = keyboards.get_admin_orders_keyboard(stats, archived_count, order_type)

    try:
        await message.edit_text(
            text,
            reply_markup=keyboard
        )
    except TelegramBadRequest as exc:
        error_text = str(exc)
        if "no text in the message to edit" in error_text or "there is no text in the message to edit" in error_text:
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            await message.bot.send_message(
                message.chat.id,
                text,
                reply_markup=keyboard
            )
        else:
            raise


async def _render_orders_materials(message: Message, order_type: str, state: FSMContext):
    """Отобразить список материалов для фильтрации заказов"""
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)
    materials = await database.db.get_materials_with_orders(order_type, statuses=("pending", "in_progress"))

    await state.update_data(
        admin_order_type=order_type,
        admin_order_status="materials",
        admin_orders_page=0,
        admin_orders_material_id=None
    )

    if materials:
        body_text = (
            "Выберите материал.\n"
            "В списке только материалы, по которым есть активные заказы (\"В ожидании\" или \"В работе\")."
        )
    else:
        body_text = (
            "Нет материалов с активными заказами.\n"
            "Добавьте материал и оформите заказ, чтобы он появился в списке."
        )

    await message.edit_text(
        f"📦 Заказы — {order_type_name}\n\n{body_text}",
        reply_markup=keyboards.get_admin_orders_materials_keyboard(materials, order_type)
    )


@router.callback_query(F.data.startswith("admin_orders_type:"))
async def show_orders_type(callback: CallbackQuery, state: FSMContext):
    """Показать статистику и разделы для выбранного типа заказов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    order_type = callback.data.split(":")[1]
    await _render_orders_overview(callback.message, order_type, state)
    await callback.answer()


@router.message(Command("admin"))
@router.message(F.text == "Админ-панель")
async def cmd_admin(message: Message):
    """Обработчик команды админ-панели"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к админ-панели.")
        return
    
    orders_enabled = await database.db.is_orders_enabled()
    await message.answer(
        "🔧 Панель администратора\n\n"
        "Выберите раздел:",
        reply_markup=keyboards.get_admin_main_keyboard(orders_enabled)
    )


@router.callback_query(F.data == "admin_toggle_orders")
async def toggle_orders_acceptance(callback: CallbackQuery):
    """Переключение доступности приёма заказов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    current_state = await database.db.is_orders_enabled()
    new_state = not current_state
    await database.db.set_orders_enabled(new_state)

    status_text = "открыт" if new_state else "закрыт"
    orders_enabled = new_state

    await callback.message.edit_text(
        "🔧 Панель администратора\n\n"
        "Выберите раздел:",
        reply_markup=keyboards.get_admin_main_keyboard(orders_enabled)
    )
    await callback.answer(f"Приём заказов {status_text}.")


@router.callback_query(F.data == "admin_find_order")
async def admin_find_order_start(callback: CallbackQuery, state: FSMContext):
    """Начать поиск заказа по номеру"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    await state.set_state(states.OrderSearchStates.waiting_for_order_number)
    await state.update_data(order_search_origin="types_menu")

    await callback.message.edit_text(
        "🔍 Поиск заказа\n\n"
        "Введите номер заказа сообщением в чат.\n"
        "Чтобы отменить поиск, напишите «отмена».",
    )
    await callback.answer()


@router.message(F.text == "Рассылка")
async def start_broadcast_from_menu(message: Message, state: FSMContext):
    """Запуск режима рассылки из главного меню"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к режиму рассылки.")
        return

    prompt_message = await message.answer(
        "📢 Режим рассылки\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям.\n"
        "Можно отправить текст, фото, документ или другое сообщение — мы отправим точную копию.\n\n"
        "Чтобы отменить рассылку, используйте кнопки ниже.",
        reply_markup=keyboards.get_broadcast_cancel_keyboard()
    )

    await state.set_state(states.BroadcastStates.waiting_for_message)
    await state.update_data(
        broadcast_prompt_chat_id=prompt_message.chat.id,
        broadcast_prompt_message_id=prompt_message.message_id
    )


@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Запустить режим рассылки сообщений"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    await state.set_state(states.BroadcastStates.waiting_for_message)
    await state.update_data(
        broadcast_prompt_chat_id=callback.message.chat.id,
        broadcast_prompt_message_id=callback.message.message_id
    )

    await callback.message.edit_text(
        "📢 Режим рассылки\n\n"
        "Отправьте сообщение, которое нужно разослать всем пользователям.\n"
        "Можно отправить текст, фото, документ или другое сообщение — мы отправим точную копию.\n\n"
        "Чтобы отменить рассылку, используйте кнопки ниже.",
        reply_markup=keyboards.get_broadcast_cancel_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отменить режим рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    await state.set_state(None)
    await state.update_data(broadcast_prompt_chat_id=None, broadcast_prompt_message_id=None)

    orders_enabled = await database.db.is_orders_enabled()
    await callback.message.edit_text(
        "🔧 Панель администратора\n\n"
        "Выберите раздел:",
        reply_markup=keyboards.get_admin_main_keyboard(orders_enabled)
    )
    await callback.answer("Рассылка отменена.")


@router.message(states.BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    """Отправить сообщение рассылки всем пользователям"""
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к режиму рассылки.")
        await state.set_state(None)
        return

    user_ids = await database.db.get_all_user_ids()
    unique_user_ids = sorted({int(user_id) for user_id in user_ids if isinstance(user_id, int)})

    # Исключаем отправителя, он уже видит своё сообщение
    if message.from_user.id in unique_user_ids:
        unique_user_ids.remove(message.from_user.id)

    total_recipients = len(unique_user_ids)

    sent_count = 0
    failed_count = 0

    for user_id in unique_user_ids:
        try:
            await message.copy_to(user_id)
            sent_count += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await message.copy_to(user_id)
                sent_count += 1
            except TelegramForbiddenError:
                failed_count += 1
                logger.info(f"Пользователь {user_id} запретил сообщения от бота, пропускаем.")
            except TelegramBadRequest as inner_exc:
                failed_count += 1
                logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {inner_exc}")
            except Exception as inner_exc:
                failed_count += 1
                logger.error(f"Ошибка при повторной отправке пользователю {user_id}: {inner_exc}")
        except TelegramForbiddenError:
            failed_count += 1
            logger.info(f"Пользователь {user_id} запретил сообщения от бота, пропускаем.")
        except TelegramBadRequest as exc:
            failed_count += 1
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {exc}")
        except Exception as exc:
            failed_count += 1
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {exc}")

        # Небольшая пауза для снижения риска Flood control
        await asyncio.sleep(0.05)

    summary_text = (
        "📢 Рассылка завершена\n\n"
        f"Всего получателей: {total_recipients}\n"
        f"Успешно отправлено: {sent_count}\n"
        f"С ошибками: {failed_count}\n\n"
        "Выберите дальнейшее действие:"
    )

    orders_enabled = await database.db.is_orders_enabled()
    await message.answer(
        summary_text,
        reply_markup=keyboards.get_admin_main_keyboard(orders_enabled)
    )

    logger.info(
        f"Администратор {message.from_user.id} отправил рассылку. "
        f"Получателей: {total_recipients}, успешно: {sent_count}, ошибки: {failed_count}"
    )

    await state.update_data(broadcast_prompt_chat_id=None, broadcast_prompt_message_id=None)
    await state.set_state(None)


@router.callback_query(F.data.startswith("admin_orders_materials:"))
async def show_orders_materials(callback: CallbackQuery, state: FSMContext):
    """Показать материалы для фильтрации заказов по материалу"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    order_type = callback.data.split(":")[1]
    await _render_orders_materials(callback.message, order_type, state)
    await callback.answer()


@router.callback_query(F.data == "admin_orders_menu")
async def show_orders_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню фильтров заказов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.update_data(admin_order_type=None, admin_order_status=None)

    order_stats: dict[str, dict] = {}
    archived_counts: dict[str, int] = {}
    summary_lines = []

    for order_type, title in config.ORDER_TYPES.items():
        stats = await database.db.get_orders_statistics(order_type)
        archived = await database.db.count_archived_orders(order_type)
        order_stats[order_type] = stats
        archived_counts[order_type] = archived

        total = stats.get("all", 0) + archived
        summary_lines.append(
            f"{title}: {total} шт (ожидание — {stats.get('pending', 0)}, "
            f"в работе — {stats.get('in_progress', 0)}, готов — {stats.get('ready', 0)}, "
            f"архив — {archived})"
        )

    stats_text = "\n".join(summary_lines) if summary_lines else "Нет заказов."

    await callback.message.edit_text(
        "📦 Заказы\n\n"
        f"{stats_text}\n\n"
        "Выберите тип заказов:",
        reply_markup=keyboards.get_admin_order_types_keyboard(order_stats, archived_counts)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_orders:"))
async def show_orders_by_status(callback: CallbackQuery, state: FSMContext):
    """Показать заказы по статусу (первая страница)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    _, order_type, status_code = callback.data.split(":")
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)

    await state.update_data(admin_order_type=order_type, admin_order_status=status_code)
    
    # Проверяем, есть ли заказы в разделе
    if status_code == "all":
        total_count = await database.db.count_orders_by_status(None, order_type=order_type)
    elif status_code == "archived":
        total_count = await database.db.count_archived_orders(order_type)
    else:
        total_count = await database.db.count_orders_by_status(status_code, order_type=order_type)

    # Если раздел пуст, показываем предупреждение и не меняем сообщение
    if total_count == 0:
        if status_code == "all":
            status_text = f"Все заказы ({order_type_name})"
        elif status_code == "archived":
            status_text = f"Архив ({order_type_name})"
        else:
            status_text = f"{config.ORDER_STATUSES.get(status_code, status_code)} ({order_type_name})"
        await callback.answer(f"Раздел '{status_text}' пуст", show_alert=True)
        return
    
    await _show_orders_page(callback, state, order_type, status_code, page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_orders_material:"))
async def show_orders_by_material(callback: CallbackQuery, state: FSMContext):
    """Показать заказы для выбранного материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    try:
        _, order_type, material_id_str = callback.data.split(":")
        material_id = int(material_id_str)
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return

    material = await database.db.get_material(material_id)
    if not material:
        await callback.answer("Материал не найден", show_alert=True)
        await _render_orders_materials(callback.message, order_type, state)
        return

    active_statuses = ("pending", "in_progress")
    total_count = await database.db.count_orders_by_material(
        material_id,
        statuses=active_statuses,
        order_type=order_type
    )

    if total_count == 0:
        await callback.answer(
            "Заказы с выбранным материалом отсутствуют в статусах \"В ожидании\" и \"В работе\".",
            show_alert=True
        )
        await _render_orders_materials(callback.message, order_type, state)
        return

    await _show_orders_page(callback, state, order_type, f"material|{material_id}", page=0)
    await callback.answer()


async def _show_orders_page(callback: CallbackQuery, state: FSMContext, order_type: str, status_code: str, page: int = 0, orders_per_page: int = 6):
    """Показать страницу с заказами"""
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)

    is_material_filter = False
    material_id: int | None = None
    material_name: str | None = None
    active_material_statuses = ("pending", "in_progress")

    if status_code and status_code.startswith("material|"):
        is_material_filter = True
        try:
            material_id = int(status_code.split("|", 1)[1])
        except (ValueError, IndexError):
            await callback.answer("Некорректный материал", show_alert=True)
            await _render_orders_materials(callback.message, order_type, state)
            return

        material = await database.db.get_material(material_id)
        if not material:
            await callback.answer("Материал не найден", show_alert=True)
            await _render_orders_materials(callback.message, order_type, state)
            return

        material_name = material["name"]
        total_count = await database.db.count_orders_by_material(
            material_id,
            statuses=active_material_statuses,
            order_type=order_type
        )
        status_text = material_name
    elif status_code == "all":
        total_count = await database.db.count_orders_by_status(None, order_type=order_type)
        status_text = "Все заказы"
    elif status_code == "archived":
        total_count = await database.db.count_archived_orders(order_type)
        status_text = "Архив"
    else:
        total_count = await database.db.count_orders_by_status(status_code, order_type=order_type)
        status_text = config.ORDER_STATUSES.get(status_code, status_code)
    
    if total_count == 0:
        if is_material_filter:
            await _render_orders_materials(callback.message, order_type, state)
            await callback.answer(
                "Заказы с выбранным материалом отсутствуют в статусах \"В ожидании\" и \"В работе\".",
                show_alert=True
            )
        else:
            # Раздел пуст — возвращаемся к уровню выше (меню статусов)
            await _render_orders_overview(callback.message, order_type, state)
            await callback.answer("Раздел пуст. Возвращаемся к списку статусов.")
        return

    total_pages = (total_count + orders_per_page - 1) // orders_per_page if total_count > 0 else 1
    page = min(page, max(total_pages - 1, 0))
    offset = page * orders_per_page

    if is_material_filter and material_id is not None:
        orders = await database.db.get_orders_by_material(
            material_id,
            statuses=active_material_statuses,
            order_type=order_type,
            limit=orders_per_page,
            offset=offset
        )
    elif status_code == "all":
        orders = await database.db.get_orders_by_status(None, order_type=order_type, limit=orders_per_page, offset=offset)
    elif status_code == "archived":
        orders = await database.db.get_archived_orders(order_type=order_type, limit=orders_per_page, offset=offset)
    else:
        orders = await database.db.get_orders_by_status(status_code, order_type=order_type, limit=orders_per_page, offset=offset)
    
    if not orders and page > 0:
        # Если после удаления заказов текущая страница опустела, пробуем предыдущую
        await _show_orders_page(callback, state, order_type, status_code, page=page - 1, orders_per_page=orders_per_page)
        return

    await state.update_data(
        admin_order_type=order_type,
        admin_order_status=status_code,
        admin_orders_page=page,
        admin_orders_material_id=material_id if is_material_filter else None
    )
    
    start_num = page * orders_per_page + 1
    end_num = min((page + 1) * orders_per_page, total_count)

    if is_material_filter:
        back_callback = f"admin_orders_materials:{order_type}"
        back_text = "⬅️ Назад к материалам"
    else:
        back_callback = f"admin_back_to_statuses:{order_type}"
        back_text = "⬅️ Назад к разделу"
    
    orders_keyboard = keyboards.get_orders_list_keyboard(
        orders,
        prefix="admin_order",
        status_code=status_code,
        current_page=page,
        total_pages=total_pages,
        order_type=order_type,
        back_callback=back_callback,
        back_text=back_text
    )
    order_type_display = html.escape(order_type_name)
    if is_material_filter and material_name is not None:
        status_display = (
            "🎨 <b>Материал выбран:</b>\n"
            f"<b>{html.escape(material_name)}</b>"
        )
        header_line = f"📋 {order_type_display}"
    else:
        status_display = html.escape(status_text)
        header_line = f"📋 {status_display} — {order_type_display}"

    orders_text = f"{header_line}\n"
    if is_material_filter and material_name is not None:
        orders_text += f"{status_display}\n"

    orders_text += (
        f"Заказы {start_num}-{end_num} из {total_count}\n"
        f"Страница {page + 1} из {total_pages}\n\n"
    )
    if is_material_filter:
        orders_text += "<i>Показываются только заказы в статусах «В ожидании» и «В работе».</i>\n\n"
    orders_text += "Выберите заказ для просмотра:"

    try:
        await callback.message.edit_text(
            orders_text,
            reply_markup=orders_keyboard,
            parse_mode="HTML"
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
                reply_markup=orders_keyboard,
                parse_mode="HTML"
            )
            await callback.answer()
            return
        raise


@router.callback_query(F.data.startswith("admin_orders_page:"))
async def show_orders_page(callback: CallbackQuery, state: FSMContext):
    """Показать конкретную страницу с заказами"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    _, order_type, status_code, page = callback.data.split(":")
    page = int(page)
    
    await _show_orders_page(callback, state, order_type, status_code, page=page)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Обработчик для пустых кнопок (без действия)"""
    await callback.answer()


@router.callback_query(F.data.startswith("admin_back_to_orders"))
async def back_to_orders_list(callback: CallbackQuery, state: FSMContext):
    """Вернуться к списку заказов выбранного типа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    parts = callback.data.split(":")
    data = await state.get_data()

    if len(parts) >= 4:
        order_type = parts[1]
        status_code = parts[2]
        page = int(parts[3])
    else:
        order_type = parts[1] if len(parts) > 1 else data.get("admin_order_type") or "3d_print"
        status_code = parts[2] if len(parts) > 2 else data.get("admin_order_status")
        page = data.get("admin_orders_page", 0)

    if status_code and status_code not in (None, "None", ""):
        await _show_orders_page(callback, state, order_type, status_code, page=page)
    else:
        await _render_orders_overview(callback.message, order_type, state)
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_main")
async def back_to_admin_main(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню админ-панели"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(None)
    await state.update_data(broadcast_prompt_chat_id=None, broadcast_prompt_message_id=None)

    orders_enabled = await database.db.is_orders_enabled()
    text = (
        "🔧 Панель администратора\n\n"
        "Выберите раздел:"
    )
    keyboard = keyboards.get_admin_main_keyboard(orders_enabled)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard
        )
    except TelegramBadRequest as exc:
        error_text = str(exc)
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
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("admin_order:"))
async def show_order_detail(callback: CallbackQuery, state: FSMContext):
    """Показать детали заказа администратору"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    parts = callback.data.split(":")
    current_page = None

    if len(parts) >= 5:
        _, order_type, list_status, order_id_str, page_str = parts[:5]
        current_page = int(page_str)
    elif len(parts) == 4:
        _, order_type, list_status, order_id_str = parts
    else:
        order_id_str = parts[-1]
        order_type = None
        list_status = None

    data = await state.get_data()
    if order_type is None:
        order_type = data.get("admin_order_type") or "3d_print"
    if list_status is None:
        list_status = data.get("admin_order_status")
    if current_page is None:
        current_page = data.get("admin_orders_page", 0)
    await state.update_data(
        admin_order_type=order_type,
        admin_order_status=list_status,
        admin_orders_page=current_page
    )

    order_id = int(order_id_str)
    order = await database.db.get_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    detail_text, detail_keyboard, photo_path, _ = _build_admin_order_detail_payload(
        order,
        order_type=order_type,
        list_status=list_status,
        current_page=current_page,
        show_list_back=True
    )

    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            await callback.message.delete()
            await callback.bot.send_photo(
                callback.message.chat.id,
                photo_file,
                caption=detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            await callback.message.edit_text(
                detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
    else:
        await callback.message.edit_text(
            detail_text,
            reply_markup=detail_keyboard,
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_expand_order:"))
async def expand_order_from_notification(callback: CallbackQuery, state: FSMContext):
    """Развернуть уведомление о новом заказе"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    try:
        _, order_id_str = callback.data.split(":")
        order_id = int(order_id_str)
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return

    order = await database.db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    await state.update_data(
        admin_order_type=order.get('order_type', '3d_print'),
        admin_order_status=order.get('status_code'),
        admin_orders_page=0
    )

    collapse_button = [("⬅️ Скрыть уведомление", f"admin_collapse_order:{order_id}")]
    detail_text, detail_keyboard, photo_path, _ = _build_admin_order_detail_payload(
        order,
        order_type=order.get('order_type'),
        list_status=order.get('status_code'),
        current_page=0,
        show_list_back=False,
        extra_buttons=collapse_button
    )

    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            await callback.message.delete()
            await callback.bot.send_photo(
                callback.message.chat.id,
                photo_file,
                caption=detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото (разворот уведомления): {e}")
            await callback.message.edit_text(
                detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
    else:
        await callback.message.edit_text(
            detail_text,
            reply_markup=detail_keyboard,
            parse_mode="HTML"
        )

    await callback.answer()


@router.callback_query(F.data.startswith("admin_collapse_order:"))
async def collapse_order_notification(callback: CallbackQuery, state: FSMContext):
    """Свернуть уведомление с подробностями заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    try:
        _, order_id_str = callback.data.split(":")
        order_id = int(order_id_str)
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return

    order = await database.db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    summary_text = _build_admin_new_order_summary(order)

    try:
        await callback.message.delete()
    except TelegramBadRequest as exc:
        logger.warning(f"Не удалось удалить сообщение уведомления: {exc}")
    except Exception as exc:
        logger.error(f"Ошибка при удалении сообщения уведомления: {exc}")

    await callback.bot.send_message(
        callback.message.chat.id,
        summary_text,
        reply_markup=keyboards.get_admin_new_order_keyboard(order_id)
    )

    await state.update_data(
        admin_order_type=order.get('order_type', '3d_print'),
        admin_order_status=order.get('status_code'),
        admin_orders_page=0
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
    
    # Формируем новое имя файла по шаблону: {order_id}_{last_name}_{first_name}_{part_name}.<ext>
    file_extension = model_path.suffix.lower()
    original_filename = order.get('original_filename')
    if original_filename:
        part_name_source = Path(original_filename).stem
    else:
        part_name_source = model_path.stem
    part_name = order['part_name'] or part_name_source
    
    # Очищаем имена от недопустимых символов для файловых имен
    import re
    def clean_filename(name):
        # Заменяем пробелы и недопустимые символы на подчеркивания
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = name.replace(' ', '_')
        return name
    
    order_id = order['id']
    last_name = clean_filename(order['last_name'])
    first_name = clean_filename(order['first_name'])
    part_name_clean = clean_filename(part_name)
    
    new_filename = f"{order_id}_{last_name}_{first_name}_{part_name_clean}{file_extension}"
    
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
        logger.info(f"Администратор {callback.from_user.id} скачал модель для заказа №{order_id} с именем {new_filename}")
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании модели: {e}")
        await callback.answer("Ошибка при отправке файла", show_alert=True)


@router.callback_query(F.data.startswith("reject_order:"))
async def reject_order_start(callback: CallbackQuery, state: FSMContext):
    """Начать процесс отклонения заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    parts = callback.data.split(":")
    state_data = await state.get_data()
    order_id = int(parts[1])
    order_type = parts[2] if len(parts) > 2 else state_data.get("admin_order_type")
    list_status = parts[3] if len(parts) > 3 else state_data.get("admin_order_status")
    list_page = int(parts[4]) if len(parts) > 4 else state_data.get("admin_orders_page", 0)
    
    # Получаем заказ для определения типа
    order = await database.db.get_order(order_id)
    if order:
        order_type = order.get('order_type', order_type or '3d_print')
    else:
        order_type = order_type or '3d_print'
    
    # Сохраняем order_id в состоянии
    await state.update_data(
        order_id=order_id,
        reject_order_type=order_type,
        reject_list_status=list_status,
        reject_list_page=list_page
    )
    
    # Получаем шаблоны для данного типа заказа
    templates = await database.db.get_rejection_templates(order_type)
    
    if templates:
        # Показываем шаблоны
        reject_prompt = (
            f"❌ Отклонение заказа №{order_id}\n\n"
            "Выберите шаблонный комментарий или введите свой:"
        )
        keyboard = keyboards.get_rejection_templates_keyboard(templates, order_id, order_type, list_status, list_page)
    else:
        # Если шаблонов нет, сразу запрашиваем ввод
        reject_prompt = (
            f"❌ Отклонение заказа №{order_id}\n\n"
            "Пожалуйста, укажите причину отклонения заказа:"
        )
        keyboard = None
        await state.set_state(states.OrderRejectionStates.waiting_for_rejection_reason)

    try:
        if keyboard:
            await callback.message.edit_text(reject_prompt, reply_markup=keyboard)
        else:
            await callback.message.edit_text(reject_prompt)
    except TelegramBadRequest as exc:
        error_text = str(exc)
        if "no text in the message to edit" in error_text or "there is no text in the message to edit" in error_text:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            if keyboard:
                await callback.bot.send_message(
                    callback.message.chat.id,
                    reject_prompt,
                    reply_markup=keyboard
                )
            else:
                await callback.bot.send_message(
                    callback.message.chat.id,
                    reject_prompt
                )
        elif "message is not modified" in error_text:
            # Игнорируем попытку изменить на тот же текст
            pass
        else:
            raise

    await callback.answer()


@router.callback_query(F.data.startswith("use_rejection_template:"))
async def use_rejection_template(callback: CallbackQuery, state: FSMContext):
    """Использовать шаблонный комментарий для отклонения заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        _, order_id_str, template_id_str, order_type = parts[:4]
        order_id = int(order_id_str)
        template_id = int(template_id_str)
        list_status = parts[4] if len(parts) > 4 and parts[4] else None
        list_page = int(parts[5]) if len(parts) > 5 and parts[5] else 0
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    
    # Получаем шаблон
    template = await database.db.get_rejection_template(template_id)
    if not template:
        await callback.answer("Шаблон не найден", show_alert=True)
        return
    
    rejection_reason = template["text"]
    
    # Получаем заказ перед архивированием для отправки уведомления
    order = await database.db.get_order(order_id)
    
    # Перемещаем заказ в архив с причиной отклонения
    success = await database.db.archive_order(order_id, rejection_reason)
    
    if not success:
        await callback.answer("Ошибка при отклонении заказа", show_alert=True)
        return
    
    # Обновляем заказ для отправки уведомления
    order = await database.db.get_order(order_id)
    order['rejection_reason'] = rejection_reason
    
    # Отправляем уведомление пользователю с причиной отклонения
    await notify_user_order_status_changed(callback.bot, order, "Отклонен")
    
    stats = await database.db.get_orders_statistics(order_type)
    archived_count = await database.db.count_archived_orders(order_type)
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)

    await state.update_data(
        admin_order_type=order_type,
        admin_order_status='archived',
        admin_orders_page=list_page
    )

    stats_text = (
        f"• В ожидании: {stats.get('pending', 0)} шт\n"
        f"• В работе: {stats.get('in_progress', 0)} шт\n"
        f"• Готов: {stats.get('ready', 0)} шт\n"
        f"• Архив: {archived_count} шт\n"
        f"• Всего (без архива): {stats.get('all', 0)} шт"
    )

    await callback.message.edit_text(
        f"✅ Заказ №{order_id} отклонен и перемещен в архив.\n\n"
        f"Причина: {rejection_reason}\n\n"
        f"📦 Заказы — {order_type_name}\n\n"
        f"{stats_text}\n\nВыберите раздел:",
        reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count, order_type)
    )
    
    await callback.answer("Заказ отклонен")
    await state.clear()


@router.callback_query(F.data.startswith("reject_order_custom:"))
async def reject_order_custom_start(callback: CallbackQuery, state: FSMContext):
    """Начать процесс отклонения заказа с вводом своего комментария"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    try:
        parts = callback.data.split(":")
        _, order_id_str, order_type = parts[:3]
        order_id = int(order_id_str)
        list_status = parts[3] if len(parts) > 3 and parts[3] else None
        list_page = int(parts[4]) if len(parts) > 4 and parts[4] else 0
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    
    # Сохраняем order_id в состоянии
    await state.update_data(
        order_id=order_id,
        reject_order_type=order_type,
        reject_list_status=list_status,
        reject_list_page=list_page
    )
    
    reject_prompt = (
        f"❌ Отклонение заказа №{order_id}\n\n"
        "Пожалуйста, укажите причину отклонения заказа:"
    )

    try:
        await callback.message.edit_text(reject_prompt)
    except TelegramBadRequest as exc:
        error_text = str(exc)
        if "no text in the message to edit" in error_text or "there is no text in the message to edit" in error_text:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.bot.send_message(
                callback.message.chat.id,
                reject_prompt
            )
        elif "message is not modified" in error_text:
            pass
        else:
            raise

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
    
    order_type = data.get('reject_order_type') or data.get('admin_order_type') or '3d_print'
    list_status = data.get('reject_list_status') or 'archived'
    list_page = data.get('reject_list_page', data.get('admin_orders_page', 0))

    stats = await database.db.get_orders_statistics(order_type)
    archived_count = await database.db.count_archived_orders(order_type)
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)

    await state.update_data(
        admin_order_type=order_type,
        admin_order_status=list_status,
        admin_orders_page=list_page
    )

    stats_text = (
        f"• В ожидании: {stats.get('pending', 0)} шт\n"
        f"• В работе: {stats.get('in_progress', 0)} шт\n"
        f"• Готов: {stats.get('ready', 0)} шт\n"
        f"• Архив: {archived_count} шт\n"
        f"• Всего (без архива): {stats.get('all', 0)} шт"
    )

    await message.answer(
        f"✅ Заказ №{order_id} отклонен и перемещен в архив.\n\n"
        f"Причина: {rejection_reason}\n\n"
        f"📦 Заказы — {order_type_name}\n\n"
        f"{stats_text}\n\nВыберите раздел:",
        reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count, order_type)
    )
    
    await state.clear()


@router.callback_query(F.data.startswith("set_status:"))
async def set_order_status(callback: CallbackQuery, state: FSMContext):
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
    
    data = await state.get_data()
    order_type = data.get('admin_order_type') or order.get('order_type') or '3d_print'
    current_list_status = data.get('admin_order_status')
    if current_list_status in ("all", "archived", None, "", "None"):
        list_status = current_list_status or status_code
    else:
        list_status = current_list_status
    current_page = data.get('admin_orders_page', 0)

    await state.update_data(
        admin_order_type=order_type,
        admin_order_status=list_status,
        admin_orders_page=current_page
    )

    # Показываем обновленную информацию о заказе
    await show_order_detail_after_update(
        callback.bot,
        callback.message.chat.id,
        order_id,
        order_type=order_type,
        list_status=list_status,
        current_page=current_page
    )
    
    await callback.answer(f"Статус изменен на '{status_name}'")


@router.callback_query(F.data.startswith("admin_picked_up:"))
async def admin_picked_up_order(callback: CallbackQuery, state: FSMContext):
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
        order_type = order.get('order_type', '3d_print')
        stats = await database.db.get_orders_statistics(order_type)
        archived_count = await database.db.count_archived_orders(order_type)
        order_type_name = config.ORDER_TYPES.get(order_type, order_type)

        await state.update_data(admin_order_type=order_type, admin_order_status='archived', admin_orders_page=0)

        stats_text = (
            f"• В ожидании: {stats.get('pending', 0)} шт\n"
            f"• В работе: {stats.get('in_progress', 0)} шт\n"
            f"• Готов: {stats.get('ready', 0)} шт\n"
            f"• Архив: {archived_count} шт\n"
            f"• Всего (без архива): {stats.get('all', 0)} шт"
        )

        await callback.message.edit_text(
            f"✅ Заказ №{order_id} перемещен в архив.\n\n"
            f"📦 Заказы — {order_type_name}\n\n"
            f"{stats_text}\n\nВыберите раздел:",
            reply_markup=keyboards.get_admin_orders_keyboard(stats, archived_count, order_type)
        )
        logger.info(f"Администратор {callback.from_user.id} пометил заказ №{order_id} как полученный (перемещен в архив)")
    else:
        await callback.answer("Ошибка при архивировании заказа", show_alert=True)
    
    await callback.answer()


async def show_order_detail_after_update(
    bot: Bot,
    chat_id: int,
    order_id: int,
    order_type: str | None = None,
    list_status: str | None = None,
    current_page: int | None = None
):
    """Показать обновленную информацию о заказе после изменения статуса"""
    order = await database.db.get_order(order_id)
    
    if not order:
        return
    
    detail_text, detail_keyboard, photo_path, status_name = _build_admin_order_detail_payload(
        order,
        order_type=order_type,
        list_status=list_status,
        current_page=current_page,
        show_list_back=True
    )

    status_message = (
        f"✅ Статус изменен на '{html.escape(status_name)}'\n\n"
        f"{detail_text}"
    )

    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            await bot.send_photo(
                chat_id,
                photo_file,
                caption=status_message,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото (обновление заказа): {e}")
            await bot.send_message(
                chat_id,
                status_message,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
    else:
        await bot.send_message(
            chat_id,
            status_message,
            reply_markup=detail_keyboard,
            parse_mode="HTML"
        )


@router.callback_query(F.data == "admin_manage_materials")
async def manage_materials(callback: CallbackQuery, state: FSMContext):
    """Управление материалами"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.update_data(material_management_type=None)

    print_materials = await database.db.get_materials_with_usage_count('3d_print')
    laser_materials = await database.db.get_materials_with_usage_count('laser_cut')

    summary = (
        "📋 Материалы по категориям:\n\n"
        f"• Для 3D печати: {len(print_materials)} шт\n"
        f"• Для лазерной резки: {len(laser_materials)} шт\n"
    )

    await callback.message.edit_text(
        f"🔧 Управление материалами\n\n{summary}\nВыберите категорию:",
        reply_markup=keyboards.get_admin_materials_type_keyboard({
            "3d_print": len(print_materials),
            "laser_cut": len(laser_materials)
        })
    )
    await callback.answer()




@router.callback_query(F.data.startswith("admin_add_material:"))
async def add_material_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    material_type = callback.data.split(":")[1]
    await state.update_data(material_management_type=material_type)

    if material_type == "laser_cut":
        prompt = (
            "Введите название материала для лазерной резки.\n\n"
            "Пример: фанера 3 мм\n"
            "Можно указывать толщину, тип древесины и т.д."
        )
    else:
        prompt = (
            "Введите название материала в формате \"цвет тип пластика\".\n\n"
            "Примеры:\n"
            "• зеленый PETG\n"
            "• синий PLA\n"
            "• красный ABS"
        )

    await callback.message.edit_text(
        prompt
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
    
    data = await state.get_data()
    material_type = data.get('material_management_type') or '3d_print'
    
    success = await database.db.add_material(material_name, material_type)
    
    if success:
        # Получаем обновленный список материалов со статистикой
        materials = await database.db.get_materials_with_usage_count(material_type)
        header = "для лазерной резки" if material_type == "laser_cut" else "для 3D печати"
        
        # Формируем текст со списком материалов
        if materials:
            materials_text = f"📋 Доступные материалы {header}:\n\n"
            for material in materials:
                usage_count = material.get('usage_count', 0)
                availability_suffix = "" if material.get('is_available', 1) else " (недоступен)"
                materials_text += f"• {material['name']}{availability_suffix}"
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
            materials_text = f"📋 Доступные материалы {header}:\n\nМатериалы не добавлены."
        
        await message.answer(
            f"✅ Материал '{material_name}' добавлен!\n\n"
            f"{materials_text}\n\n"
            "Выберите действие:",
            reply_markup=keyboards.get_manage_materials_keyboard(material_type)
        )
    else:
        await message.answer(f"❌ Материал '{material_name}' уже существует!")
    
    await state.clear()


@router.callback_query(F.data.startswith("admin_delete_material:"))
async def delete_material_start(callback: CallbackQuery, state: FSMContext):
    """Начать удаление материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    material_type = callback.data.split(":")[1]
    await state.update_data(material_management_type=material_type)

    materials = await database.db.get_all_materials(material_type, only_available=True)
    
    if not materials:
        await callback.message.edit_text("Нет материалов для удаления.")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "Выберите материал для удаления:",
        reply_markup=keyboards.get_delete_materials_keyboard(materials, material_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_restore_material:"))
async def restore_material_start(callback: CallbackQuery, state: FSMContext):
    """Начать восстановление доступа к материалу"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    material_type = callback.data.split(":")[1]
    await state.update_data(material_management_type=material_type)

    all_materials = await database.db.get_all_materials(material_type, only_available=False)
    disabled_materials = [material for material in all_materials if not material.get("is_available", 1)]

    if not disabled_materials:
        await callback.answer("Нет недоступных материалов.", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите материал для возобновления доступа:",
        reply_markup=keyboards.get_restore_materials_keyboard(disabled_materials, material_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_material:"))
async def delete_material_process(callback: CallbackQuery, state: FSMContext):
    """Обработка удаления материала"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    _, material_type, material_id_str = callback.data.split(":")
    material_id = int(material_id_str)
    success = await database.db.delete_material(material_id)
    
    if success:
        # Получаем обновленный список материалов со статистикой
        materials = await database.db.get_materials_with_usage_count(material_type)
        header = "для лазерной резки" if material_type == "laser_cut" else "для 3D печати"
        
        # Формируем текст со списком материалов
        if materials:
            materials_text = f"📋 Доступные материалы {header}:\n\n"
            for material in materials:
                usage_count = material.get('usage_count', 0)
                availability_suffix = "" if material.get('is_available', 1) else " (недоступен)"
                materials_text += f"• {material['name']}{availability_suffix}"
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
            materials_text = f"📋 Доступные материалы {header}:\n\nМатериалы не добавлены."
        
        await callback.message.edit_text(
            f"✅ Материал помечен как недоступный.\n\n{materials_text}\n\nВыберите действие:",
            reply_markup=keyboards.get_manage_materials_keyboard(material_type)
        )
    else:
        await callback.message.edit_text("❌ Ошибка при удалении!")
    
    await callback.answer()


@router.callback_query(F.data.startswith("restore_material:"))
async def restore_material_process(callback: CallbackQuery, state: FSMContext):
    """Обработка восстановления доступа к материалу"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    _, material_type, material_id_str = callback.data.split(":")
    material_id = int(material_id_str)
    success = await database.db.restore_material(material_id)

    if success:
        materials = await database.db.get_materials_with_usage_count(material_type)
        header = "для лазерной резки" if material_type == "laser_cut" else "для 3D печати"

        if materials:
            materials_text = f"📋 Доступные материалы {header}:\n\n"
            for material in materials:
                usage_count = material.get('usage_count', 0)
                availability_suffix = "" if material.get('is_available', 1) else " (недоступен)"
                materials_text += f"• {material['name']}{availability_suffix}"
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
            materials_text = f"📋 Доступные материалы {header}:\n\nМатериалы не добавлены."

        await callback.message.edit_text(
            f"✅ Материал снова доступен.\n\n{materials_text}\n\nВыберите действие:",
            reply_markup=keyboards.get_manage_materials_keyboard(material_type)
        )
    else:
        await callback.message.edit_text("❌ Ошибка при восстановлении доступа!")

    await callback.answer()


@router.callback_query(F.data == "admin_manage_rejection_templates_menu")
async def manage_rejection_templates_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню управления шаблонами отклонения"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 Управление шаблонами отклонения заказов\n\n"
        "Выберите тип заказов для управления шаблонами:",
        reply_markup=keyboards.get_rejection_template_type_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_manage_rejection_templates:"))
async def manage_rejection_templates(callback: CallbackQuery, state: FSMContext):
    """Показать управление шаблонами для выбранного типа заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_type = callback.data.split(":")[1]
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)
    
    templates = await database.db.get_rejection_templates(order_type)
    
    if templates:
        templates_text = f"📋 Шаблоны для {order_type_name}:\n\n"
        for i, template in enumerate(templates, 1):
            templates_text += f"{i}. {template['text']}\n"
        templates_text += f"\nВсего шаблонов: {len(templates)}"
    else:
        templates_text = f"📋 Шаблоны для {order_type_name}:\n\nШаблоны не добавлены."
    
    await callback.message.edit_text(
        f"{templates_text}\n\nВыберите действие:",
        reply_markup=keyboards.get_rejection_template_management_keyboard(order_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_add_rejection_template:"))
async def add_rejection_template_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление шаблона отклонения"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_type = callback.data.split(":")[1]
    order_type_name = config.ORDER_TYPES.get(order_type, order_type)
    
    await state.update_data(rejection_template_order_type=order_type)
    
    await callback.message.edit_text(
        f"➕ Добавление шаблона отклонения для {order_type_name}\n\n"
        "Введите текст шаблона:"
    )
    await state.set_state(states.RejectionTemplateManagementStates.waiting_for_template_text)
    await callback.answer()


@router.message(states.RejectionTemplateManagementStates.waiting_for_template_text)
async def add_rejection_template_process(message: Message, state: FSMContext):
    """Обработка добавления шаблона отклонения"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    template_text = message.text.strip()
    if not template_text:
        await message.answer("Пожалуйста, введите текст шаблона:")
        return
    
    data = await state.get_data()
    order_type = data.get('rejection_template_order_type')
    
    if not order_type:
        await message.answer("Ошибка: не найден тип заказа")
        await state.clear()
        return
    
    success = await database.db.add_rejection_template(order_type, template_text)
    
    if success:
        order_type_name = config.ORDER_TYPES.get(order_type, order_type)
        templates = await database.db.get_rejection_templates(order_type)
        
        if templates:
            templates_text = f"📋 Шаблоны для {order_type_name}:\n\n"
            for i, template in enumerate(templates, 1):
                templates_text += f"{i}. {template['text']}\n"
            templates_text += f"\nВсего шаблонов: {len(templates)}"
        else:
            templates_text = f"📋 Шаблоны для {order_type_name}:\n\nШаблоны не добавлены."
        
        await message.answer(
            f"✅ Шаблон добавлен!\n\n{templates_text}\n\nВыберите действие:",
            reply_markup=keyboards.get_rejection_template_management_keyboard(order_type)
        )
    else:
        await message.answer("❌ Ошибка при добавлении шаблона")
    
    await state.clear()


@router.callback_query(F.data.startswith("admin_delete_rejection_template:"))
async def delete_rejection_template_start(callback: CallbackQuery, state: FSMContext):
    """Начать удаление шаблона отклонения"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    order_type = callback.data.split(":")[1]
    
    templates = await database.db.get_rejection_templates(order_type)
    
    if not templates:
        await callback.answer("Нет шаблонов для удаления", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🗑️ Выберите шаблон для удаления:",
        reply_markup=keyboards.get_delete_rejection_templates_keyboard(templates, order_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_rejection_template:"))
async def delete_rejection_template_process(callback: CallbackQuery, state: FSMContext):
    """Обработка удаления шаблона отклонения"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    try:
        _, order_type, template_id_str = callback.data.split(":")
        template_id = int(template_id_str)
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    
    success = await database.db.delete_rejection_template(template_id)
    
    if success:
        order_type_name = config.ORDER_TYPES.get(order_type, order_type)
        templates = await database.db.get_rejection_templates(order_type)
        
        if templates:
            templates_text = f"📋 Шаблоны для {order_type_name}:\n\n"
            for i, template in enumerate(templates, 1):
                templates_text += f"{i}. {template['text']}\n"
            templates_text += f"\nВсего шаблонов: {len(templates)}"
        else:
            templates_text = f"📋 Шаблоны для {order_type_name}:\n\nШаблоны не добавлены."
        
        await callback.message.edit_text(
            f"✅ Шаблон удален!\n\n{templates_text}\n\nВыберите действие:",
            reply_markup=keyboards.get_rejection_template_management_keyboard(order_type)
        )
    else:
        await callback.answer("Ошибка при удалении шаблона", show_alert=True)
    
    await callback.answer()


@router.message(states.OrderSearchStates.waiting_for_order_number)
async def admin_process_order_search(message: Message, state: FSMContext):
    """Обработка ввода номера заказа для поиска"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    text = message.text.strip()
    if text.lower() in {"отмена", "cancel"}:
        await state.clear()
        orders_enabled = await database.db.is_orders_enabled()
        await message.answer(
            "Поиск заказов отменён.",
            reply_markup=keyboards.get_admin_main_keyboard(orders_enabled)
        )
        return

    if not text.isdigit():
        await message.answer("Введите числовой номер заказа или напишите «отмена».")
        return

    order_id = int(text)
    order = await database.db.get_order(order_id)

    if not order:
        await message.answer(
            f"Заказ №{order_id} не найден. Проверьте номер и попробуйте снова, или напишите «отмена».",
        )
        return

    await state.clear()

    order_type = order.get('order_type', '3d_print')
    list_status = order.get('status_code')

    extra_buttons = [
        ("➡️ Открыть раздел", f"admin_orders_type:{order_type}"),
        ("⬅️ В меню", "admin_back_to_main")
    ]

    detail_text, detail_keyboard, photo_path, _ = _build_admin_order_detail_payload(
        order,
        order_type=order_type,
        list_status=list_status,
        current_page=0,
        show_list_back=False,
        extra_buttons=extra_buttons
    )

    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            await message.answer_photo(
                photo_file,
                caption=detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
        except Exception as exc:
            logger.error(f"Ошибка при отправке фото (поиск заказа): {exc}")
            await message.answer(
                detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
    else:
        await message.answer(
            detail_text,
            reply_markup=detail_keyboard,
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("admin_view_from_user:"))
async def admin_view_order_from_user(callback: CallbackQuery, state: FSMContext):
    """Показать админское описание заказа из пользовательского списка"""
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет доступа", show_alert=True)
        return

    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный идентификатор заказа", show_alert=True)
        return

    order = await database.db.get_order(order_id)
    if not order or order.get('user_id') != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    order_type = order.get('order_type', '3d_print')
    status_code = order.get('status_code')

    await state.update_data(
        admin_order_type=order_type,
        admin_order_status=status_code,
        admin_orders_page=0
    )

    extra_buttons = [("⬅️ К моим заказам", "user_back_to_orders")]
    detail_text, detail_keyboard, photo_path, _ = _build_admin_order_detail_payload(
        order,
        order_type=order_type,
        list_status=status_code,
        current_page=0,
        show_list_back=False,
        extra_buttons=extra_buttons
    )

    if photo_path and Path(photo_path).exists():
        try:
            photo_file = FSInputFile(photo_path)
            await callback.message.delete()
            await callback.bot.send_photo(
                callback.message.chat.id,
                photo_file,
                caption=detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
        except Exception as exc:
            logger.error(f"Ошибка при отправке фото (админ просмотр из пользовательского списка): {exc}")
            await callback.message.edit_text(
                detail_text,
                reply_markup=detail_keyboard,
                parse_mode="HTML"
            )
    else:
        await callback.message.edit_text(
            detail_text,
            reply_markup=detail_keyboard,
            parse_mode="HTML"
        )

    await callback.answer()


