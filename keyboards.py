from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from alert_types import KIND_PCT, WINDOWS
from config import PREMIUM_PRICE_STARS

# ---------- постоянная клавиатура внизу ----------

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Создать алерт")],
        [KeyboardButton(text="📋 Мои алерты"), KeyboardButton(text="🗑 Удалить все")],
        [KeyboardButton(text="⭐ Премиум"), KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие…",
)

# ---------- inline-кнопки ----------

_CANCEL_ROW = [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]


def kind_kb(premium: bool) -> InlineKeyboardMarkup:
    lock = "" if premium else "🔒 "
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Цена достигла уровня", callback_data="kind:price")],
            [InlineKeyboardButton(text=f"{lock}📈 Рост/падение на %", callback_data="kind:pct")],
            [InlineKeyboardButton(text=f"{lock}📊 Объём за 24ч", callback_data="kind:volume")],
            [InlineKeyboardButton(text=f"{lock}💸 Фандинг", callback_data="kind:funding")],
            _CANCEL_ROW,
        ]
    )


def direction_kb(kind: str) -> InlineKeyboardMarkup:
    if kind == KIND_PCT:
        first = InlineKeyboardButton(text="📈 Рост", callback_data="dir:up")
        second = InlineKeyboardButton(text="📉 Падение", callback_data="dir:down")
    else:
        first = InlineKeyboardButton(text="⬇️ Ниже", callback_data="dir:below")
        second = InlineKeyboardButton(text="⬆️ Выше", callback_data="dir:above")
    return InlineKeyboardMarkup(inline_keyboard=[[first, second], _CANCEL_ROW])


def window_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"win:{sec}")
        for sec, label in WINDOWS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:], _CANCEL_ROW])


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать", callback_data="confirm")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_CANCEL_ROW])


def pay_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"⭐ Подписаться — {PREMIUM_PRICE_STARS} Stars/мес",
                callback_data="pay_premium",
            )],
        ]
    )


def pay_link_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить {PREMIUM_PRICE_STARS} Stars", url=url)],
        ]
    )


def alert_item_kb(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{alert_id}")]
        ]
    )