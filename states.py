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
    waiting_for_photo = State()
    waiting_for_model = State()
    waiting_for_part_name = State()
    waiting_for_material = State()
    waiting_for_confirm = State()


class MaterialManagementStates(StatesGroup):
    """Состояния для управления материалами (админ)"""
    waiting_for_material_name = State()

