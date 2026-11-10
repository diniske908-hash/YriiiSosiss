"""Тест бота-пульта: прогоняем все разделы и кнопки без реальных сообщений.

    python business/test_bot.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import events as _events
_events.log = lambda *a, **k: None
_events.log_exception = lambda *a, **k: None
import bot  # noqa: E402
import answers  # noqa: E402

sent: list[dict] = []
edited: list[dict] = []


def fake_send(chat_id, text, kb=None, html_mode=False):
    sent.append({"chat": chat_id, "text": text, "kb": kb})


def fake_edit(chat_id, message_id, text, kb=None):
    edited.append({"chat": chat_id, "mid": message_id, "text": text, "kb": kb})


def fake_call(method, params=None, timeout=30):
    if method == "answerCallbackQuery":
        return {"ok": True}
    return {"ok": True, "result": {"message_id": 1}}


bot.ev_log = lambda *a, **k: None
import fix_done as _fd
CREATED = []
def _spy_add(*a, **k):
    CREATED.append((a, k))
    return "test"
_fd.add = _spy_add                     # тесты не создают боевых задач, но видят вызов
import tempfile
import pathlib
_tmp = pathlib.Path(tempfile.mkdtemp()) / "pending.json"
bot.PENDING_ERRORS = _tmp          # жалобы пишем во временный файл
bot.ev_log = lambda *a, **k: None
relay_hits = []
import relay as _relay_global
_relay_global.notify = lambda *a, **k: relay_hits.append((a, k))
bot.send = fake_send
bot.edit = fake_edit
bot.call = fake_call

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond), extra))
    print(("OK   " if cond else "FAIL ") + name + (f"  → {extra}" if extra else ""))


_cb_counter = [0]

def cb(data: str, chat: int = bot.OWNER) -> None:
    sent.clear(); edited.clear()
    _cb_counter[0] += 1
    bot.handle_callback({
        "id": f"cb{_cb_counter[0]}",
        "data": data,
        "message": {"chat": {"id": chat}, "message_id": 42},
    })


def msg(text: str, chat: int = bot.OWNER, kind: str = "text") -> None:
    sent.clear(); edited.clear()
    m = {"chat": {"id": chat}, "from": {"first_name": "Тест"}}
    if kind == "text":
        m["text"] = text
    elif kind == "sticker":
        m["sticker"] = {"file_id": "x"}
    elif kind == "photo":
        m["photo"] = [{"file_id": "x"}]
    else:
        m["voice"] = {"file_id": "x"}
    bot.handle_message(m)


def main() -> None:
    import sales
    sales.clear(999999); sales.clear(bot.OWNER)
    # 1. меню
    text, kb = bot.main_menu()
    check("меню: текст собирается", "Пульт Зиныч IT" in text)
    check("меню: разделы на месте", len(kb["inline_keyboard"]) >= 4,
          str(len(kb["inline_keyboard"])) + " ряда")

    # 2. все разделы
    for name in ("messages", "errors", "ops", "clients", "links"):
        try:
            t, k = bot.screen(name)
            check(f"раздел {name}: открывается", bool(t) and "inline_keyboard" in k)
        except Exception as exc:  # noqa: BLE001
            check(f"раздел {name}: открывается", False, str(exc))

    # 3. пагинация
    try:
        t, k = bot.screen("messages", 0)
        check("пагинация: первая страница", "стр." in t or "Пока пусто" in t)
        t, k = bot.screen("messages", 999)
        check("пагинация: несуществующая страница не ломает", bool(t))
    except Exception as exc:  # noqa: BLE001
        check("пагинация", False, str(exc))

    # 4. кнопки-разделы
    for data in ("menu", "st:messages", "st:errors", "st:ops", "st:clients", "st:links",
                 "page:messages:1", "page:errors:999"):
        try:
            cb(data)
            check(f"кнопка {data}", len(sent) + len(edited) >= 1)
        except Exception as exc:  # noqa: BLE001
            check(f"кнопка {data}", False, str(exc))

    # 5. кнопки клиента
    for data in ("cl:prices", "cl:contacts", "cl:menu"):
        try:
            cb(data, chat=999999)
            check(f"клиентская кнопка {data}", len(sent) + len(edited) == 1)
        except Exception as exc:  # noqa: BLE001
            check(f"клиентская кнопка {data}", False, str(exc))

    # 6. чужие не пролезают в пульт
    sent.clear(); edited.clear()
    cb("st:ops", chat=999999)
    check("посторонний не получает пульт",
          not any("Ошибки" in (x.get("text") or "") for x in sent + edited))

    # 7. проверка ссылок по кнопке
    cb("ops:links:apply")
    check("кнопка «проверить ссылки» отвечает", any("ссылк" in (s.get("text") or "") for s in sent + edited),
          (sent + edited)[0]["text"][:60] if (sent or edited) else "нет ответа")

    # 8. сообщения
    msg("/menu")
    check("владелец: /menu открывает пульт", len(sent) == 1 and "Пульт" in sent[0]["text"])

    answers.answer = lambda q: "Бот записи — 10 000 ₽, запуск 5–10 дней."
    msg("сколько стоит бот", chat=999999)
    check("клиент: на вопрос отвечает сам",
          any("10 000" in ((x.get("text") or "") if isinstance(x, dict) else "") for x in sent))

    answers.answer = lambda q: None
    relay_hits.clear()
    msg("хочу обсудить договор", chat=999999)
    check("сложный вопрос → владельцу", len(relay_hits) >= 1, str(len(relay_hits)))
    check("клиенту обещали вернуться", any("уточню" in (x.get("text") or "") for x in sent))

    answers.answer = lambda q: "ok"
    msg("реклама заработок крипта", chat=999999)
    check("спам не получает ответа",
          all("10 000" not in (x.get("text") or "") for x in sent))

    msg("/start", chat=999999)
    check("клиент: /start → приветствие про сервис",
          len(sent) == 1 and ("бот записи" in sent[0]["text"].lower()
                              or "Зиныч IT" in sent[0]["text"]))

    msg("", chat=999999, kind="sticker")
    check("клиент: стикер → просьба написать текстом",
          len(sent) == 1 and "только текст" in sent[0]["text"])

    msg("", chat=999999, kind="photo")
    check("клиент: скриншот уходит владельцу",
          any(x["chat"] == bot.OWNER and "Скриншот" in (x.get("text") or "") for x in sent))
    check("клиент: скриншот принят с ответом",
          any("Получил скриншот" in (x.get("text") or "") for x in sent))

    msg("", chat=999999, kind="voice")
    check("клиент: голосовое → просьба написать текстом",
          len(sent) == 1 and "только текст" in sent[0]["text"])


    # 10. продающий сценарий
    cb("sale:price", chat=999999)
    check("прайс показывается", any("10 000" in (x.get("text") or "") for x in sent + edited))

    cb("sale:what", chat=999999)
    check("что входит показывается", any("Что входит" in (x.get("text") or "") for x in sent + edited))

    cb("sale:order", chat=999999)
    check("заявка: спросили название клиники", any("называется ваша клиника" in (x.get("text") or "") for x in sent + edited))

    msg("Клиника Тест", chat=999999)
    check("заявка: спросили телефон", any("телефон" in (x.get("text") or "") for x in sent))

    msg("+7 999 111-22-33", chat=999999)
    check("заявка: спросили что нужно", any("Что нужно" in (x.get("text") or "") for x in sent))

    relay_hits.clear()
    msg("бот с сайтом", chat=999999)
    check("заявка дошла до владельца", len(relay_hits) >= 1, str(len(relay_hits)))
    check("клиенту подтвердили", any("Заявка у меня" in (x.get("text") or "") for x in sent))

    cb("sale:bug", chat=999999)
    check("ошибка: попросили описать", any("Опишите" in (x.get("text") or "") for x in sent + edited))

    msg("не работает кнопка записаться", chat=999999)
    check("сообщение об ошибке дошло до владельца",
          any(x["chat"] == bot.OWNER and ("Жалоба клиента" in (x.get("text") or "")
                                          or "Сообщение об ошибке" in (x.get("text") or "")) for x in sent))


    # 18. каждая команда и кнопка отвечают клиенту
    answers.answer = lambda q: "Ответ по существу."
    for cmd in ("/start", "/help", "/price", "/demo", "/what", "/order", "/bug", "/slots", "/foo"):
        msg(cmd, chat=999999)
        check(f"команда {cmd} отвечает", len(sent) >= 1, str(len(sent)))

    for cbdata in ("sale:price", "sale:what", "sale:demo", "sale:order", "sale:bug",
                   "cl:prices", "cl:contacts", "cl:menu"):
        cb(cbdata, chat=999999)
        check(f"кнопка {cbdata} отвечает", len(sent) + len(edited) >= 1)


    # 18б. меню команд («☰» слева в Telegram) — короткое и каждый пункт живой
    import setup_bot as _setup
    cmds = [c["command"] for c in _setup.COMMANDS]
    check("меню команд: не больше 5 пунктов", len(cmds) <= 5, str(len(cmds)))
    check("меню команд: без дублей", len(cmds) == len(set(cmds)), ",".join(cmds))
    check("меню команд: описания не пустые",
          all(c.get("description", "").strip() for c in _setup.COMMANDS))
    for cmd in cmds:
        msg("/" + cmd, chat=999999)
        check(f"пункт меню /{cmd} отвечает", len(sent) >= 1)
    # клиентское кнопочное меню — те же 4 кнопки, что и в коде
    _kb = bot.CLINIC_KB["inline_keyboard"]
    check("клиентское меню: 4 кнопки",
          sum(len(r) for r in _kb) == 4,
          f"{sum(len(r) for r in _kb)} кнопок / {len(_kb)} ряда")


    # 19. админка по клиентам
    text, kb = bot.section_clients(0)
    check("раздел клиентов открывается", "Клиенты" in text)
    rows = kb["inline_keyboard"]
    check("на клиента есть своя кнопка", any("👤" in b["text"] for row in rows for b in row), str(len(rows)))


    # 20. жалоба → подтверждение владельцем → задача
    import bot as _bot
    import sales as _sales
    _sales.clear(999999)
    _bot.PENDING_ERRORS.write_text("{}", encoding="utf-8")
    _bot.pend_save({})
    answers.answer = lambda q: "ок"
    msg("кнопки в меню неудобные, непонятно как ориентироваться", chat=999999)
    check("жалоба ушла владельцу на подтверждение",
          any(x["chat"] == _bot.OWNER and "Жалоба клиента" in (x.get("text") or "") for x in sent))
    store = _bot.pend_load()
    check("жалоба сохранена с кнопками", len(store) == 1, str(len(store)))
    eid = list(store.keys())[0]

    cb(f"err:note:{eid}", chat=_bot.OWNER)
    check("попросили комментарий", any("комментарий" in (x.get("text") or "").lower() for x in sent))
    msg("это правда неудобно, поправь меню", chat=_bot.OWNER)
    check("комментарий сохранён", _bot.pend_load()[eid]["note"] != "")

    sent.clear()
    cb(f"err:ok:{eid}", chat=_bot.OWNER)
    check("подтвердили ошибку", any("Принято в работу" in (x.get("text") or "") for x in sent + edited))
    check("задача создана", len(CREATED) >= 1, str(len(CREATED)))
    check("комментарий ушёл в задачу",
          any("поправь меню" in str(args) for args, kw in CREATED))

    # 9. экранирование HTML
    check("html-экранирование работает",
          bot.esc("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;", bot.esc("<b>&</b>"))

    failed = [r for r in results if not r[1]]
    print(f"\nИтого: {len(results) - len(failed)}/{len(results)} проверок пройдено")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
