"""Передача диалога человеку: пока владелец отвечает, бот молчит.

Ключ — канал + чат, чтобы Telegram и MAX с одинаковым id не конфликтовали.
Пауза скользящая: каждый новый ответ владельца продлевает её.

    handoff.mute("tg", 123456, hours=6)
    handoff.is_muted("tg", 123456)
    handoff.resume("tg", 123456)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILE = ROOT / "_handoff.json"
DEFAULT_HOURS = 6


def key(channel: str, chat) -> str:
    ch = (channel or "tg").lower()
    if ch not in ("tg", "max", "email"):
        ch = "tg"
    return f"{ch}:{chat}"


def _load() -> dict:
    if FILE.exists():
        try:
            return json.loads(FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save(data: dict) -> None:
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def mute(channel: str, chat, hours: float = DEFAULT_HOURS) -> None:
    data = _load()
    data[key(channel, chat)] = {
        "until": time.time() + hours * 3600,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": (channel or "tg").lower() if (channel or "").lower() in ("tg", "max", "email") else "tg",
        "chat": str(chat),
        "hours": hours,
    }
    _save(data)


def resume(channel: str, chat) -> None:
    data = _load()
    data.pop(key(channel, chat), None)
    _save(data)


def unmute(chat) -> None:
    """Совместимость: снимает обе записи (tg и max)."""
    data = _load()
    for ch in ("tg", "max"):
        data.pop(key(ch, chat), None)
    _save(data)


def is_muted(channel_or_chat, chat=None) -> bool:
    """Можно вызывать как is_muted(chat) или is_muted('max', chat)."""
    if chat is None:
        channel, chat = "tg", channel_or_chat
        # проверяем оба канала — старый вызов без канала
        for ch in ("tg", "max"):
            if _check(ch, chat):
                return True
        return False
    return _check(channel_or_chat, chat)


def _check(channel: str, chat) -> bool:
    data = _load()
    k = key(channel, chat)
    item = data.get(k)
    if not item:
        return False
    if item.get("until", 0) < time.time():
        data.pop(k, None)
        _save(data)
        return False
    return True


def info(channel: str, chat) -> dict:
    return _load().get(key(channel, chat), {})


def active() -> dict:
    """Все активные паузы: {'tg:123': {...}}."""
    data = _load()
    now = time.time()
    return {k: v for k, v in data.items() if v.get("until", 0) > now}
