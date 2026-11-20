from aiogram.fsm.state import State, StatesGroup


class AlertForm(StatesGroup):
    waiting_symbol = State()
    waiting_direction = State()
    waiting_price = State()
    waiting_confirm = State()