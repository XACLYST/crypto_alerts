"""Разбор текстовой команды /alert. Без обращений к сети и к Telegram."""
import re
from dataclasses import dataclass

from alert_types import (
    KIND_FUNDING,
    KIND_PCT,
    KIND_PRICE,
    KIND_VOLUME,
    WINDOWS,
    parse_number,
)


class ParseError(ValueError):
    """Понятное пользователю сообщение о том, что не так в команде."""


@dataclass(frozen=True)
class ParsedAlert:
    symbol: str                # как ввёл пользователь, верхний регистр, без "/"
    kind: str
    direction: str | None      # None -> определить по текущей цене (только для price)
    threshold: float
    window_sec: int = 0


_ABOVE = {">", ">=", "above", "over", "выше"}
_BELOW = {"<", "<=", "below", "under", "ниже"}
_UP = {"up", "+", "рост", "вверх", "pump"}
_DOWN = {"down", "-", "падение", "вниз", "dump"}
_VOLUME = {"vol", "volume", "объём", "объем"}
_FUNDING = {"fund", "funding", "фандинг"}

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")
_WINDOW_RE = re.compile(r"^(\d+)(m|min|м|мин|h|hr|ч|час|d|д|сут)$")
_UNIT_SECONDS = {
    "m": 60, "min": 60, "м": 60, "мин": 60,
    "h": 3600, "hr": 3600, "ч": 3600, "час": 3600,
    "d": 86400, "д": 86400, "сут": 86400,
}
DEFAULT_WINDOW = 3600


def _normalize(text: str) -> list[str]:
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"(>=|<=|>|<)", r" \1 ", text)          # BTC>70000 -> BTC > 70000
    text = re.sub(r"(?<=[A-Za-z])([+-])(?=\d)", r" \1", text)  # ETH-5% -> ETH -5%
    return text.split()


def _parse_level(kind: str, rest: list[str]) -> ParsedAlert:
    direction = None
    values: list[str] = []
    for t in rest:
        if t in _ABOVE or t in _BELOW:
            new = "above" if t in _ABOVE else "below"
            if direction and direction != new:
                raise ParseError("Противоречивое условие: и «выше», и «ниже».")
            direction = new
        else:
            values.append(t)

    if len(values) != 1:
        raise ParseError("Не получилось найти значение. Пример: /alert BTC > 70000")
    value = parse_number(values[0], any_sign=(kind == KIND_FUNDING), suffix=(kind != KIND_FUNDING))
    if value is None:
        raise ParseError(f"Не понял число: {values[0]}")
    if kind != KIND_PRICE and direction is None:
        raise ParseError("Укажи условие: > (выше) или < (ниже).")
    return ParsedAlert("", kind, direction, value)


def _parse_pct(rest: list[str]) -> ParsedAlert:
    word_dir = None
    sign_dir = None
    window = None
    value = None

    for t in rest:
        if t in _UP or t in _DOWN:
            new = "up" if t in _UP else "down"
            if word_dir and word_dir != new:
                raise ParseError("Противоречивое условие: и рост, и падение.")
            word_dir = new
            continue
        if "%" not in t and _WINDOW_RE.match(t):
            if window is not None:
                raise ParseError("Период указан дважды.")
            n, unit = _WINDOW_RE.match(t).groups()
            window = int(n) * _UNIT_SECONDS[unit]
            continue

        s = t
        if s.startswith("+"):
            s, new = s[1:], "up"
        elif s.startswith("-"):
            s, new = s[1:], "down"
        else:
            new = None
        number = parse_number(s)
        if number is None or value is not None:
            raise ParseError(f"Не понял: {t}")
        value = number
        sign_dir = new

    if value is None:
        raise ParseError("Не нашёл процент. Пример: /alert ETH +5% 1h")
    if value > 1000:
        raise ParseError("Слишком большой процент.")
    if word_dir and sign_dir and word_dir != sign_dir:
        raise ParseError("Знак и слово противоречат друг другу (рост/падение).")
    direction = word_dir or sign_dir
    if direction is None:
        raise ParseError("Укажи рост или падение: +5% или -5%.")

    window = DEFAULT_WINDOW if window is None else window
    if window not in WINDOWS:
        allowed = ", ".join(["5m", "15m", "1h", "24h"])
        raise ParseError(f"Такой период не поддерживается. Доступно: {allowed}.")
    return ParsedAlert("", KIND_PCT, direction, value, window)


def parse_alert_command(text: str) -> ParsedAlert:
    tokens = _normalize(text)
    if not tokens:
        raise ParseError("Пустая команда.")

    symbol = tokens[0].upper().replace("/", "")
    if not _SYMBOL_RE.match(symbol):
        raise ParseError(f"Не похоже на тикер: {tokens[0]}")

    rest = [t.lower() for t in tokens[1:]]
    if not rest:
        raise ParseError("Укажи условие. Пример: /alert BTC > 70000")

    if any(t in _VOLUME for t in rest):
        parsed = _parse_level(KIND_VOLUME, [t for t in rest if t not in _VOLUME])
    elif any(t in _FUNDING for t in rest):
        parsed = _parse_level(KIND_FUNDING, [t for t in rest if t not in _FUNDING])
    elif any("%" in t or t in _UP or t in _DOWN for t in rest):
        parsed = _parse_pct(rest)
    else:
        parsed = _parse_level(KIND_PRICE, rest)

    return ParsedAlert(symbol, parsed.kind, parsed.direction, parsed.threshold, parsed.window_sec)