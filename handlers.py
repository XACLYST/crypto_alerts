import time
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from alert_types import (
    KIND_FUNDING,
    KIND_PCT,
    KIND_PRICE,
    KIND_VOLUME,
    PREMIUM_KINDS,
    allowed_alert_ids,
    describe_alert,
    parse_number,
)
from config import (
    FREE_ALERT_LIMIT,
    PREMIUM_ALERT_LIMIT,
    PREMIUM_PRICE_STARS,
    SUBSCRIPTION_PERIOD,
)
from keyboards import (
    alert_item_kb,
    cancel_kb,
    confirm_kb,
    direction_kb,
    kind_kb,
    main_kb,
    pay_kb,
    pay_link_kb,
    window_kb,
)
from price_service import validate_symbol
from states import AlertForm
from storage import (
    Alert,
    add_alert,
    count_user_alerts,
    delete_alert,
    delete_all_user_alerts,
    get_premium_status,
    get_user_alerts,
    is_user_premium,
    record_subscription_payment,
)

router = Router()

PREMIUM_PAYLOAD = "premium_sub_30d"

FEATURES_TEXT = (
    f"• до {PREMIUM_ALERT_LIMIT} алертов вместо {FREE_ALERT_LIMIT}\n"
    "• 📈 рост/падение цены на % за 5 мин, 15 мин, 1 час или 24 часа\n"
    "• 📊 алерты по объёму торгов за 24 часа\n"
    "• 💸 алерты по ставке фандинга (бессрочные контракты)"
)


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")


async def _paywall(message: Message, text: str) -> None:
    await message.answer(
        f"{text}\n\n<b>Премиум</b> — {PREMIUM_PRICE_STARS} ⭐ в месяц:\n{FEATURES_TEXT}",
        reply_markup=pay_kb(),
    )


# ВАЖНО: обработчики кнопок меню стоят ВЫШЕ обработчиков FSM-шагов,
# чтобы нажатие кнопки в середине диалога не воспринималось как тикер/число.
# Каждый из них сбрасывает состояние.

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я присылаю алерты по ценам крипты (данные с Bybit).\n"
        "Выбери действие на клавиатуре ниже 👇",
        reply_markup=main_kb,
    )


@router.message(F.text == "ℹ️ Помощь")
async def help_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Как пользоваться:\n"
        "1. Нажми «➕ Создать алерт» и выбери тип\n"
        "2. Введи тикер пары (например, <code>BTCUSDT</code>)\n"
        "3. Задай условие и значение\n\n"
        "Типы алертов:\n"
        f"• 💰 Цена достигла уровня — бесплатно, до {FREE_ALERT_LIMIT} алертов\n"
        "• 📈 Рост/падение на % за период — премиум\n"
        "• 📊 Объём за 24ч — премиум\n"
        "• 💸 Фандинг — премиум\n\n"
        "Тикер — спот-пара, как на Bybit (для фандинга — бессрочный контракт). "
        "Цена указывается в валюте котировки, для BTCUSDT это USDT.\n\n"
        f"Премиум: {PREMIUM_PRICE_STARS} ⭐ в месяц, кнопка «⭐ Премиум».",
        reply_markup=main_kb,
    )


@router.message(F.text == "➕ Создать алерт")
async def start_create(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    premium = await is_user_premium(user_id)

    if premium and await count_user_alerts(user_id) >= PREMIUM_ALERT_LIMIT:
        await message.answer(f"Достигнут максимум: {PREMIUM_ALERT_LIMIT} алертов. Удали ненужные.")
        return

    await state.set_state(AlertForm.waiting_kind)
    await message.answer("Какой алерт создаём?", reply_markup=kind_kb(premium))


@router.message(F.text == "📋 Мои алерты")
async def list_alerts(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    user_alerts = await get_user_alerts(user_id)
    if not user_alerts:
        await message.answer("У тебя нет активных алертов.")
        return

    premium = await is_user_premium(user_id)
    allowed = allowed_alert_ids(user_alerts, {user_id} if premium else set())

    for a in user_alerts:
        if a.id not in allowed:
            status = "⏸ на паузе (нужен премиум)"
        elif a.triggered:
            status = "🔔 сработал"
        else:
            status = "⏳ ждёт"
        await message.answer(
            f"• {describe_alert(a)} — {status}",
            reply_markup=alert_item_kb(a.id),
        )


@router.message(F.text == "🗑 Удалить все")
async def delete_all(message: Message, state: FSMContext) -> None:
    await state.clear()
    deleted = await delete_all_user_alerts(message.from_user.id)
    await message.answer(f"Удалено алертов: {deleted}")


@router.message(F.text == "⭐ Премиум")
async def premium_info(message: Message, state: FSMContext) -> None:
    await state.clear()
    lifetime, until = await get_premium_status(message.from_user.id)

    if lifetime:
        await message.answer("У тебя премиум навсегда 🎉 Подписка не нужна.")
        return
    if until > time.time():
        await message.answer(
            f"⭐ Премиум активен до <b>{_date(until)}</b> (UTC).\n\n{FEATURES_TEXT}\n\n"
            "Подписка продлевается автоматически. Отменить автопродление можно "
            "в настройках Telegram, в разделе Stars: доступ сохранится до конца "
            "оплаченного периода."
        )
        return

    await message.answer(
        f"<b>Премиум</b> — {PREMIUM_PRICE_STARS} ⭐ в месяц:\n{FEATURES_TEXT}\n\n"
        f"Бесплатно: {FREE_ALERT_LIMIT} алерта «цена достигла уровня».\n"
        "Подписка продлевается автоматически каждые 30 дней, отменить можно "
        "в любой момент.",
        reply_markup=pay_kb(),
    )


# ---------- создание алерта (FSM) ----------

@router.callback_query(AlertForm.waiting_kind, F.data.startswith("kind:"))
async def got_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[1]
    if kind not in {KIND_PRICE, *PREMIUM_KINDS}:
        await callback.answer()
        return

    user_id = callback.from_user.id
    premium = await is_user_premium(user_id)

    if kind in PREMIUM_KINDS and not premium:
        await state.clear()
        await callback.message.edit_text("Этот тип алерта доступен в премиуме.")
        await _paywall(callback.message, "🔒")
        await callback.answer()
        return

    if kind == KIND_PRICE and not premium:
        if await count_user_alerts(user_id, KIND_PRICE) >= FREE_ALERT_LIMIT:
            await state.clear()
            await callback.message.edit_text(
                f"Бесплатный лимит исчерпан: {FREE_ALERT_LIMIT} алерта."
            )
            await _paywall(callback.message, "Хочешь больше алертов?")
            await callback.answer()
            return

    await state.update_data(kind=kind)
    await state.set_state(AlertForm.waiting_symbol)
    hint = (
        "Введи тикер бессрочного контракта (например, <code>BTCUSDT</code>):"
        if kind == KIND_FUNDING
        else "Введи тикер пары (например, <code>BTCUSDT</code>, <code>GRAMUSDT</code>):"
    )
    await callback.message.edit_text(hint, reply_markup=cancel_kb())
    await callback.answer()


@router.message(AlertForm.waiting_symbol, F.text)
async def got_symbol(message: Message, state: FSMContext) -> None:
    symbol = message.text.strip().upper()
    data = await state.get_data()
    kind = data["kind"]

    if not symbol.isascii() or " " in symbol:
        await message.answer(
            "Похоже на опечатку. Введи тикер латиницей, без пробелов "
            "(например, <code>BTCUSDT</code>)."
        )
        return

    if not await validate_symbol(symbol, kind):
        where = "среди бессрочных контрактов Bybit" if kind == KIND_FUNDING else "на Bybit (спот)"
        await message.answer(
            f"Пара <code>{symbol}</code> не найдена {where}.\n"
            "Проверь тикер — это должно быть что-то вроде <code>BTCUSDT</code>."
        )
        return

    await state.update_data(symbol=symbol)
    await state.set_state(AlertForm.waiting_direction)
    question = "Какое движение отслеживаем?" if kind == KIND_PCT else "Когда присылать алерт?"
    await message.answer(
        f"Пара: <b>{symbol}</b>\n{question}",
        reply_markup=direction_kb(kind),
    )


@router.message(AlertForm.waiting_symbol, ~F.text)
@router.message(AlertForm.waiting_value, ~F.text)
async def not_text(message: Message) -> None:
    await message.answer("Пришли, пожалуйста, текстом.")


def _value_prompt(kind: str, direction: str) -> str:
    if kind == KIND_PCT:
        word = "вырастет" if direction == "up" else "упадёт"
        return f"На сколько процентов должна измениться цена, чтобы я написал? (например, <code>5</code>)\nСлежу, пока цена {word}."
    word = "ниже" if direction == "below" else "выше"
    if kind == KIND_VOLUME:
        return (f"Пришли, когда объём за 24ч будет <b>{word}</b> какой суммы "
                "(в валюте котировки)?\nМожно с суффиксом: <code>500k</code>, "
                "<code>50m</code>, <code>1.5b</code>")
    if kind == KIND_FUNDING:
        return (f"Пришли, когда фандинг будет <b>{word}</b> какого значения (в %)?\n"
                "Например <code>0.05</code> или <code>-0.05</code>")
    return f"Пришли, когда цена будет <b>{word}</b> какой суммы (в USDT)?"


@router.callback_query(AlertForm.waiting_direction, F.data.startswith("dir:"))
async def got_direction(callback: CallbackQuery, state: FSMContext) -> None:
    direction = callback.data.split(":")[1]
    data = await state.get_data()
    kind = data["kind"]
    await state.update_data(direction=direction)

    if kind == KIND_PCT:
        await state.set_state(AlertForm.waiting_window)
        await callback.message.edit_text("За какой период считаем изменение?", reply_markup=window_kb())
    else:
        await state.set_state(AlertForm.waiting_value)
        await callback.message.edit_text(_value_prompt(kind, direction), reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(AlertForm.waiting_window, F.data.startswith("win:"))
async def got_window(callback: CallbackQuery, state: FSMContext) -> None:
    window = int(callback.data.split(":")[1])
    data = await state.get_data()
    await state.update_data(window_sec=window)
    await state.set_state(AlertForm.waiting_value)
    await callback.message.edit_text(
        _value_prompt(KIND_PCT, data["direction"]), reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(AlertForm.waiting_value, F.text)
async def got_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    kind = data["kind"]

    value = parse_number(
        message.text,
        any_sign=(kind == KIND_FUNDING),
        suffix=(kind == KIND_VOLUME),
    )
    if value is None or (kind == KIND_PCT and value > 1000):
        examples = {
            KIND_PRICE: "<code>60000</code> или <code>0.5</code>",
            KIND_PCT: "<code>5</code> или <code>2.5</code>",
            KIND_VOLUME: "<code>50m</code> или <code>500000</code>",
            KIND_FUNDING: "<code>0.05</code> или <code>-0.05</code>",
        }
        await message.answer(f"Нужно число, например {examples[kind]}")
        return

    alert = Alert(
        id=None,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        symbol=data["symbol"],
        threshold=value,
        direction=data["direction"],
        kind=kind,
        window_sec=data.get("window_sec", 0),
    )
    await state.update_data(threshold=value)
    await state.set_state(AlertForm.waiting_confirm)
    await message.answer(
        f"Проверь алерт:\n• {describe_alert(alert)}\n\nСоздаём?",
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
        threshold=data["threshold"],
        direction=data["direction"],
        kind=data["kind"],
        window_sec=data.get("window_sec", 0),
    )
    await add_alert(alert)
    await callback.message.edit_text(f"✅ Алерт создан:\n{describe_alert(alert)}")
    await callback.answer("Готово!")


@router.callback_query(F.data == "cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()


@router.callback_query(F.data.startswith("del:"))
async def delete_one(callback: CallbackQuery) -> None:
    alert_id = int(callback.data.split(":")[1])
    ok = await delete_alert(alert_id, callback.from_user.id)
    await callback.message.edit_text("🗑 Алерт удалён." if ok else "Алерт уже не найден.")
    await callback.answer()


# ---------- оплата: подписка в Telegram Stars ----------

@router.callback_query(F.data == "pay_premium")
async def send_subscription_link(callback: CallbackQuery) -> None:
    lifetime, until = await get_premium_status(callback.from_user.id)
    if lifetime or until > time.time():
        # не даём оформить вторую подписку поверх действующей
        await callback.answer("Премиум уже активен.", show_alert=True)
        return

    try:
        link = await callback.bot.create_invoice_link(
            title="Премиум на 30 дней",
            description="Алерты на %, объём и фандинг, до "
                        f"{PREMIUM_ALERT_LIMIT} алертов. Автопродление раз в 30 дней.",
            payload=PREMIUM_PAYLOAD,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Премиум · 30 дней", amount=PREMIUM_PRICE_STARS)],
            subscription_period=SUBSCRIPTION_PERIOD,
        )
    except TelegramBadRequest as e:
        await callback.answer("Не удалось создать счёт, попробуй позже.", show_alert=True)
        raise e

    await callback.message.answer(
        f"Подписка: {PREMIUM_PRICE_STARS} ⭐ каждые 30 дней, "
        "отменить можно в любой момент.",
        reply_markup=pay_link_kb(link),
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery) -> None:
    # Намеренно НЕ проверяем сумму и текущий премиум: если продления тоже
    # проходят через pre_checkout, то отказ тут оборвёт подписку действующему
    # пользователю (например, после смены цены в config.py).
    if query.invoice_payload != PREMIUM_PAYLOAD or query.currency != "XTR":
        await query.answer(ok=False, error_message="Некорректный платёж.")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if payment.invoice_payload != PREMIUM_PAYLOAD:
        return

    expires = payment.subscription_expiration_date or int(time.time()) + SUBSCRIPTION_PERIOD
    # charge_id сохраняем: он нужен для возврата (bot.refund_star_payment)
    is_new = await record_subscription_payment(
        user_id=message.from_user.id,
        charge_id=payment.telegram_payment_charge_id,
        amount=payment.total_amount,
        payload=payment.invoice_payload,
        expires_at=expires,
        is_recurring=bool(payment.is_recurring),
    )
    if not is_new:
        return

    if payment.is_recurring and not payment.is_first_recurring:
        await message.answer(f"🔄 Подписка продлена до {_date(expires)} (UTC). Спасибо!")
    else:
        await message.answer(
            f"✅ Премиум активен до {_date(expires)} (UTC)!\n"
            "Теперь доступны алерты на %, объём и фандинг.",
            reply_markup=main_kb,
        )