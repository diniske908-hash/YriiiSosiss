"""Бот-пульт Зиныч IT: видит всё, что происходит с клиниками.

Для владельца — меню с разделами (сводка, сообщения, ошибки, предложения, клиенты).
Для остальных — демо бота записи, как у клиники.

    python business/bot.py            # запустить
    python business/bot.py --check    # проверить связь
"""
from __future__ import annotations
import os

import html
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from events import log as ev_log, log_exception, read_events
import sales
import handoff

ROOT = Path(__file__).resolve().parent
TOKEN = os.environ.get("TG_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"
SITE = "https://ufa-zapis.surge.sh"
DEMO = SITE + "/demos/moj-doktor.html"

SPAM_WORDS = [
    "заработ", "крипт", "инвестиц", "казино", "ставк", "подписчик", "раскрут",
    "продвижен", "реклам", "биржа", "займ", "микрозайм", "1xbet", "казин",
    "накрутк", "трафик", "партнерк", "партнёрк", "доход в день", "пассивн",
]

TECH_WORDS = [
    "не работает", "не открывается", "не грузится", "не грузит", "ошибка", "ошибку",
    "сломалось", "сломалось", "белый экран", "не нажимается", "не реагирует",
    "висит", "глючит", "не приходит", "не отправилось", "пустая страница",
]

OWNER = 564920456
SEEN_CALLBACKS: set[str] = set()
PENDING = {"chat": None}   # кому сейчас отвечаем           # твой Telegram — только здесь открывается пульт
PAGE = 6                    # сколько строк на страницу

# ---------------------------------------------------------------- демо для клиники

CLINIC_HELLO = (
    "Бот записи для клиник.\n\n"
    "Пациент выбирает услугу и время — заявка сразу приходит администратору.\n\n"
    "10 000 ₽ · запуск 5–10 дней · Telegram и MAX"
)

HELP_TEXT = (
    "<b>Чем помочь</b>\n\n"
    "Ответьте кнопкой ниже или напишите словами — я передам владельцу."
)

CLINIC_KB = sales.MENU_KB

PRICES = ["Консультация — 500 ₽", "Лечение кариеса — 3 500 ₽", "Профгигиена — 4 000 ₽",
          "Удаление зуба — 2 000 ₽", "Имплантация — от 35 000 ₽"]
ADDRESS, HOURS, PHONE = "Уфа, ул. Аксакова, 80", "Ежедневно 9:00–20:00", "+7 347 257-44-04"


# ---------------------------------------------------------------- Telegram

def call(method: str, params: dict | None = None, timeout: int = 40) -> dict:
    url = f"{API}/{method}"
    data = urllib.parse.urlencode(params, doseq=True).encode() if params else None
    try:
        with urllib.request.urlopen(url, data=data, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        log_exception("telegram", exc)
        return {"ok": False, "error": str(exc)}


def send(chat_id: int, text: str, kb: dict | None = None, html_mode: bool = False) -> None:
    params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    if kb:
        params["reply_markup"] = json.dumps(kb, ensure_ascii=False)
    if html_mode:
        params["parse_mode"] = "HTML"
    res = call("sendMessage", params)
    if not res.get("ok") and html_mode:
        # разметка не понравилась — отправляем как обычный текст
        params.pop("parse_mode", None)
        call("sendMessage", params)


def edit(chat_id: int, message_id: int, text: str, kb: dict | None = None) -> None:
    params = {"chat_id": chat_id, "message_id": message_id, "text": text,
              "disable_web_page_preview": "true", "parse_mode": "HTML"}
    if kb:
        params["reply_markup"] = json.dumps(kb, ensure_ascii=False)
    res = call("editMessageText", params)
    if not res.get("ok"):
        send(chat_id, text, kb, html_mode=True)


def looks_like_spam(text: str) -> bool:
    low = text.lower()
    if any(w in low for w in SPAM_WORDS):
        return True
    links = low.count("http") + low.count("t.me/")
    return links >= 2 and len(low) < 300



PENDING_ERRORS = ROOT / "_pending_errors.json"


def pend_load() -> dict:
    if PENDING_ERRORS.exists():
        try:
            return json.loads(PENDING_ERRORS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def pend_save(data: dict) -> None:
    PENDING_ERRORS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ask_owner_about_error(text: str, chat_id: int, who: str) -> None:
    """Спрашивает владельца: это ошибка или нет. Можно добавить комментарий."""
    data = pend_load()
    eid = str(int(time.time() * 1000))
    data[eid] = {"text": text[:900], "chat": chat_id, "who": who,
                 "created": time.strftime("%Y-%m-%d %H:%M:%S"), "note": "", "status": "wait"}
    pend_save(data)
    kb = {"inline_keyboard": [
        [{"text": "✅ Да, ошибка — исправить", "callback_data": f"err:ok:{eid}"}],
        [{"text": "❌ Нет, всё работает", "callback_data": f"err:no:{eid}"}],
        [{"text": "💬 Добавить комментарий", "callback_data": f"err:note:{eid}"}],
    ]}
    send(OWNER, (f"❓ <b>Жалоба клиента</b>\n\n"
                 f"От: {esc(who)} ({chat_id})\n"
                 f"Время: {data[eid]['created']}\n\n"
                 f"{esc(text[:700])}\n\n"
                 "<i>Это ошибка?</i>"), kb, html_mode=True)

def remember(chat_id: int, who: str) -> None:
    path = ROOT / "_subscribers.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    data[str(chat_id)] = {"name": who, "at": time.strftime("%Y-%m-%d %H:%M")}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- экраны пульта

def esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def main_menu() -> tuple[str, dict]:
    events = read_events(300)
    msgs = [e for e in events if e["kind"] == "message"]
    tech = [e for e in msgs if (e.get("extra") or {}).get("tech")]
    import resolve
    errs = [e for e in events if e["kind"] == "error" and not resolve.is_resolved(e)]
    queue = {}
    qpath = ROOT / "_ops_queue.json"
    if qpath.exists():
        try:
            queue = json.loads(qpath.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            queue = {}
    waiting = [q for q in queue.values() if q.get("status") == "waiting"]

    text = (
        "<b>Пульт Зиныч IT</b>\n\n"
        f"Сообщений от клиник: <b>{len(msgs)}</b>\n"
        f"Из них технических: <b>{len(tech)}</b>\n"
        f"Ошибок: <b>{len(errs)}</b>\n"
        f"Ждут решения: <b>{len(waiting)}</b>\n\n"
        "Выберите раздел:"
    )
    kb = {"inline_keyboard": [
        [{"text": "💬 Сообщения клиентов", "callback_data": "st:messages"}],
        [{"text": "🐞 Ошибки", "callback_data": "st:errors"},
         {"text": "🛠 Предложения", "callback_data": "st:ops"}],
        [{"text": "👥 Клиенты", "callback_data": "st:clients"},
         {"text": "🌐 Сайт и демо", "callback_data": "st:links"}],
        [{"text": "🛠 В работе", "callback_data": "st:fixes"},
         {"text": "🚫 Спам", "callback_data": "st:spam"},
         {"text": "✅ Исправлено", "callback_data": "st:fixed"}],
    ]}
    return text, kb



def clients_index() -> dict:
    """Кто нам писал: chat_id → имя, сколько сообщений, последнее."""
    out: dict = {}
    for e in read_events(500):
        if e["kind"] not in ("message", "spam"):
            continue
        chat = (e.get("extra") or {}).get("chat_id")
        if not chat:
            continue
        item = out.setdefault(str(chat), {
            "who": "", "count": 0, "last": "", "last_ts": "",
            "channel": (e.get("extra") or {}).get("channel", "telegram"), "tech": 0, "apps": 0,
        })
        extra = e.get("extra") or {}
        name = (e.get("who") or "").strip()
        # старое MAX-событие писало числовой id вместо имени — не затираем имя из заявки
        if extra.get("from") != "owner" and name and name != str(chat) and not name.isdigit():
            item["who"] = name
        item["count"] += 1
        text = e.get("text") or ""
        if text.startswith("ЗАЯВКА"):
            item["apps"] += 1
        if (e.get("extra") or {}).get("tech"):
            item["tech"] += 1
        if e["ts"] >= item["last_ts"]:
            item["last_ts"] = e["ts"]
            item["last"] = text
    for chat, item in out.items():
        item["who"] = item["who"] or chat
    return out


def section_clients(page: int) -> tuple[str, dict]:
    clients = clients_index()
    if not clients:
        return ("<b>Клиенты</b>\n\nПока никто не писал.",
                {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
    items = sorted(clients.items(), key=lambda kv: kv[1]["last_ts"], reverse=True)
    total = (len(items) - 1) // PAGE + 1
    page = max(0, min(page, total - 1))
    chunk = items[page * PAGE:(page + 1) * PAGE]

    lines = [f"<b>Клиенты</b> — {len(items)} · стр. {page + 1}/{total}", ""]
    rows = []
    for chat, info in chunk:
        badge = f" · заявок: {info['apps']}" if info["apps"] else ""
        lines.append(f"<b>{esc(info['who'])}</b> · {info['count']} сообщ.{badge}\n"
                     f"{esc(info['last'][:60])}")
        rows.append([{"text": f"👤 {info['who'][:16]} · {info['count']}",
                      "callback_data": f"client:{chat}"}])
    if page > 0:
        rows.append([{"text": "‹ Раньше", "callback_data": f"page:clients:{page - 1}"}])
    if page < total - 1:
        rows.append([{"text": "Позже ›", "callback_data": f"page:clients:{page + 1}"}])
    rows.append([{"text": "← Меню", "callback_data": "menu"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def section_client(chat: str) -> tuple[str, dict]:
    info = clients_index().get(chat, {})
    thread = [e for e in read_events(500)
              if str((e.get("extra") or {}).get("chat_id")) == str(chat)][-10:]
    if not thread:
        return ("<b>Клиент</b>\n\nСообщений не нашлось.",
                {"inline_keyboard": [[{"text": "← Клиенты", "callback_data": "st:clients"}]]})
    lines = [f"<b>{esc(info.get('who', chat))}</b> · {len(thread)} последних", ""]
    for e in thread:
        mark = "🛠 " if (e.get("extra") or {}).get("tech") else ""
        if (e.get("text") or "").startswith("ЗАЯВКА"):
            mark = "🚀 "
        lines.append(f"{mark}<i>{e['ts'][11:16]}</i> {esc((e.get('text') or '')[:180])}")
    kb = {"inline_keyboard": [
        [{"text": "✍️ Ответить", "callback_data": f"reply:{chat}"}],
        [{"text": "← Клиенты", "callback_data": "st:clients"},
         {"text": "← Меню", "callback_data": "menu"}],
    ]}
    return "\n".join(lines), kb


def section_messages(page: int) -> tuple[str, dict]:
    items = [e for e in read_events(500) if e["kind"] == "message"][::-1]
    if not items:
        return ("<b>Сообщения клиентов</b>\n\nПока никто не писал.",
                {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
    total = (len(items) - 1) // PAGE + 1
    page = max(0, min(page, total - 1))
    chunk = items[page * PAGE:(page + 1) * PAGE]
    lines = [f"<b>Сообщения клиентов</b> · стр. {page + 1}/{total}", ""]
    rows = []
    for e in chunk:
        tech = "🛠 " if (e.get("extra") or {}).get("tech") else ""
        lines.append(f"{tech}<b>{esc(e.get('who') or '—')}</b> · {e['ts'][11:16]}\n{esc(e['text'][:160])}")
        chat = (e.get("extra") or {}).get("chat_id")
        if chat:
            rows.append([{"text": f"✍️ Ответить {e.get('who') or ''}", "callback_data": f"reply:{chat}"}])
    if page > 0:
        rows.append([{"text": "‹ Раньше", "callback_data": f"page:messages:{page - 1}"}])
    if page < total - 1:
        rows.append([{"text": "Позже ›", "callback_data": f"page:messages:{page + 1}"}])
    rows.append([{"text": "← Меню", "callback_data": "menu"}])
    return "\n".join(lines), {"inline_keyboard": rows}


def section_errors(page: int) -> tuple[str, dict]:
    import resolve
    items = [e for e in read_events(500) if e["kind"] == "error" and not resolve.is_resolved(e)][::-1]
    if not items:
        return ("<b>Ошибки</b>\n\nАктивных ошибок нет — всё исправлено ✅",
                {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
    text, kb = page_view("Ошибки", items, page, "errors",
                         lambda e: f"{e['ts'][5:16]} · {esc(e.get('source'))}\n{esc(e['text'][:200])}")
    kb["inline_keyboard"].insert(0, [{"text": "✅ Всё исправлено", "callback_data": "fixall"}])
    return text, kb


def section_fixes(page: int) -> tuple[str, dict]:
    import json as _json
    path = ROOT / "_fix_queue.json"
    data = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    new = [(t, v) for t, v in data.items() if v["status"] != "done"][::-1]
    done = [(t, v) for t, v in data.items() if v["status"] == "done"]
    if not new:
        text = ("<b>В работе</b>\n\n"
                f"Открытых задач нет. Исправлено: {len(done)}")
    else:
        lines = [f"<b>В работе</b> — {len(new)} задач", ""]
        for tid, v in new[:PAGE]:
            lines.append(f"• {esc(v.get('summary', ''))}\n  {(v.get('text') or '')[:90]}")
        text = "\n".join(lines)
    kb = {"inline_keyboard": []}
    for tid, v in new[:PAGE]:
        kb["inline_keyboard"].append([
            {"text": f"✅ Готово: {v.get('summary', '')[:18]}", "callback_data": f"fix:{tid}"},
        ])
    kb["inline_keyboard"].append([{"text": "← Меню", "callback_data": "menu"}])
    return text, kb


def section_spam(page: int) -> tuple[str, dict]:
    items = [e for e in read_events(500) if e["kind"] == "spam"][::-1]
    return page_view("Спам", items, page, "spam",
                     lambda e: f"<b>{esc(e.get('who') or '—')}</b> · {e['ts'][11:16]}\n{esc(e['text'][:200])}")


def section_fixed(page: int) -> tuple[str, dict]:
    import resolve
    done = resolve.load()
    if not done:
        return ("<b>Исправлено</b>\n\nПока пусто.",
                {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
    lines = ["<b>Исправлено</b>", ""]
    for k, v in list(done.items())[-12:][::-1]:
        lines.append(f"✅ {esc(v.get('at', ''))} · {esc(k.split('|')[2][:60])}")
    return "\n".join(lines), {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]}


def section_ops(page: int) -> tuple[str, dict]:
    qpath = ROOT / "_ops_queue.json"
    queue = json.loads(qpath.read_text(encoding="utf-8")) if qpath.exists() else {}
    waiting = [(pid, q) for pid, q in queue.items() if q.get("status") == "waiting"][::-1]
    if not waiting:
        text = "<b>Предложения</b>\n\nПока нечего решать — всё разобрано."
    else:
        lines = ["<b>Предложения</b>", ""]
        for pid, q in waiting[:PAGE]:
            a = q["analysis"]
            lines.append(f"• {esc(a.get('summary'))}")
        text = "\n".join(lines)
    kb_rows = []
    for pid, q in waiting[:PAGE]:
        kb_rows.append([
            {"text": f"✅ {q['analysis'].get('summary', '')[:24]}", "callback_data": f"ops:{pid}:apply"},
            {"text": "❌", "callback_data": f"ops:{pid}:reject"},
        ])
    kb_rows.append([{"text": "← Назад", "callback_data": "menu"}])
    return text, {"inline_keyboard": kb_rows}


def section_links() -> tuple[str, dict]:
    text = ("<b>Сайт и демо</b>\n\n"
            f"Сайт: {SITE}\n"
            f"Демо: {DEMO}\n\n"
            "Проверить, что всё открывается: нажмите кнопку ниже.")
    kb = {"inline_keyboard": [
        [{"text": "🔍 Проверить ссылки", "callback_data": "ops:links:apply"}],
        [{"text": "← Назад", "callback_data": "menu"}],
    ]}
    return text, kb


def page_view(title: str, items: list, page: int, key: str, fmt) -> tuple[str, dict]:
    if not items:
        return f"<b>{title}</b>\n\nПока пусто.", {"inline_keyboard": [[{"text": "← Назад", "callback_data": "menu"}]]}
    total = (len(items) - 1) // PAGE + 1
    page = max(0, min(page, total - 1))
    chunk = items[page * PAGE:(page + 1) * PAGE]
    text = f"<b>{title}</b> · стр. {page + 1}/{total}\n\n" + "\n\n".join(fmt(e) for e in chunk)
    nav = []
    if page > 0:
        nav.append({"text": "‹ Раньше", "callback_data": f"page:{key}:{page - 1}"})
    if page < total - 1:
        nav.append({"text": "Позже ›", "callback_data": f"page:{key}:{page + 1}"})
    rows = [nav] if nav else []
    rows.append([{"text": "← Меню", "callback_data": "menu"}])
    return text, {"inline_keyboard": rows}


def screen(name: str, page: int = 0) -> tuple[str, dict]:
    if name == "messages":
        return section_messages(page)
    if name == "errors":
        return section_errors(page)
    if name == "ops":
        return section_ops(page)
    if name == "clients":
        return section_clients(page)
    if name.startswith("client:"):
        return section_client(name.split(":", 1)[1])
    if name == "links":
        return section_links()
    if name == "fixed":
        return section_fixed(page)
    if name == "spam":
        return section_spam(page)
    if name == "fixes":
        return section_fixes(page)
    return main_menu()


# ---------------------------------------------------------------- обработчики

def handle_callback(cb: dict) -> None:
    cb_id = cb["id"]
    msg = cb["message"]
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]
    data = cb.get("data", "")

    # защита от повторной обработки одного нажатия
    cb_uid = str(cb.get("id") or "")
    if cb_uid:
        if cb_uid in SEEN_CALLBACKS:
            call("answerCallbackQuery", {"callback_query_id": cb_id})
            return
        SEEN_CALLBACKS.add(cb_uid)
        if len(SEEN_CALLBACKS) > 800:
            SEEN_CALLBACKS.clear()

    call("answerCallbackQuery", {"callback_query_id": cb_id})

    # бот на паузе — кнопки клиенту не отвечают
    if chat_id != OWNER and handoff.is_muted("tg", chat_id):
        edit(chat_id, message_id,
             "Сейчас с вами общается владелец лично — напишите сообщением.",
             {"inline_keyboard": [[{"text": "← В начало", "callback_data": "sale:menu"}]]})
        return


    # подтверждение жалобы владельцем
    if data.startswith("err:"):
        _, act, eid = data.split(":", 2)
        store = pend_load()
        item = store.get(eid)
        if not item:
            edit(chat_id, message_id, "Жалоба не найдена — возможно, уже обработана.",
                 {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
            return

        if act == "note":
            PENDING["note_for"] = eid
            PENDING["chat"] = None
            send(chat_id, "Напишите комментарий к этой жалобе — он уйдёт разработчику вместе с задачей.")
            return

        if act == "no":
            item["status"] = "not_error"
            pend_save(store)
            import resolve
            # закрываем ИМЕННО то событие, на которое жаловались
            target = None
            for ev in read_events(800):
                if (ev.get("text") or "").strip() == item["text"].strip() and \
                        str((ev.get("extra") or {}).get("chat_id")) == str(item["chat"]):
                    target = ev
            if target:
                resolve.mark_resolved([target], "не ошибка")
            else:
                resolve.mark_resolved([{"ts": item["created"], "source": "telegram",
                                        "text": item["text"]}], "не ошибка")
            reply_to = item.get("channel", "telegram")
            if reply_to == "max":
                handoff.mute("max", item["chat"], 6)
                from maxapi import api as _maxapi
                _maxapi("POST", f"/messages?user_id={item['chat']}",
                        {"text": "Проверили — всё должно работать. Попробуйте ещё раз, "
                                 "а если снова не получится, напишите, что именно нажимали."})
            else:
                send(item["chat"], "Проверили — всё должно работать. Попробуйте ещё раз, "
                                   "а если снова не получится, напишите, что именно нажимали.")
            edit(chat_id, message_id, "❌ Отмечено как «не ошибка». Клиенту написал, что всё в порядке.",
                 {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
            return

        if act == "ok":
            import fix_done
            item["status"] = "error"
            pend_save(store)
            note = (item.get("note") or "").strip()
            fix_done.add(item["text"][:120],
                         note or "разобрать и исправить",
                         item["text"][:300] + (("\n\nКомментарий владельца: " + note) if note else ""))
            if item.get("channel") == "max":
                from maxapi import api as _maxapi
                _maxapi("POST", f"/messages?user_id={item['chat']}",
                        {"text": "Подтвердили — это ошибка. Исправляем, вернусь с ответом."})
            else:
                send(item["chat"], "Подтвердили — это ошибка. Исправляем, вернусь с ответом.")
            edit(chat_id, message_id,
                 "✅ Принято в работу. Задача ушла разработчику." + (f"\nКомментарий: {note}" if note else ""),
                 {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
            return

    # продающие кнопки
    if data.startswith("sale:"):
        action = data.split(":", 1)[1]
        if action == "price":
            send(chat_id, sales.PRICE_TEXT + "\n\n" + sales.WHAT_TEXT, sales.NEXT_KB, html_mode=True)
        elif action == "extras":
            send(chat_id, sales.EXTRAS_TEXT, sales.BACK_KB, html_mode=True)
        elif action == "what":
            send(chat_id, sales.WHAT_TEXT, sales.BACK_KB, html_mode=True)
        elif action == "demo":
            send(chat_id, sales.DEMO_TEXT, sales.MENU_KB)
        elif action == "order":
            sales.set_step(chat_id, {"step": "name"})
            send(chat_id, "Как называется ваша клиника?")
        elif action == "menu":
            sales.clear(chat_id)
            send(chat_id, CLINIC_HELLO, sales.MENU_KB)
        elif action == "bug":
            sales.set_step(chat_id, {"step": "bug"})
            send(chat_id, "Опишите, что не работает — передам разработчику сразу.")
        return

    # демо-клиент
    if data.startswith("cl:"):
        action = data.split(":", 1)[1]
        if action == "prices":
            text = "Цены клиники «Мой доктор»:\n\n" + "\n".join(PRICES)
        elif action == "contacts":
            text = f"📍 {ADDRESS}\n🕒 {HOURS}\n📞 {PHONE}"
        else:
            text = CLINIC_HELLO
        kb = {"inline_keyboard": [[{"text": "🦷 Записаться", "url": DEMO}],
                                  [{"text": "← Меню", "callback_data": "cl:menu"}]]}
        edit(chat_id, message_id, esc(text), kb)
        return

    # бот на паузе — кнопки не отвечают
    if chat_id != OWNER and handoff.is_muted("tg", chat_id):
        edit(chat_id, msg["message_id"],
             "Сейчас отвечает владелец лично — напишите ему сообщением.",
             {"inline_keyboard": [[{"text": "← В начало", "callback_data": "sale:menu"}]]})
        return

    # не владелец нажал старую кнопку — подсказываем
    if chat_id != OWNER:
        edit(chat_id, msg["message_id"],
             "Эта кнопка устарела. Напишите /start — покажу меню заново.",
             {"inline_keyboard": [[{"text": "← В начало", "callback_data": "sale:menu"}]]})
        return

    if data.startswith("ops:"):
        import ops_agent
        parts = data.split(":")
        if parts[1] == "links":
            result = ops_agent.apply_fix("links") if hasattr(ops_agent, "apply_fix") else "—"
        else:
            _, pid, verdict = parts[0], parts[1], parts[2]
            result = ops_agent.apply_fix(pid) if verdict == "apply" else ops_agent.reject(pid)
        edit(chat_id, message_id, f"<b>{esc(result)}</b>",
             {"inline_keyboard": [[{"text": "← Меню", "callback_data": "menu"}]]})
        return

    if data.startswith("page:"):
        _, key, page = data.split(":")
        text, kb = screen(key, int(page))
        edit(chat_id, message_id, text, kb)
        return

    if data.startswith("fix:"):
        import fix_done
        tid = data.split(":", 1)[1]
        data_q = fix_done.load()
        item = data_q.get(tid)
        if item:
            item["status"] = "done"
            item["closed"] = time.strftime("%Y-%m-%d %H:%M:%S")
            item["note"] = "исправлено владельцем"
            fix_done.save(data_q)
        text, kb = main_menu()
        edit(chat_id, message_id, "<b>Отмечено готовым.</b>\n\n" + text, kb)
        return

    if data == "fixall":
        import resolve
        n = resolve.mark_resolved(resolve.active_errors(), "исправлено из бота")
        text, kb = main_menu()
        edit(chat_id, message_id, f"<b>Отмечено исправленными: {n}</b>\n\n" +
             "Эти ошибки больше не показываются в журнале.\n\n" + text, kb)
        return

    if data.startswith("reply:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            channel, target = parts[1], parts[2]
        else:
            channel, target = "tg", parts[1]
        PENDING["chat"] = target
        PENDING["channel"] = channel
        PENDING["started"] = time.time()
        if channel == "max":
            send(chat_id, "Напишите ответ клиенту в MAX — отправлю сразу.")
        elif channel == "email":
            send(chat_id, "Напишите ответ на почту клиенту — отправлю сразу.")
        else:
            send(chat_id, "Напишите ответ клиенту — отправлю сразу.")
        return

    if data.startswith("replymax:"):
        PENDING["chat"] = int(data.split(":")[1])
        PENDING["channel"] = "max"
        send(chat_id, "Напишите ответ клиенту в MAX — отправлю сразу.")
        return
    if data.startswith("reply_legacy:"):
        PENDING["channel"] = "telegram"
        PENDING["chat"] = int(data.split(":")[1])
        send(chat_id, "Напишите ответ клиенту — я отправлю его сразу.")
        return

    if data.startswith("client:"):
        text, kb = section_client(data.split(":", 1)[1])
        edit(chat_id, message_id, text, kb)
        return

    if data.startswith("st:"):
        text, kb = screen(data.split(":", 1)[1])
        edit(chat_id, message_id, text, kb)
        return

    text, kb = main_menu()
    edit(chat_id, message_id, text, kb)


def handle_group_reply(msg: dict) -> bool:
    """Владелец отвечает в группе реплаем на уведомление — уходит клиенту в его канал."""
    reply = msg.get("reply_to_message")
    if not reply:
        return False
    import relay
    target = relay.lookup(reply.get("message_id"))
    if not target:
        return False
    text = (msg.get("text") or "").strip()
    if not text:
        return False
    ok = relay.send_reply(target["channel"], target["chat"], text)
    if ok:
        handoff.mute(target["channel"], target["chat"], 6)
    send(msg["chat"]["id"], "✅ Отправлено клиенту" if ok else "⚠️ Не удалось отправить")
    return True


def handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    if msg.get("chat", {}).get("type") in ("group", "supergroup"):
        text = (msg.get("text") or "").strip().lower()
        if text in ("/здесь", "/here", "/set_here"):
            import relay
            relay.CONFIG.write_text(json.dumps({"chat_id": chat_id}, ensure_ascii=False), encoding="utf-8")
            send(chat_id, "Готово. Сюда будут приходить сообщения клиентов.")
            return
        if handle_group_reply(msg):
            return
        return
    who = msg.get("from", {}).get("first_name", "")
    raw = msg.get("text") or msg.get("caption") or ""
    if not raw:
        raw = "[стикер]" if msg.get("sticker") else "[фото]" if msg.get("photo") else \
              "[голосовое]" if (msg.get("voice") or msg.get("audio")) else "[без текста]"
    text = raw.strip()
    msg_photo = msg.get("photo") or []
    print(f"  сообщение от {who}: {text[:60]}", flush=True)
    remember(chat_id, who)
    # если владелец уже ведёт диалог — бот не вмешивается
    if handoff.is_muted("tg", chat_id):
        ev_log("telegram", "message", text, who,
               {"chat_id": chat_id, "channel": "telegram", "handled_by": "owner"})
        return

    COMPLAINT = (
        "не работает", "не открывается", "не нажимается", "не приходит", "не грузится",
        "не могу", "непонятно", "не понятно", "не так", "неудобно", "ошибк", "сломал",
        "баг", "глючит", "висит", "кнопка не", "кнопки не", "кнопку не",
        "две кнопки", "криво", "не там", "не туда", "не вижу",
    )
    low = text.lower()
    tech = any(w in low for w in TECH_WORDS) or any(k in low for k in COMPLAINT)
    ev_log("telegram", "message", text, who, {"chat_id": chat_id, "tech": tech, "channel": "telegram"})

    # команда отменяет ожидание ответа
    if text.startswith("/") and (PENDING.get("chat") or PENDING.get("note_for")):
        PENDING["chat"] = None
        PENDING["note_for"] = None
        send(OWNER, "Ок, ответ клиенту отменён.")

    if PENDING.get("started") and time.time() - PENDING["started"] > 900:
        PENDING["chat"] = None
        PENDING["note_for"] = None

    if chat_id == OWNER and PENDING.get("note_for"):
        eid = PENDING["note_for"]
        PENDING["note_for"] = None
        store = pend_load()
        if eid in store:
            store[eid]["note"] = text[:500]
            pend_save(store)
            item = store[eid]
            kb = {"inline_keyboard": [
                [{"text": "✅ Да, ошибка — исправить", "callback_data": f"err:ok:{eid}"}],
                [{"text": "❌ Нет, всё работает", "callback_data": f"err:no:{eid}"}],
                [{"text": "💬 Изменить комментарий", "callback_data": f"err:note:{eid}"}],
            ]}
            send(OWNER, f"Комментарий сохранён:\n\n{esc(text[:400])}\n\nТеперь подтвердите:", kb, html_mode=True)
        return

    # владелец отвечает реплаем на карточку клиента в личке
    if chat_id == OWNER and msg.get("reply_to_message"):
        import relay as _r
        target = _r.lookup(msg["reply_to_message"].get("message_id"))
        if target and text and not text.startswith("/"):
            ok = _r.send_reply(target["channel"], target["chat"], text)
            if ok:
                ev_log("max" if target["channel"] == "max" else "telegram", "message", text, "владелец",
                       {"chat_id": target["chat"], "channel": target["channel"], "from": "owner"})
                handoff.mute(target["channel"], target["chat"], 6)
            send(OWNER, "✅ Отправлено клиенту" if ok else "⚠️ Не удалось отправить")
            return

    if chat_id == OWNER and PENDING.get("chat"):
        target = PENDING["chat"]
        channel = PENDING.get("channel", "telegram")
        PENDING["chat"] = None
        PENDING["channel"] = "telegram"
        import relay
        ok = relay.send_reply(channel, target, text)
        if ok:
            ev_log("max" if channel == "max" else "telegram", "message", text, "владелец",
                   {"chat_id": int(target) if str(target).isdigit() else target,
                    "channel": channel, "from": "owner"})
            handoff.mute(channel, target, 6)
            send(OWNER, f"✅ Отправлено клиенту ({target}). Бот замолчит на 6 часов по этому клиенту:\n\n{text[:300]}")
        else:
            send(OWNER, f"⚠️ Не удалось отправить клиенту ({target}). Проверьте канал {channel} и попробуйте снова.")
        return

    if chat_id == OWNER:
        if text.lower().startswith("/start") or text.lower().startswith("/menu"):
            body, kb = main_menu()
            send(chat_id, body, kb, html_mode=True)
            return
        if text.startswith("["):
            send(chat_id, "Это служебное сообщение — записал в раздел «Сообщения».")
            return
        # любое другое сообщение владельца — короткая справка
        send(chat_id, "Пульт открывается командой /menu.\nИли нажмите кнопку ниже.",
             {"inline_keyboard": [[{"text": "🛠 Открыть пульт", "callback_data": "menu"}]]})
        return

    # клиент
    st = sales.step(chat_id)

    if looks_like_spam(text):
        ev_log("telegram", "spam", text, who, {"chat_id": chat_id})
        send(OWNER, f"🚫 <b>Спам от {esc(who)}</b>\n\n{esc(text[:300])}")
        return


    if text.lower().startswith("/start"):
        sales.clear(chat_id)
        if "bug" in text.lower():
            sales.set_step(chat_id, {"step": "bug"})
            send(chat_id, "Опишите, что не работает — сразу передам разработчику.")
        else:
            send(chat_id, CLINIC_HELLO, CLINIC_KB)
        return
    commands = {
        "/help": HELP_TEXT,
        "/price": sales.PRICE_TEXT,
        "/demo": sales.DEMO_TEXT,
        "/what": sales.WHAT_TEXT,
    }
    if text.lower() in commands:
        body = commands[text.lower()]
        send(chat_id, body, sales.BACK_KB, html_mode="<b>" in body)
        return
    if text.lower().startswith("/order"):
        sales.set_step(chat_id, {"step": "name"})
        send(chat_id, "Как называется ваша клиника?")
        return
    if text.lower().startswith("/bug"):
        sales.set_step(chat_id, {"step": "bug"})
        send(chat_id, "Опишите, что не работает — сразу передам разработчику.")
        return
    if text.startswith("/"):
        # любая неизвестная команда — показываем меню, а не «принял»
        sales.clear(chat_id)
        send(chat_id, "Не знаю такую команду. Вот что умею:", sales.MENU_KB)
        return

    if msg_photo:
        send(OWNER, "📷 <b>Скриншот от клиента</b>\n\n"
                    f"От: {esc(who)} ({chat_id})\n{(esc(text) if text and not text.startswith('[') else '')}",
             {"inline_keyboard": [[{"text": "✍️ Ответить", "callback_data": f"reply:{chat_id}"}]]},
             html_mode=True)
        try:
            photo_id = msg_photo[-1]["file_id"]
            call("sendPhoto", {"chat_id": OWNER, "photo": photo_id,
                               "caption": f"Скриншот от {who}"[:200]})
        except Exception:  # noqa: BLE001
            pass
        send(chat_id, "Получил скриншот, спасибо! Передал разработчику — вернусь с ответом.")
        return

    if text.startswith("["):
        send(chat_id, "Пока понимаю только текст — напишите словами, пожалуйста.")
        return

    # оформление заявки
    CANCEL_WORDS = ("отмена", "отменить", "передумал", "стоп")
    if any(w in text.lower() for w in CANCEL_WORDS):
        sales.clear(chat_id)
        send(chat_id, "Хорошо, отменил. Если понадобится — просто напишите.", sales.MENU_KB)
        return

    if st.get("step") and any(k in text.lower() for k in ("не работает", "ошибк", "кнопка не")):
        sales.clear(chat_id)
        ask_owner_about_error(text, chat_id, who)
        send(chat_id, "Спасибо, что написали! Проверяю, что не так — вернусь с ответом.")
        return

    if st.get("step") == "name":
        sales.set_step(chat_id, {"step": "phone", "clinic": text})
        send(chat_id, "Принял. На какой телефон или ник с вами связаться?\n"
                      "(напишите «отмена», если передумали)")
        return
    if st.get("step") == "phone":
        data = {"step": "need", "clinic": st.get("clinic", ""), "phone": text}
        sales.set_step(chat_id, data)
        send(chat_id, "Что нужно: только бот, бот с сайтом, или пока не решили?")
        return
    if st.get("step") == "need":
        app = {"clinic": st.get("clinic", ""), "phone": st.get("phone", ""), "need": text,
               "chat_id": chat_id, "who": who}
        sales.clear(chat_id)
        ev_log("telegram", "message", f"ЗАЯВКА: {app['clinic']} | {app['phone']} | {app['need']}",
               who, {"chat_id": chat_id, "application": app})
        import relay as _relay
        _relay.notify("tg", chat_id, who,
                      f"Заявка: {app['clinic']} | {app['phone']} | {app['need']}",
                      clinic=app["clinic"])
        send(chat_id, "Заявка у меня. Свяжусь с вами в течение дня и покажу демо под вашу клинику.\n\n"
                      "Пока можете посмотреть, как это выглядит:", sales.MENU_KB)
        return

    # сообщение об ошибке
    if st.get("step") == "bug":
        if len(text.strip()) < 5:
            send(chat_id, "Опишите подробнее, пожалуйста: что нажали и что произошло.")
            return
        sales.clear(chat_id)
        ask_owner_about_error(text, chat_id, who)     # та же схема с кнопками
        send(chat_id, "Спасибо, что написали! Проверяю, что не так — вернусь с ответом.")
        return

    # жалоба или ошибка в свободной форме — сразу в поддержку
    import answers
    low = text.lower()
    COMPLAINT = (
        "не работает", "не открывается", "не нажимается", "не приходит", "не грузится",
        "не могу", "непонятно", "не понятно", "не так", "неудобно", "ошибк", "сломал",
        "баг", "глючит", "висит", "кнопка не", "кнопки не", "кнопку не",
        "две кнопки", "криво", "не там", "не туда", "не вижу",
    )
    if any(k in low for k in COMPLAINT) and not text.startswith("/"):
        ask_owner_about_error(text, chat_id, who)
        send(chat_id, "Спасибо, что написали! Проверяю, что не так — вернусь с ответом.")
        return

    # обычный вопрос — пробуем ответить сами
    reply = answers.answer(text)
    if reply:
        send(chat_id, reply, CLINIC_KB)
        ev_log("telegram", "message", f"[ответ бота] {reply[:200]}", who, {"chat_id": chat_id})
    else:
        import relay as _relay
        _relay.notify("tg", chat_id, who, text)
        send(chat_id, "Хороший вопрос — уточню и вернусь с ответом.\n\n"
                      "А пока можно посмотреть, как выглядит запись:", CLINIC_KB)


def main() -> None:
    if "--check" in sys.argv:
        print(json.dumps(call("getMe").get("result"), ensure_ascii=False, indent=2))
        return

    from lock import acquire
    acquire("bot")
    me = call("getMe")["result"]
    print(f"Бот запущен: @{me['username']} ({me['first_name']}). Жду сообщения…", flush=True)

    # помним, на каком сообщении остановились — чтобы не отвечать заново
    offset_file = ROOT / "_run" / "tg_offset.txt"
    offset_file.parent.mkdir(exist_ok=True)
    try:
        offset = int(offset_file.read_text(encoding="utf-8").strip() or 0)
    except Exception:  # noqa: BLE001
        offset = 0

    while True:
        try:
            upd = call("getUpdates", {"timeout": 25, "offset": offset,
                                      "allowed_updates": json.dumps(["message", "callback_query"])})
            for item in upd.get("result", []):
                offset = item["update_id"] + 1
                try:
                    offset_file.write_text(str(offset), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
                if "callback_query" in item:
                    handle_callback(item["callback_query"])
                elif "message" in item:
                    handle_message(item["message"])
        except Exception as exc:  # noqa: BLE001
            log_exception("telegram", exc)
            print("ошибка:", type(exc).__name__, str(exc)[:120], flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
