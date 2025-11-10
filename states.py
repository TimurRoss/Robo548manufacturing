"""
Модуль для состояний FSM (Finite State Machine) бота
"""
from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния для регистрации пользователя"""
    waiting_for_first_name = State()
    waiting_for_last_name = State()


class OrderCreationStates(StatesGroup):
    """Состояния для создания заказа"""
    waiting_for_order_type = State()
    waiting_for_photo = State()
    waiting_for_model = State()
    waiting_for_part_name = State()
    waiting_for_material = State()
    waiting_for_comment = State()
    waiting_for_confirm = State()


class MaterialManagementStates(StatesGroup):
    """Состояния для управления материалами (админ)"""
    waiting_for_material_name = State()


class OrderRejectionStates(StatesGroup):
    """Состояния для отклонения заказа"""
    waiting_for_rejection_reason = State()


class BroadcastStates(StatesGroup):
    """Состояния для рассылки сообщений администраторами"""
    waiting_for_message = State()

