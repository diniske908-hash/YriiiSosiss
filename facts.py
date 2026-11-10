"""Факты о клинике из её сайта: часы работы, есть ли онлайн-запись и бот.

Нужно, чтобы письмо было персональным и не врало: «вы работаете до 20:00»,
«у вас стоит YCLIENTS», «у вас есть бот, но записи в нём нет».

    from facts import collect
    collect("https://example.ru") -> {...}
"""
from __future__ import annotations

import re
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# признаки систем онлайн-записи
SYSTEMS = {
    "yclients": ["yclients", "yclients.com", "ycms"],
    "dikidi": ["dikidi"],
    "altegio": ["altegio"],
    "simplybook": ["simplybook"],
    "bookform": ["bookform", "bookform.ru"],
    "telegram_bot": ["t.me/", "telegram.me/"],
    "vk": ["vk.me/", "vk.com/write", "vk.com/app"],
}

BOOKING_WORDS = [
    "онлайн-запис", "онлайн запис", "записаться онлайн", "запись онлайн",
    "записаться на приём", "записаться на прием", "запись на приём",
    "запись на прием", "book online", "забронировать",
]

HOURS_RE = re.compile(
    r"((?:ежедневно|пн|вт|ср|чт|пт|сб|вс|круглосуточно)[^.\n]{0,40}?"
    r"\d{1,2}[:.]\d{2}[^.\n]{0,25}?\d{1,2}[:.]\d{2}"
    r"|круглосуточно"
    r"|\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}[:.]\d{2}"
    r"|с\s*\d{1,2}[:.]\d{2}\s*до\s*\d{1,2}[:.]\d{2})",
    re.IGNORECASE,
)


def fetch(url: str, limit: int = 6000) -> tuple[str, str]:
    """Возвращает (текст без тегов, сырой html). Пустые строки, если не открылось."""
    if not url:
        return "", ""
    if not url.startswith("http"):
        url = "http://" + url
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(400_000)
        html = raw.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return "", ""

    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&laquo;", "«").replace("&raquo;", "»"))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit], html


def detect_systems(html: str) -> list[str]:
    low = html.lower()
    found = []
    for name, signs in SYSTEMS.items():
        if any(sign in low for sign in signs):
            found.append(name)
    return found


def detect_booking(text: str, html: str) -> tuple[bool, list[str]]:
    low = (text + " " + html).lower()
    systems = detect_systems(html)
    words = [w for w in BOOKING_WORDS if w in low]
    has = bool(words or [s for s in systems if s != "telegram_bot"])
    return has, systems


def detect_hours(text: str) -> str:
    m = HOURS_RE.search(text)
    if not m:
        return ""
    value = re.sub(r"\s+", " ", m.group(0)).strip(" ,.")
    value = value.replace(".", ":")
    return value[:60]


def collect(url: str) -> dict:
    text, html = fetch(url)
    has_booking, systems = detect_booking(text, html)
    hours = detect_hours(text)

    # часы часто лежат отдельной страницей «Контакты» — заглянем туда
    if not hours and text and url:
        base = url.rstrip("/")
        if not base.startswith("http"):
            base = "http://" + base
        for path in ("/contacts", "/kontakty", "/contact", "/about", "/o-nas", "/klinika"):
            extra, extra_html = fetch(base + path, limit=4000)
            if not extra:
                continue
            hours = detect_hours(extra)
            if hours:
                if not has_booking:
                    has_booking, systems = detect_booking(extra, extra_html)
                break

    return {
        "site_ok": bool(text),
        "text": text,
        "hours": hours,
        "has_booking": has_booking,
        "systems": systems,
        "has_bot": "telegram_bot" in systems,
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        data = collect(sys.argv[1])
        data.pop("text", None)
        print(json.dumps(data, ensure_ascii=False, indent=2))
