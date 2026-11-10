"""MAX-бот «Зиныч — запись»: тот же сценарий, что в Telegram.

Меню, цены, заявка из трёх шагов, приём ошибок — всё как в Telegram:
кнопки работают внутри чата (callback), ответы те же, состояние то же.

    python business/bot_max.py
"""
from __future__ import annotations
import os

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from maxapi import api
from events import log as ev_log, log_exception
from commands import for_max
import sales
import answers
import handoff

ROOT = Path(__file__).resolve().parent
SITE = "https://ufa-zapis.surge.sh"
DEMO = SITE + "/demos/moj-doktor.html"
TG_TOKEN = os.environ.get("TG_TOKEN", "")
OWNER_TG = 564920456

HELLO = (
    "Здравствуйте! Это бот Зиныч IT.\n\n"
    "Делаем запись для клиник: клиент выбирает услугу и время, "
    "заявка приходит администратору. Работает в MAX и Telegram.\n\n"
    "Что показать?"
)

SEEN_CALLBACKS: set[str] = set()
MAX_SEEN = 500

# Меню команд — из общего commands.py, чтобы в MAX и Telegram было одинаково коротко.
COMMANDS = for_max()

# те же кнопки, что в Telegram, но в формате MAX
BUTTONS = [
    [{"type": "link", "text": "👀 Посмотреть пример", "url": DEMO}],
    [{"type": "callback", "text": "💰 Цена и что входит", "payload": "sale:price"}],
    [{"type": "callback", "text": "🚀 Оставить заявку", "payload": "sale:order"},
     {"type": "callback", "text": "💬 Вопрос", "payload": "sale:bug"}],
]
BACK_BUTTONS = [[{"type": "callback", "text": "← В начало", "payload": "sale:menu"}]]
NEXT_BUTTONS = [
    [{"type": "callback", "text": "🚀 Оставить заявку", "payload": "sale:order"}],
    [{"type": "link", "text": "👀 Посмотреть пример", "url": "https://ufa-zapis.surge.sh/demos/moj-doktor.html"}],
    [{"type": "callback", "text": "← В начало", "payload": "sale:menu"}],
]


def plain(text: str) -> str:
    """MAX не понимает HTML-теги — убираем их."""
    import re
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</?(b|i|u|s|code|pre)>", "", text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def keyboard(buttons):
    return {"attachments": [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]}


def remember(user_id: int) -> None:
    path = ROOT / "_subscribers_max.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    data[str(user_id)] = time.strftime("%Y-%m-%d %H:%M")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def notify_owner(user_id: int, text: str, who: str = "", clinic: str = "") -> None:
    import relay
    relay.notify("max", user_id, who or str(user_id), text, clinic=clinic)


def ask_owner_about_error(user_id: int, text: str, who: str) -> None:
    """Как в Telegram: спрашиваем владельца, ошибка это или нет."""
    import bot  # переиспользуем хранилище жалоб и клавиатуру
    data = bot.pend_load()
    eid = str(int(time.time() * 1000))
    data[eid] = {"text": text[:900], "chat": user_id, "who": who + " (MAX)",
                 "created": time.strftime("%Y-%m-%d %H:%M:%S"), "note": "",
                 "status": "wait", "channel": "max"}
    bot.pend_save(data)
    kb = {"inline_keyboard": [
        [{"text": "✅ Да, ошибка — исправить", "callback_data": f"err:ok:{eid}"}],
        [{"text": "❌ Нет, всё работает", "callback_data": f"err:no:{eid}"}],
        [{"text": "💬 Добавить комментарий", "callback_data": f"err:note:{eid}"}],
    ]}
    import html as _html
    safe_who = _html.escape(str(who))
    safe_text = _html.escape(text[:700])
    payload = {"chat_id": OWNER_TG, "parse_mode": "HTML", "reply_markup": json.dumps(kb, ensure_ascii=False),
               "text": (f"❓ <b>Жалоба клиента (MAX)</b>\n\nОт: {safe_who}\nВремя: {data[eid]['created']}\n\n"
                        f"{safe_text}\n\n<i>Это ошибка?</i>")}
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                               data=urllib.parse.urlencode(payload).encode(), timeout=20)
    except Exception:  # noqa: BLE001
        pass


def send(user_id: int, text: str, buttons=None) -> None:
    body = {"text": plain(text)}
    if buttons is not None:
        body.update(keyboard(buttons if buttons else BACK_BUTTONS))
    status, res = api("POST", f"/messages?user_id={user_id}", body)
    if status != 200:
        print(f"  ошибка отправки {user_id}: {status} {json.dumps(res, ensure_ascii=False)[:150]}", flush=True)


def edit(message_id: str, text: str, buttons=None) -> bool:
    """Меняет уже отправленное сообщение — как в Telegram."""
    body = {"text": plain(text)}
    if buttons is not None:
        body.update(keyboard(buttons if buttons else BACK_BUTTONS))
    status, res = api("PUT", f"/messages?message_id={message_id}", body)
    if status != 200:
        print(f"  правка не удалась: {status} {str(res)[:120]}", flush=True)
    return status == 200


def delete_message(message_id: str) -> bool:
    """Удаляет сообщение бота. Проверено: после удаления чтение даёт 404."""
    status, res = api("DELETE", f"/messages?message_id={message_id}")
    return status == 200


def set_commands() -> None:
    status, res = api("PATCH", "/me/commands", {"commands": COMMANDS})
    print(f"команды бота: {status}", flush=True)


def answer_callback(callback_id: str, text: str = "Готово", buttons=None) -> bool:
    """Ответ на нажатие: МЕНЯЕТ сообщение с кнопкой (так требует MAX)."""
    if not callback_id:
        return False
    try:
        status, res = api("POST", f"/answers?callback_id={callback_id}", {"notification": text[:60]})
        print(f"  ответ на callback: {status} {str(res)[:80]}", flush=True)
        return status == 200
    except Exception as exc:  # noqa: BLE001
        print("  ответ на callback не ушёл:", exc, flush=True)
        return False


def action_payload(user_id: int, action: str) -> tuple[str, list | None]:
    """Что показать после нажатия кнопки. payload приходит как 'sale:price'."""
    action = (action or "").split(":")[-1].strip()
    if action == "menu":
        sales.clear(user_id)
        return HELLO, BUTTONS
    if action == "price":
        return sales.PRICE_TEXT + "\n\n" + sales.WHAT_TEXT, NEXT_BUTTONS
    if action == "extras":
        return sales.EXTRAS_TEXT, BACK_BUTTONS
    if action == "what":
        return sales.WHAT_TEXT, BACK_BUTTONS
    if action == "order":
        sales.set_step(user_id, {"step": "name"})
        return "Оформляем заявку.\n\nКак называется ваша клиника?", BACK_BUTTONS
    if action == "bug":
        sales.set_step(user_id, {"step": "bug"})
        return "Опишите, что не работает — сразу передам разработчику.", BACK_BUTTONS
    return HELLO, BUTTONS


def handle_text(user_id: int, text: str, who: str) -> None:
    low = text.strip().lower()

    # владелец уже отвечает — бот молчит
    if handoff.is_muted("max", user_id) and not low.startswith("/"):
        ev_log("max", "message", text, who or str(user_id),
               {"chat_id": user_id, "channel": "max", "handled_by": "owner"})
        return
    remember(user_id)
    ev_log("max", "message", text, who or str(user_id),
           {"chat_id": user_id, "channel": "max", "tech": any(k in low for k in
            ("не работает", "ошибк", "кнопк", "неудобн", "непонятн", "сломал"))})

    if low.startswith("/start") or low in ("start", "starts", "начать", "/menu", "привет"):
        sales.clear(user_id)
        send(user_id, HELLO, BUTTONS)
        return
    if low.startswith("/help"):
        send(user_id, "Помощь:\n" + "\n".join(f"/{c['name']} — {c['description']}" for c in COMMANDS),
             BACK_BUTTONS)
        return
    if low.startswith("/price"):
        send(user_id, sales.PRICE_TEXT + "\n\n" + sales.WHAT_TEXT, BACK_BUTTONS)
        return
    if low.startswith("/what"):
        send(user_id, sales.WHAT_TEXT, BACK_BUTTONS)
        return
    if low.startswith("/demo"):
        send(user_id, "Вот как это выглядит для пациента:\n" + DEMO, BACK_BUTTONS)
        return
    if low.startswith("/order"):
        text_out, buttons = action_payload(user_id, "order")
        send(user_id, text_out, buttons)
        return
    if low.startswith("/bug"):
        text_out, buttons = action_payload(user_id, "bug")
        send(user_id, text_out, buttons)
        return

    st = sales.step(user_id)

    CANCEL = ("отмена", "отменить", "передумал", "стоп")
    if st.get("step") and any(w in low for w in CANCEL):
        sales.clear(user_id)
        send(user_id, "Хорошо, отменил. Если понадобится — напишите.", BUTTONS)
        return

    if st.get("step") and any(w in low for w in ("не работает", "ошибк", "кнопка не")):
        sales.clear(user_id)
        ask_owner_about_error(user_id, text, who)
        send(user_id, "Спасибо, что написали! Проверяю, что не так — вернусь с ответом.")
        return

    if st.get("step") == "name":
        sales.set_step(user_id, {"step": "phone", "clinic": text})
        send(user_id, "Принял. На какой телефон или ник с вами связаться?")
        return
    if st.get("step") == "phone":
        sales.set_step(user_id, {"step": "need", "clinic": st.get("clinic", ""), "phone": text})
        send(user_id, "Что нужно: только бот, бот с сайтом, или пока не решили?")
        return
    if st.get("step") == "need":
        app = {"clinic": st.get("clinic", ""), "phone": st.get("phone", ""), "need": text, "chat": user_id}
        sales.clear(user_id)
        ev_log("max", "message", f"ЗАЯВКА: {app['clinic']} | {app['phone']} | {app['need']}", who,
               {"chat_id": user_id, "channel": "max", "application": app})
        notify_owner(user_id, f"Заявка: {app['clinic']} | {app['phone']} | {app['need']}",
                     who, clinic=app["clinic"])
        send(user_id, "Заявка у меня. Свяжусь в течение дня и покажу демо под вашу клинику.", BUTTONS)
        return

    if st.get("step") == "bug":
        if len(text.strip()) < 5:
            send(user_id, "Опишите подробнее, пожалуйста: что нажали и что произошло.")
            return
        sales.clear(user_id)
        ask_owner_about_error(user_id, text, who)
        send(user_id, "Спасибо, что написали! Проверяю, что не так — вернусь с ответом.")
        return

    # жалоба в свободной форме
    if any(k in low for k in ("не работает", "ошибк", "кнопк", "неудобн", "непонятн", "сломал")):
        ask_owner_about_error(user_id, text, who)
        send(user_id, "Спасибо, что написали! Проверяю, что не так — вернусь с ответом.")
        return

    reply = answers.answer(text)
    if reply:
        send(user_id, reply, BUTTONS)
    else:
        notify_owner(user_id, text, who)
        send(user_id, "Спасибо! Передал владельцу — ответит лично.", BUTTONS)


def main() -> None:
    from lock import acquire
    acquire("bot_max")

    status, me = api("GET", "/me")
    if status != 200:
        print("MAX не ответил:", status, me)
        return
    print(f"MAX-бот запущен: {me.get('name')} ({me.get('username')}). Жду сообщения…", flush=True)
    if "--check" in sys.argv:
        return

    set_commands()

    marker = None
    while True:
        try:
            url = "/updates?timeout=20" + (f"&marker={marker}" if marker else "")
            status, res = api("GET", url, timeout=40)
            if status != 200 or not isinstance(res, dict):
                time.sleep(3)
                continue
            marker = res.get("marker", marker)

            for upd in res.get("updates", []):
                kind = upd.get("update_type", "")

                if "callback" in kind:
                    print("  RAW CALLBACK: " + json.dumps(upd, ensure_ascii=False)[:700], flush=True)
                    cb = upd.get("callback") or upd
                    payload = (cb.get("payload") or "").strip()
                    user = ((cb.get("user") or {}).get("user_id")
                            or (upd.get("message") or {}).get("recipient", {}).get("user_id"))
                    who = (cb.get("user") or {}).get("name") or str(user)
                    cb_id_str = str(cb.get("callback_id") or "")
                    if cb_id_str and cb_id_str in SEEN_CALLBACKS:
                        print(f"  повтор нажатия пропущен: {payload}", flush=True)
                        continue
                    if cb_id_str:
                        SEEN_CALLBACKS.add(cb_id_str)
                        if len(SEEN_CALLBACKS) > MAX_SEEN:
                            SEEN_CALLBACKS.clear()
                    print(f"  кнопка {payload} от {user}", flush=True)
                    if not user:
                        continue
                    if handoff.is_muted("max", int(user)):
                        answer_callback(str(cb.get("callback_id") or ""), "Владелец ответит лично")
                        continue
                    text, buttons = action_payload(int(user), payload)
                    answer_callback(str(cb.get("callback_id") or ""), "Открываю")
                    cb_mid = ((upd.get("message") or {}).get("body") or {}).get("mid")
                    if cb_mid and edit(cb_mid, text, buttons):
                        pass                            # сообщение меняется на месте, без мигания
                    else:
                        send(int(user), text, buttons)
                    continue

                msg = upd.get("message") or {}
                sender = (msg.get("sender") or {})
                user_id = sender.get("user_id") or (msg.get("recipient") or {}).get("user_id")
                who = sender.get("name") or str(user_id)
                text = ((msg.get("body") or {}).get("text") or "").strip()
                if not user_id:
                    continue
                print(f"  сообщение от {user_id}: {text[:60]}", flush=True)
                if text:
                    handle_text(int(user_id), text, who)
                else:
                    send(int(user_id), "Пока понимаю только текст — напишите словами, пожалуйста.")
        except Exception as exc:  # noqa: BLE001
            log_exception("max", exc)
            print("ошибка:", type(exc).__name__, str(exc)[:120], flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
