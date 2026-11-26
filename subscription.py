"""Обязательная подписка на каналы-партнёры перед созданием алерта."""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

# Список каналов читается при каждой проверке, поэтому партнёров можно
# добавлять и убирать без перезапуска бота.
CHANNELS_FILE = Path(__file__).parent / "channels.json"

# успешную проверку помним коротко, чтобы не дёргать API на каждом шаге диалога
_OK_TTL = 60
_ok_until: dict[tuple[int, str], float] = {}


@dataclass(frozen=True)
class Channel:
    chat_id: int | str   # "@username" или числовой id вида -100123...
    title: str
    url: str


def load_channels() -> list[Channel]:
    try:
        raw = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.exception("Не удалось прочитать %s — проверка подписки отключена", CHANNELS_FILE)
        return []

    channels: list[Channel] = []
    for item in raw:
        chat_id = item.get("chat_id")
        if chat_id is None:
            continue
        if isinstance(chat_id, str) and chat_id.lstrip("-").isdigit():
            chat_id = int(chat_id)
        url = item.get("url")
        if not url and isinstance(chat_id, str) and chat_id.startswith("@"):
            url = f"https://t.me/{chat_id[1:]}"
        if not url:
            logger.warning("Канал %s пропущен: нет url (для приватных нужна invite-ссылка)", chat_id)
            continue
        channels.append(Channel(chat_id, item.get("title") or str(chat_id), url))
    return channels


async def _is_member(bot: Bot, channel: Channel, user_id: int) -> bool:
    key = (user_id, str(channel.chat_id))
    if _ok_until.get(key, 0) > time.time():
        return True

    try:
        member = await bot.get_chat_member(channel.chat_id, user_id)
    except TelegramAPIError as e:
        # Ошибка настройки (бот не админ в канале, неверный id) не должна
        # блокировать пользователей — пропускаем, но громко пишем в лог.
        logger.error(
            "Не могу проверить подписку на %s (%s). Бот должен быть администратором канала.",
            channel.chat_id, e,
        )
        return True

    status = str(getattr(member.status, "value", member.status))
    ok = status in ("creator", "administrator", "member") or (
        status == "restricted" and bool(getattr(member, "is_member", False))
    )
    if ok:
        _ok_until[key] = time.time() + _OK_TTL
    return ok


async def missing_channels(bot: Bot, user_id: int) -> list[Channel]:
    """Каналы из channels.json, на которые пользователь ещё не подписан."""
    channels = load_channels()
    if not channels:
        return []
    results = await asyncio.gather(*(_is_member(bot, c, user_id) for c in channels))
    return [c for c, ok in zip(channels, results) if not ok]