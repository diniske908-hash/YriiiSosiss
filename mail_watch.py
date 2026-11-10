"""Сторож почты: пересылает в Telegram только то, что касается клиник.

Правила: письмо считается важным, если
  • в теме есть «заявка» (заявка из демо);
  • отправитель есть в нашей базе клиник;
  • в теме есть слова бот / запись / клиника / демо.
Всё остальное (рассылки, чеки, реклама) пропускается и помечается прочитанным.

    python business/mail_watch.py
    python business/mail_watch.py --once
    python business/mail_watch.py --skip-all    # пометить всё текущее прочитанным
"""
from __future__ import annotations
import os

import csv
import datetime as dt
import email
import imaplib
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from email.header import decode_header
from pathlib import Path

import relay
from events import log as ev_log

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "_mail.json").read_text(encoding="utf-8"))
SEEN = ROOT / "_mail_seen.json"
TOKEN = os.environ.get("TG_TOKEN", "")
OWNER = 564920456

KEYWORDS = ("бот", "запис", "клиник", "демо", "заявк", "сайт")


def decode(value: str) -> str:
    parts = []
    for chunk, enc in decode_header(value or ""):
        parts.append(chunk.decode(enc or "utf-8", "replace") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def clinic_emails() -> set[str]:
    """Почты клиник из нашей базы — их письма важны всегда."""
    found: set[str] = set()
    for name in ("leads_ufa_dentist.csv", "leads_ufa_clinic.csv", "leads_ufa_beauty.csv"):
        path = ROOT / name
        if not path.exists():
            continue
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            addr = (row.get("email") or "").strip().lower()
            if addr:
                found.add(addr)
    return found


def body_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:  # noqa: BLE001
                    continue
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""



def spam_folder(box) -> str | None:
    """Возвращает имя папки «Спам» в кавычках, готовое для IMAP.

    Формат строки LIST: (флаги) "разделитель" ИмяПапки
    """
    try:
        status, data = box.list()
        for raw in data or []:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            m = re.match(r'\([^)]*\)\s+"([^"]*)"\s+(.+)$', line)
            if not m:
                continue
            name = m.group(2).strip().strip('"')
            if name.lower() in ("spam", "\u0441\u043f\u0430\u043c", "junk"):
                return '"' + name + '"'
    except Exception:  # noqa: BLE001
        pass
    return None


def tg(text: str) -> None:
    data = urllib.parse.urlencode({"chat_id": OWNER, "text": text[:3500],
                                   "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data, timeout=30)


def load_seen() -> set[str]:
    if SEEN.exists():
        try:
            return set(json.loads(SEEN.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN.write_text(json.dumps(sorted(seen)[-2000:], ensure_ascii=False), encoding="utf-8")


def is_important(subject: str, sender: str, known: set[str]) -> bool:
    low_subj = subject.lower()
    low_from = sender.lower()
    addr = (re.findall(r"[\w\.\-+]+@[\w\.\-]+", low_from) or [""])[0]
    if "заявк" in low_subj:
        return True
    if addr in known:
        return True
    if "danzinowjev" in low_from or "zynych" in low_from:
        return False
    return any(word in low_subj for word in KEYWORDS)


def is_bulk(msg) -> bool:
    if msg.get("List-Unsubscribe"):
        return True
    return (msg.get("Precedence", "") or "").lower() in ("bulk", "list", "junk")


def check_once(skip_all: bool = False) -> int:
    seen = load_seen()
    known = clinic_emails()
    handled = 0

    with imaplib.IMAP4_SSL("imap.yandex.ru", 993, ssl_context=ssl.create_default_context()) as box:
        box.login(CFG["login"], CFG["password"])
        box.select("INBOX")
        # читаем не только UNSEEN: если владелец открыл письмо в Яндекс.Почте,
        # оно всё равно должно попасть в админку
        since = (dt.datetime.now() - dt.timedelta(days=3)).strftime("%d-%b-%Y")
        status, data = box.search(None, "SINCE", since)
        if status != "OK":
            return 0
        ids = (data[0].split() or [])[-30:]

        for num in ids:
            status, raw = box.fetch(num, "(RFC822)")
            if status != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            msg = email.message_from_bytes(raw[0][1])
            legacy = f"{num.decode()}-{msg.get('Date', '')}"
            uid = (msg.get("Message-ID") or legacy).strip()
            if uid in seen or legacy in seen:
                continue
            seen.add(uid)
            seen.add(legacy)
            if skip_all or is_bulk(msg):
                continue

            subject = decode(msg.get("Subject", ""))
            sender = decode(msg.get("From", ""))
            low_from = sender.lower()
            if any(w in low_from for w in ("no-reply", "noreply", "mailer-daemon")):
                continue
            text = body_text(msg).strip()[:1200]
            name = re.sub(r"<[^>]*>", "", sender).strip().strip('"') or sender
            addr = (re.findall(r"[\w\.\-+]+@[\w\.\-]+", sender) or [""])[0]
            important = is_important(subject, sender, known)
            if addr and addr.lower() == (CFG.get("login") or "").lower():
                continue          # свои исходящие уже в админке, не дублируем
            if addr:
                # в админку попадают все обычные письма; в Telegram — только важные
                ev_log("email", "message", f"{subject}\n\n{text}", name,
                       {"chat_id": addr, "channel": "email", "mail_important": important})
                handled += 1
            if important:
                if addr:
                    relay.remember_email(sender, subject, text, name)
                else:
                    kind = "📥 Заявка из демо" if "заявк" in subject.lower() else "✉️ Письмо клиента"
                    tg(f"{kind}\n\nТема: {subject}\nОт: {sender}\n\n{text}"[:3500])

    save_seen(seen)
    return handled


def main() -> None:
    from lock import acquire
    acquire("mail_watch")

    if "--skip-all" in sys.argv:
        n = check_once(skip_all=True)
        print(f"помечено прочитанным: {n}")
        return
    if "--once" in sys.argv:
        print("писем в админку:", check_once())
        return
    print("сторож почты запущен: письма идут в админку, важные — в Telegram", flush=True)
    while True:
        try:
            n = check_once()
            if n:
                print(f"  писем в админку: {n}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print("ошибка почты:", type(exc).__name__, str(exc)[:120], flush=True)
        time.sleep(40)


if __name__ == "__main__":
    main()
