"""Типы алертов, форматирование, разбор чисел и правила доступа (free/premium)."""
import math

from config import FREE_ALERT_LIMIT
from price_service import fmt_price

KIND_PRICE = "price"      # цена выше/ниже уровня            (бесплатно)
KIND_PCT = "pct"          # рост/падение на X% за период      (премиум)
KIND_VOLUME = "volume"    # объём за 24ч выше/ниже уровня     (премиум)
KIND_FUNDING = "funding"  # ставка фандинга выше/ниже уровня  (премиум)

PREMIUM_KINDS = {KIND_PCT, KIND_VOLUME, KIND_FUNDING}

# окна для алерта на % (секунды -> подпись)
WINDOWS = {300: "5 мин", 900: "15 мин", 3600: "1 час", 86400: "24 часа"}


def fmt_big(x: float) -> str:
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= limit:
            return f"{x / limit:.2f}".rstrip("0").rstrip(".") + suffix
    return fmt_price(x)


def window_label(seconds: int) -> str:
    return WINDOWS.get(seconds, f"{seconds} с")


def describe_alert(a) -> str:
    if a.kind == KIND_PCT:
        word = "рост на" if a.direction == "up" else "падение на"
        return f"{a.symbol}: {word} {fmt_price(a.threshold)}% за {window_label(a.window_sec)}"
    word = "ниже" if a.direction == "below" else "выше"
    if a.kind == KIND_VOLUME:
        return f"{a.symbol}: объём за 24ч {word} {fmt_big(a.threshold)}"
    if a.kind == KIND_FUNDING:
        return f"{a.symbol}: фандинг {word} {fmt_price(a.threshold)}%"
    return f"{a.symbol}: цена {word} {fmt_price(a.threshold)} USDT"


def notification_text(a, value: float, price: float | None) -> str:
    price_line = f"\nСейчас: {fmt_price(price)}$" if price is not None else ""
    if a.kind == KIND_PCT:
        emoji = "📈" if a.direction == "up" else "📉"
        return f"{emoji} {a.symbol}: {value:+.2f}% за {window_label(a.window_sec)}{price_line}"
    word = "ниже" if a.direction == "below" else "выше"
    if a.kind == KIND_VOLUME:
        return (f"📊 {a.symbol}: объём за 24ч {fmt_big(value)} "
                f"({word} {fmt_big(a.threshold)}){price_line}")
    if a.kind == KIND_FUNDING:
        return (f"💸 {a.symbol}: фандинг {value:+.4f}% "
                f"({word} {fmt_price(a.threshold)}%){price_line}")
    return (f"🚩🚩🚩 {a.symbol} сейчас {fmt_price(value)}$ 🚩🚩🚩\n"
            f"({word} {fmt_price(a.threshold)}$)")


_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_number(text: str, *, any_sign: bool = False, suffix: bool = False) -> float | None:
    """Разбирает число из ввода. any_sign=True разрешает 0 и отрицательные,
    иначе нужно число > 0. suffix=True понимает 50k / 2.5m / 1b."""
    t = text.strip().lower().replace(",", ".").replace("$", "").replace("%", "")
    t = t.replace(" ", "").replace("_", "")
    mult = 1.0
    if suffix and t and t[-1] in _SUFFIX:
        mult = _SUFFIX[t[-1]]
        t = t[:-1]
    try:
        value = float(t) * mult
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    if not any_sign and value <= 0:
        return None
    return value


def allowed_alert_ids(alerts, premium_user_ids: set[int]) -> set[int]:
    """Какие алерты сейчас имеют право работать.

    Премиум: все. Бесплатные: только "цена" и только первые FREE_ALERT_LIMIT
    (по id). Остальные ставятся на паузу — не удаляются, и оживут при
    возобновлении подписки. Так нельзя оплатить месяц, наделать алертов
    и пользоваться ими бесплатно.
    """
    allowed: set[int] = set()
    used: dict[int, int] = {}
    for a in sorted(alerts, key=lambda x: x.id):
        if a.user_id in premium_user_ids:
            allowed.add(a.id)
        elif a.kind == KIND_PRICE and used.get(a.user_id, 0) < FREE_ALERT_LIMIT:
            used[a.user_id] = used.get(a.user_id, 0) + 1
            allowed.add(a.id)
    return allowed


_QUOTES = ("USDT", "USDC", "EUR", "DAI", "BTC", "ETH")


def format_symbol_info(symbol: str, kind: str, info) -> str:
    """Текст «текущая цена» для сообщений при создании алерта (HTML)."""
    quote = next((q for q in _QUOTES if symbol.endswith(q)), "")
    lines = [f"Текущая цена {symbol}: <b>{fmt_price(info.price)}</b> {quote}".rstrip()]
    if kind == KIND_PCT and info.change24h_pct is not None:
        lines.append(f"За 24ч: {info.change24h_pct:+.2f}%")
    if kind == KIND_VOLUME and info.turnover24h is not None:
        lines.append(f"Объём за 24ч: <b>{fmt_big(info.turnover24h)}</b> {quote}".rstrip())
    if kind == KIND_FUNDING and info.funding is not None:
        lines.append(f"Фандинг сейчас: <b>{info.funding:+.4f}%</b>")
    return "\n".join(lines)