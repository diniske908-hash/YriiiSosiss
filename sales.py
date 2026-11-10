"""Продающий сценарий бота: прайс, заявка, приём ошибок.

Состояние диалога хранится в _chat_states.json, чтобы бот помнил, на каком шаге клиент.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATES = ROOT / "_chat_states.json"

PRICE_TEXT = (
    "<b>Бот записи — 10 000 ₽</b>\n"
    "Запуск 5–10 дней · оплата 50/50 · правки 14 дней бесплатно"
)

EXTRAS_TEXT = (
    "<b>Что можно добавить</b>\n\n"
    "• сайт с записью — 20 000 ₽\n"
    "• напоминания клиентам — +5 000 ₽\n"
    "• поддержка после запуска — 2 000 ₽/мес\n"
    "• своё оформление — от 15 000 ₽\n"
    "• свой домен — +3 000 ₽\n"
    "• связка с CRM — от 10 000 ₽"
)

WHAT_TEXT = (
    "<b>Что входит</b>\n\n"
    "• запись: услуга, день, время\n"
    "• заявка администратору\n"
    "• перенос и отмена с причиной\n"
    "• маршрут до клиники и звонок в один клик\n"
    "• бот под ваш прайс и услуги"
)

DEMO_TEXT = (
    "Вот как это выглядит для пациента — можно потыкать:\n"
    "https://ufa-zapis.surge.sh/demos/moj-doktor.html\n\n"
    "Там запись за 40 секунд: услуга → время → имя и телефон."
)

MENU_KB = {"inline_keyboard": [
    [{"text": "👀 Посмотреть пример", "url": "https://ufa-zapis.surge.sh/demos/moj-doktor.html"}],
    [{"text": "💰 Цена и что входит", "callback_data": "sale:price"}],
    [{"text": "🚀 Оставить заявку", "callback_data": "sale:order"}],
    [{"text": "💬 Задать вопрос", "callback_data": "sale:bug"}],
]}

BACK_KB = {"inline_keyboard": [[{"text": "← В начало", "callback_data": "sale:menu"}]]}

NEXT_KB = {"inline_keyboard": [
    [{"text": "🚀 Оставить заявку", "callback_data": "sale:order"}],
    [{"text": "👀 Посмотреть пример", "url": "https://ufa-zapis.surge.sh/demos/moj-doktor.html"}],
    [{"text": "← В начало", "callback_data": "sale:menu"}],
]}


def load() -> dict:
    if STATES.exists():
        try:
            return json.loads(STATES.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save(data: dict) -> None:
    STATES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


TTL_SEC = 60 * 60          # через полчаса незаконченный диалог забываем


def step(chat_id: int) -> dict:
    data = load().get(str(chat_id), {})
    if not data:
        return {}
    if time.time() - float(data.get("ts", 0)) > TTL_SEC:
        clear(chat_id)
        return {}
    return data


def set_step(chat_id: int, data: dict) -> None:
    allstates = load()
    data["ts"] = time.time()
    allstates[str(chat_id)] = data
    save(allstates)


def clear(chat_id: int) -> None:
    allstates = load()
    allstates.pop(str(chat_id), None)
    save(allstates)
