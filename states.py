from aiogram.fsm.state import State, StatesGroup


class AlertForm(StatesGroup):
    waiting_kind = State()
    waiting_symbol = State()
    waiting_direction = State()
    waiting_window = State()
    waiting_value = State()
    waiting_confirm = State()