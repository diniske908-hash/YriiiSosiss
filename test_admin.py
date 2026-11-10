"""Полный функциональный тест админки (API + инварианты)."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "_events.jsonl"

passed = failed = 0


def ok(name: str, cond: bool, info: object = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"OK   {name}" + (f"  → {info}" if info != "" else ""))
    else:
        failed += 1
        print(f"FAIL {name}" + (f"  → {info}" if info != "" else ""))


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path: str, data: dict):
    req = urllib.request.Request(BASE + path, data=json.dumps(data, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def add_event(channel: str, chat: int, who: str, text: str) -> None:
    ev = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "source": channel, "kind": "message",
          "who": who, "text": text, "extra": {"chat_id": chat, "channel": channel}}
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def test_clients():
    cl = get("/api/clients")
    ok("диалоги отдаются", isinstance(cl, list) and len(cl) > 0, len(cl))
    keys = [c["key"] for c in cl]
    ok("ключи не дублируются", len(keys) == len(set(keys)))
    ok("у каждого есть chat/key/status", all(c.get("chat") and c.get("key") and c.get("status") for c in cl))
    merged = [c for c in cl if c.get("merged")]
    ok("объединённый клиент есть", bool(merged), [(c["who"], c["channels"]) for c in merged])
    if merged:
        m = merged[0]
        ok("у объединённого 2+ канала", len(m["channels"]) >= 2, m["channels"])
        ok("ключи объединённого 2+", len(m["keys"]) >= 2, len(m["keys"]))
    waiting = [c for c in cl if not c.get("archived") and c["status"] == "waiting"]
    ok("ожидающие отсортированы по времени", waiting == sorted(waiting, key=lambda x: x["last_ts"]))
    ok("wait_min не отрицательный", all(c["wait_min"] >= 0 for c in cl))


def test_thread():
    cl = get("/api/clients")
    merged = next((c for c in cl if c.get("merged")), None)
    if not merged:
        ok("есть объединённый для проверки переписки", False)
        return
    t = get(f"/api/client/{merged['chat']}")
    ok("переписка объединённого не пустая", len(t["messages"]) > 0, len(t["messages"]))
    ok("в переписке 2+ цели", len(t["targets"]) >= 2, [(x["channel"], x["chat"]) for x in t["targets"]])
    ok("у сообщений есть канал", all("channel" in m for m in t["messages"]))
    ok("каналы совпадают", {x["channel"] for x in t["targets"]} == set(t["channels"]))
    ok("total = messages", t["total"] >= len(t["messages"]))


def test_crm():
    cl = get("/api/clients")
    keys = {c["key"] for c in cl}
    crm = get("/api/crm")
    ok("6 стадий сделок", len(crm["stages"]) == 6, [s["name"] for s in crm["stages"]])
    bad = [d["key"] for d in crm["deals"] if d["key"] not in keys]
    ok("сделки привязаны к диалогам", not bad, bad)
    bad_t = [t["key"] for t in crm["tasks"] if t["key"] not in keys]
    ok("дела привязаны к диалогам", not bad_t, bad_t)
    ok("у сделок есть этап", all(d.get("stage") in {s["id"] for s in crm["stages"]} for d in crm["deals"]))


def test_cold():
    d = get("/api/cold")
    leads = d["leads"]
    ok("холодные лиды есть", len(leads) >= 40, len(leads))
    phones = [l.get("phone_digits") for l in leads if l.get("phone_digits")]
    ok("телефоны 10–11 цифр", all(len(p) in (10, 11) for p in phones))
    ok("нет дублей телефонов", len(phones) == len(set(phones)), len(phones) - len(set(phones)))
    ok("статусы известные", all(l.get("status") in {"new", "contacted", "replied", "refused"} for l in leads))
    r2 = [l for l in leads if l.get("rating_2gis")]
    ry = [l for l in leads if l.get("rating_yandex")]
    ok("рейтинги 2ГИС заполнены", len(r2) >= 25, len(r2))
    ok("рейтинги Яндекс заполнены", len(ry) >= 20, len(ry))
    ok("рейтинги в диапазоне 0–5", all(0 <= float(l["rating_2gis"]) <= 5 for l in r2)
       and all(0 <= float(l["rating_yandex"]) <= 5 for l in ry))
    for l in leads[:10]:
        if l.get("phone") and l.get("phone_digits"):
            first = re.split(r"[;,/]", l["phone"])[0]
            d1 = re.sub(r"\D", "", first)
            if len(d1) == 11 and d1.startswith("8"):
                d1 = "7" + d1[1:]
            elif len(d1) == 10:
                d1 = "7" + d1
            ok(f"телефон = первый из списка: {l['name'][:18]}", d1 == l["phone_digits"], first)
            break


def test_errors():
    e = get("/api/errors")
    texts = [(x.get("text") or "")[:200] for x in e]
    ok("проблемы без дублей", len(texts) == len(set(texts)), len(e))
    ok("проблем немного", len(e) <= 10, len(e))


def test_sections_archive():
    sec = get("/api/sections")
    ok("разделы отдаются", "sections" in sec and "map" in sec)
    cl = get("/api/clients")
    keys = {c["key"] for c in cl}
    ok("привязки разделов валидны", set(sec["map"]) <= keys | {""})


def test_archive_auto_return():
    chat = 889101
    add_event("telegram", chat, "Архив Тест", "до архива")
    post("/api/archive", {"key": f"telegram:{chat}", "archived": True})
    cl = {c["chat"]: c for c in get("/api/clients")}
    ok("архив скрывает диалог", cl.get(str(chat), {}).get("archived") is True)
    time.sleep(1.2)
    add_event("telegram", chat, "Архив Тест", "новое сообщение после архива")
    cl = {c["chat"]: c for c in get("/api/clients")}
    ok("новое сообщение возвращает из архива", cl.get(str(chat), {}).get("archived") is False)
    post("/api/chat/delete", {"chats": [str(chat)]})
    ok("тестовый диалог удалён", str(chat) not in {c["chat"] for c in get("/api/clients")})


def test_merge_cycle():
    ca, cb = 889201, 889202
    add_event("telegram", ca, "Merge QA", "тг")
    add_event("max", cb, "Merge QA", "макс")
    res = post("/api/merge", {"keys": [f"telegram:{ca}", f"max:{cb}"]})
    ok("объединение создаёт контакт", bool(res.get("merge")), res.get("merge", {}).get("primary"))
    cl = {c["chat"]: c for c in get("/api/clients")}
    m = cl.get(str(ca))
    ok("один контакт на два канала", bool(m and m["merged"] and len(m["channels"]) == 2))
    t = get(f"/api/client/{ca}")
    ok("в переписке оба сообщения", len(t["messages"]) == 2, len(t["messages"]))
    post("/api/chat/delete", {"chats": [str(ca)]})
    ok("удаление чистит оба канала", str(ca) not in {c["chat"] for c in get("/api/clients")})


def test_html():
    html = urllib.request.urlopen(BASE + "/", timeout=20).read().decode("utf-8")
    for needle in ("Выбрать несколько", "selMerge", "replyChan", "Холодные лиды", "Найти ещё"):
        ok(f"в интерфейсе есть {needle}", needle in html)
    ok("нет внешних script", '<script src="http' not in html)


def main() -> None:
    global passed, failed
    for fn in (test_clients, test_thread, test_crm, test_cold, test_errors,
               test_sections_archive, test_archive_auto_return, test_merge_cycle, test_html):
        print(f"\n— {fn.__name__} —")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__} упал: {type(exc).__name__}: {exc}")
    print(f"\nИтого: {passed}/{passed + failed} проверок пройдено")
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
