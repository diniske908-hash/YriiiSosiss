"""Генерация персональных демо-ботов и писем для клиник.

python -m business.make_demos --limit 10
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "demo_template.html"
OUT = ROOT / "demos"
LEADS = ROOT / "leads_ufa_dentist.csv"

DEFAULT_PRICES = [
    "Консультация — 0 ₽",
    "Чистка зубов — от 3 500 ₽",
    "Лечение кариеса — от 4 500 ₽",
    "Имплант под ключ — от 35 000 ₽",
    "Брекеты — от 60 000 ₽",
]


def slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "-", name.lower()).strip("-")
    return s[:40] or "clinic"


def make_demo(row: dict) -> Path:
    html = TEMPLATE.read_text(encoding="utf-8")
    name = row["name"]
    html = (html
            .replace("__CLINIC__", name)
            .replace("__INIT__", name[:1].upper())
            .replace("__PHONE__", row.get("phone") or "")
            .replace("__ADDRESS__", (row.get("address") or "").replace('"', ""))
            .replace("__PRICES__", json.dumps(DEFAULT_PRICES, ensure_ascii=False)))
    out = OUT / f"{slug(name)}.html"
    out.write_text(html, encoding="utf-8")
    return out


def make_message(row: dict, link: str) -> str:
    name = row["name"]
    has_site = bool(row.get("website"))
    if not has_site:
        opener = f"Смотрел клиники Уфы — у «{name}» не нашёл онлайн-записи."
    else:
        opener = f"Зашёл на сайт «{name}» — записи онлайн нет, только телефон."
    return (
        f"Здравствуйте! Я Данила, разработчик из Уфы.\n\n"
        f"{opener}\n"
        f"Сделал демо-бота для вашей клиники: {link}\n"
        f"Пациент сам выбирает услугу и время, вам падает готовая запись — без звонков.\n\n"
        f"Если не актуально — просто скажите, больше не напишу.\n"
        f"Показать, как это будет работать на вашем прайсе?"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--with-phone", action="store_true", default=True)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(LEADS, encoding="utf-8-sig")))
    picks = [r for r in rows if (r.get("phone") or "").strip()][: args.limit]

    lines = []
    for r in picks:
        path = make_demo(r)
        link = f"[ссылка на демо: {path.name}]"
        msg = make_message(r, link)
        lines.append(f"### {r['name']}\nТелефон: {r.get('phone','')}\nФайл: {path.name}\n\n{msg}\n")
        print(f"демо: {path.name}")

    (OUT / "messages.md").write_text("\n---\n\n".join(lines), encoding="utf-8")
    print(f"\nвсего демо: {len(picks)}")
    print(f"письма: {OUT / 'messages.md'}")


if __name__ == "__main__":
    main()
