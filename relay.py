"""Релей сообщений: всё от клиентов — владельцу в Telegram, ответ — обратно в тот же канал.

    relay.notify("max", 266502994, "Виктория", "сколько стоит?", clinic="Милена")
    relay.send_reply("max", "266502994", "Здравствуйте! ...")
"""
from __future__ import annotations
import os

import html
import json
import smtplib
import ssl
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TG_TOKEN = os.environ.get("TG_TOKEN", "")
OWNER_TG = 564920456

CHANNEL_NAMES = {"tg": "Telegram", "max": "MAX", "email": "почта"}
MAP_FILE = ROOT / "_relay_map.json"
CONFIG = ROOT / "_relay_target.json"


def notify_target(default: int = OWNER_TG) -> int:
    """Куда слать уведомления: личка или отдельная группа (задаётся в _relay_target.json)."""
    if CONFIG.exists():
        try:
            data = json.loads(CONFIG.read_text(encoding="utf-8"))
            if data.get("chat_id"):
                return int(data["chat_id"])
        except Exception:  # noqa: BLE001
            pass
    return default


def _map_load() -> dict:
    if MAP_FILE.exists():
        try:
            return json.loads(MAP_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _map_save(data: dict) -> None:
    MAP_FILE.write_text(json.dumps(data, ensure_ascii=False)[:200000], encoding="utf-8")


def bind(message_id: int, channel: str, chat) -> None:
    data = _map_load()
    data[str(message_id)] = {"channel": channel, "chat": str(chat)}
    _map_save(data)


def lookup(message_id: int) -> dict | None:
    return _map_load().get(str(message_id))


def _tg(method: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/{method}",
                                    data=data, timeout=25) as resp:
            return json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001
        return {}


def summarize(text: str) -> str:
    """Коротко: чего хочет клиент. Сначала правила, потом нейросеть."""
    low = (text or "").lower()
    if "заявк" in low or "записаться" in low:
        return "оставляет заявку"
    if any(w in low for w in ("сколько", "цена", "стоит", "прайс")):
        return "спрашивает цену"
    if any(w in low for w in ("срок", "когда будет", "как быстро")):
        return "спрашивает сроки"
    if any(w in low for w in ("не работает", "ошибк", "сломал", "не открывается")):
        return "сообщает об ошибке"
    if any(w in low for w in ("демо", "пример", "показать")):
        return "просит показать пример"
    if any(w in low for w in ("сайт", "дизайн", "crm", "домен")):
        return "спрашивает про доработки"

    try:
        from llm import chat
        answer = chat([{"role": "user", "content":
                        "Одной строкой до 6 слов: чего хочет клиент в сообщении: "
                        + text[:300]}], max_tokens=30, temperature=0.1, retries=1).strip()
        if answer and len(answer) < 80:
            return answer.lower()
    except Exception:  # noqa: BLE001
        pass
    return "написал сообщение"


def notify(channel: str, chat, who: str, text: str, clinic: str = "") -> None:
    """Присылает владельцу в личку сообщение клиента с подписью."""
    ch = (channel or "tg").lower()
    ch = "max" if ch == "max" else ("email" if ch == "email" else "tg")
    hospital = clinic or "не указана"
    body = (
        f"<b>Клиника:</b> {html.escape(hospital)}\n"
        f"<b>Хочет:</b> {html.escape(summarize(text))}\n"
        f"<b>Канал:</b> {CHANNEL_NAMES.get(ch, ch)} · {html.escape(str(who))}\n\n"
        f"{html.escape((text or '')[:700])}"
    )
    kb = {"inline_keyboard": [[
        {"text": "✍️ Ответить", "callback_data": f"reply:{ch}:{chat}"},
    ]]}
    res = _tg("sendMessage", {"chat_id": notify_target(), "text": body,
                              "parse_mode": "HTML",
                              "reply_markup": json.dumps(kb, ensure_ascii=False)})
    if res.get("ok"):
        bind(res["result"]["message_id"], ch, chat)


def send_reply(channel: str, chat, text: str) -> bool:
    """Отправляет ответ владельца в тот канал, откуда пришёл клиент."""
    ch = (channel or "tg").lower()

    if ch in ("whatsapp", "wa"):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8790/send",
                data=json.dumps({"chat": str(chat), "text": text}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    if ch == "max":
        try:
            from maxapi import api
            status, _ = api("POST", f"/messages?user_id={chat}", {"text": text})
            return status == 200
        except Exception:  # noqa: BLE001
            return False

    if ch == "email":
        try:
            cfg = json.loads((ROOT / "_mail.json").read_text(encoding="utf-8"))
            msg = EmailMessage()
            msg["From"] = formataddr((cfg.get("from_name", "Зиныч IT"), cfg["login"]))
            msg["To"] = str(chat)
            msg["Subject"] = "Ответ на ваше сообщение — Зиныч IT"
            msg.set_content(text)
            with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]),
                                  context=ssl.create_default_context(), timeout=40) as server:
                server.login(cfg["login"], cfg["password"])
                server.send_message(msg)
            return True
        except Exception:  # noqa: BLE001
            return False

    res = _tg("sendMessage", {"chat_id": chat, "text": text})
    return bool(res.get("ok"))


def remember_email(sender: str, subject: str, text: str, who: str = "") -> None:
    """Письмо клиента тоже попадает владельцу с кнопкой ответа."""
    import re
    addr = (re.findall(r"[\w\.\-+]+@[\w\.\-]+", sender or "") or [""])[0]
    if not addr:
        return
    notify("email", addr, who or addr, f"{subject}\n\n{text}", clinic="")
