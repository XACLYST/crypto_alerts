from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from config import FREE_ALERT_LIMIT, PREMIUM_PRICE_STARS
from keyboards import (
    alert_item_kb,
    cancel_kb,
    confirm_kb,
    direction_kb,
    main_kb,
    pay_kb,
)
from price_service import validate_symbol
from states import AlertForm
from storage import (
    Alert,
    add_alert,
    count_user_alerts,
    delete_alert,
    delete_all_user_alerts,
    get_user_alerts,
    is_user_premium,
    set_user_premium,
)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я присылаю алерты по ценам крипты (данные с Binance).\n"
        "Выбери действие на клавиатуре ниже 👇",
        reply_markup=main_kb,
    )


@router.message(F.text == "ℹ️ Помощь")
async def help_handler(message: Message) -> None:
    await message.answer(
        "Как пользоваться:\n"
        "1. Нажми «➕ Создать алерт»\n"
        "2. Введи тикер пары (например, <code>BTCUSDT</code>, "
        "<code>ETHUSDT</code>, <code>GRAMUSDT</code>)\n"
        "3. Выбери «Ниже» или «Выше»\n"
        "4. Введи цену в той валюте, котировка которой указана второй в паре (например для пары BTCUSDT укажи цену в USDT)\n\n"
        "Тикер — это пара, как на Bybit или Binance. "
        "Например, для Bitcoin это <code>BTCUSDT</code>.\n\n"
        f"Бесплатный лимит: {FREE_ALERT_LIMIT} алерта.\n"
        f"Премиум: {PREMIUM_PRICE_STARS} ⭐ — без лимита.",
        reply_markup=main_kb,
    )


@router.message(F.text == "➕ Создать алерт")
async def start_create(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    premium = await is_user_premium(user_id)
    count = await count_user_alerts(user_id)

    if not premium and count >= FREE_ALERT_LIMIT:
        await message.answer(
            f"Ты использовал все {FREE_ALERT_LIMIT} бесплатных алерта.\n"
            f"Оплати {PREMIUM_PRICE_STARS} ⭐, чтобы снять лимит навсегда.",
            reply_markup=pay_kb(),
        )
        return

    await state.set_state(AlertForm.waiting_symbol)
    await message.answer(
        "Введи тикер пары (например, <code>BTCUSDT</code>, "
        "<code>GRAMUSDT</code>):",
        reply_markup=cancel_kb(),
    )


@router.message(AlertForm.waiting_symbol)
async def got_symbol(message: Message, state: FSMContext) -> None:
    symbol = message.text.strip().upper()

    if not symbol.isascii() or " " in symbol:
        await message.answer(
            "Похоже на опечатку. Введи тикер латиницей, без пробелов "
            "(например, <code>BTCUSDT</code>)."
        )
        return

    # проверяем, что пара существует на Binance
    if not await validate_symbol(symbol):
        await message.answer(
            f"Пара <code>{symbol}</code> не найдена на Binance.\n"
            "Проверь тикер — это должно быть что-то вроде "
            "<code>BTCUSDT</code> или <code>GRAMUSDT</code>."
        )
        return

    await state.update_data(symbol=symbol)
    await state.set_state(AlertForm.waiting_direction)
    await message.answer(
        f"Пара: <b>{symbol}</b>\nКогда присылать алерт?",
        reply_markup=direction_kb,
    )


@router.callback_query(AlertForm.waiting_direction, F.data.startswith("dir:"))
async def got_direction(callback: CallbackQuery, state: FSMContext) -> None:
    direction = callback.data.split(":")[1]
    await state.update_data(direction=direction)
    await state.set_state(AlertForm.waiting_price)
    label = "ниже" if direction == "below" else "выше"
    await callback.message.edit_text(
        f"Пришли, когда цена будет <b>{label}</b> какой суммы (в USDT)?",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(AlertForm.waiting_price)
async def got_price(message: Message, state: FSMContext) -> None:
    try:
        price = float(message.text.replace(",", ".").replace("$", "").strip())
    except ValueError:
        await message.answer(
            "Нужно число, например <code>60000</code> или <code>0.5</code>"
        )
        return
    await state.update_data(price=price)
    await state.set_state(AlertForm.waiting_confirm)

    data = await state.get_data()
    label = "ниже" if data["direction"] == "below" else "выше"
    await message.answer(
        f"Проверь алерт:\n"
        f"• Пара: <b>{data['symbol']}</b>\n"
        f"• Условие: цена <b>{label}</b> <b>{price} USDT</b>\n\n"
        f"Создаём?",
        reply_markup=confirm_kb(),
    )


@router.callback_query(AlertForm.waiting_confirm, F.data == "confirm")
async def confirm_alert(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    alert = Alert(
        id=None,
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        symbol=data["symbol"],
        threshold=data["price"],
        direction=data["direction"],
    )
    await add_alert(alert)
    await callback.message.edit_text(
        f"✅ Алерт создан: {alert.symbol} "
        f"{'ниже' if alert.direction == 'below' else 'выше'} {alert.threshold} USDT"
    )
    await callback.answer("Готово!")


@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()


@router.message(F.text == "📋 Мои алерты")
async def list_alerts(message: Message) -> None:
    user_alerts = await get_user_alerts(message.from_user.id)
    if not user_alerts:
        await message.answer("У тебя нет активных алертов.")
        return

    for a in user_alerts:
        status = "🔔 сработал" if a.triggered else "⏳ ждёт"
        label = "ниже" if a.direction == "below" else "выше"
        await message.answer(
            f"• {a.symbol} {label} {a.threshold} USDT — {status}",
            reply_markup=alert_item_kb(a.id),
        )


@router.callback_query(F.data.startswith("del:"))
async def delete_one(callback: CallbackQuery) -> None:
    alert_id = int(callback.data.split(":")[1])
    ok = await delete_alert(alert_id, callback.from_user.id)
    if ok:
        await callback.message.edit_text("🗑 Алерт удалён.")
    else:
        await callback.message.edit_text("Алерт уже не найден.")
    await callback.answer()


@router.message(F.text == "🗑 Удалить все")
async def delete_all(message: Message) -> None:
    deleted = await delete_all_user_alerts(message.from_user.id)
    await message.answer(f"Удалено алертов: {deleted}")


@router.message(F.text == "⭐ Премиум")
async def premium_info(message: Message) -> None:
    premium = await is_user_premium(message.from_user.id)
    if premium:
        await message.answer("У тебя уже есть премиум — лимита нет 🎉")
        return

    count = await count_user_alerts(message.from_user.id)
    await message.answer(
        f"Бесплатный лимит: {FREE_ALERT_LIMIT} алерта.\n"
        f"Сейчас у тебя: {count}.\n\n"
        f"Премиум снимает лимит навсегда за {PREMIUM_PRICE_STARS} ⭐.",
        reply_markup=pay_kb(),
    )


@router.callback_query(F.data == "pay_premium")
async def send_stars_invoice(callback: CallbackQuery) -> None:
    if await is_user_premium(callback.from_user.id):
        await callback.answer("У тебя уже есть премиум.", show_alert=True)
        return

    await callback.message.answer_invoice(
        title="Премиум: безлимитные алерты",
        description="Снимает лимит в 2 алерта навсегда",
        payload="premium_unlock",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Премиум", amount=PREMIUM_PRICE_STARS)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    payload = message.successful_payment.invoice_payload
    if payload == "premium_unlock":
        await set_user_premium(message.from_user.id, True)
        await message.answer(
            "✅ Оплата получена! Лимит снят — создавай сколько хочешь.",
            reply_markup=main_kb,
        )