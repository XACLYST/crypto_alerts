from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

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

direction_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="⬇️ Ниже", callback_data="dir:below"),
            InlineKeyboardButton(text="⬆️ Выше", callback_data="dir:above"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ]
)


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать", callback_data="confirm")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ]
    )


def pay_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оплатить 50 Stars", callback_data="pay_premium")],
        ]
    )


def alert_item_kb(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{alert_id}")]
        ]
    )