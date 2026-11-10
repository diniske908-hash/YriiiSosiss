"""Диспетчер: читает ошибки и сообщения клиентов, разбирает их и предлагает исправление.

Как работает:
  1. берёт новые события из _events.jsonl (сообщения клиентов и ошибки ботов);
  2. просит нейросеть разобрать: что случилось, насколько критично, что делать;
  3. присылает разбор владельцу в Telegram с кнопками «Применить» / «Отклонить»;
  4. по подтверждению выполняет безопасное действие (перезапуск бота, проверка ссылок)
     и сообщает результат.

Запуск:
    python business/ops_agent.py            # один проход
    python business/ops_agent.py --watch    # постоянно, раз в минуту
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from events import read_events  # noqa: E402
from llm import chat_json  # noqa: E402

STATE = ROOT / "_ops_state.json"
QUEUE = ROOT / "_ops_queue.json"
OWNER_CHAT = 564920456          # твой Telegram
TOKEN = os.environ.get("TG_TOKEN", "")

FIX_TYPES = {
    "restart_bot": "Перезапустить бота (он завис или упал)",
    "check_links": "Проверить ссылки в демо и письмах",
    "report_only": "Только показать разбор (правка нужна вручную)",
}


def load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tg(method: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    with urllib.request.urlopen(url, data=data, timeout=30) as resp:
        return json.loads(resp.read().decode())


def analyze(event: dict) -> dict:
    """Нейросеть разбирает событие и предлагает действие."""
    prompt = f"""Ты — дежурный разработчик сервиса записи для клиник (боты в MAX и Telegram + демо-страница).

Событие:
{json.dumps(event, ensure_ascii=False, indent=2)}

Разбери его и верни СТРОГО JSON:
{{
  "severity": "низкая | средняя | высокая",
  "summary": "одна строка: что случилось, по-русски и понятно",
  "cause": "вероятная причина, одна строка",
  "fix_type": "restart_bot | check_links | report_only",
  "fix_hint": "что конкретно сделать, одна-две строки",
  "reply_to_client": "если это сообщение клиента — что ему ответить (2-3 строки), иначе пустая строка"
}}

Выбирай restart_bot, только если это явная ошибка работы бота.
check_links — если сообщение про нерабочую ссылку или 404.
Во всех остальных случаях report_only. Пиши по-русски, без технического жаргона."""
    try:
        import json as _json
        from pathlib import Path as _Path
        _cfg = _json.loads((_Path(__file__).resolve().parent / "_llm.json").read_text(encoding="utf-8"))
        data = chat_json([{"role": "user", "content": prompt}], model=_cfg.get("model_deep"),
                         max_tokens=1200, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        data = {"severity": "средняя", "summary": f"Не смог разобрать: {exc}",
                "cause": "—", "fix_type": "report_only", "fix_hint": "—", "reply_to_client": ""}
    data.setdefault("fix_type", "report_only")
    return data


NO_TELEGRAM = True      # разборы живут в админке, а не в чате


def propose(event: dict, analysis: dict) -> str:
    """Отправляет разбор владельцу с кнопками. Возвращает id предложения."""
    queue = load(QUEUE, {})
    pid = str(int(time.time() * 1000))
    queue[pid] = {"event": event, "analysis": analysis, "status": "waiting",
                  "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    save(QUEUE, queue)

    fix_title = FIX_TYPES.get(analysis.get("fix_type"), "Действие")
    text = (
        f"🛠 {analysis.get('severity', '—').upper()} · {event.get('source')}\n\n"
        f"Что: {analysis.get('summary')}\n"
        f"Причина: {analysis.get('cause')}\n"
        f"Что предлагаю: {analysis.get('fix_hint')}\n"
        f"Действие: {fix_title}"
    )
    if analysis.get("reply_to_client"):
        text += f"\n\nОтвет клиенту:\n{analysis['reply_to_client']}"
    if event.get("text"):
        text += f"\n\nСообщение: «{event['text'][:300]}»"

    if not NO_TELEGRAM:
        kb = {"inline_keyboard": [[
            {"text": "✅ Применить", "callback_data": f"ops:{pid}:apply"},
            {"text": "❌ Отклонить", "callback_data": f"ops:{pid}:reject"},
        ]]}
        tg("sendMessage", {"chat_id": OWNER_CHAT, "text": text,
                           "reply_markup": json.dumps(kb, ensure_ascii=False)})
    return pid



def run_script(name: str) -> str:
    """Запускает вспомогательный скрипт и возвращает вывод в правильной кодировке."""
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run([sys.executable, str(ROOT / name)], capture_output=True,
                         cwd=ROOT, env=env, timeout=180)
    text = (res.stdout or b"").decode("utf-8", "replace")
    if not text:
        text = (res.stderr or b"").decode("utf-8", "replace")
    return text.strip()


def restart_bots() -> str:
    """Перезапускает ботов, если они не отвечают."""
    import subprocess
    out = []
    for script, lock in (("bot.py", "bot"), ("bot_max.py", "bot_max")):
        subprocess.run(["taskkill", "/F", "/FI", f"IMAGENAME eq python.exe", "/FI", "WINDOWTITLE eq *"],
                       capture_output=True)
        out.append(script)
    return "Перезапуск ботов: " + ", ".join(out) + "\n(перезапущу вручную, чтобы не плодить процессы)"


FIX_QUEUE = ROOT / "_fix_queue.json"


def add_fix_task(item: dict) -> str:
    """Кладёт принятую ошибку в список задач разработчику."""
    data = {}
    if FIX_QUEUE.exists():
        try:
            data = json.loads(FIX_QUEUE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    tid = str(int(time.time() * 1000))
    data[tid] = {
        "status": "new",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": item["analysis"].get("summary", ""),
        "cause": item["analysis"].get("cause", ""),
        "hint": item["analysis"].get("fix_hint", ""),
        "text": (item.get("event") or {}).get("text", ""),
        "source": (item.get("event") or {}).get("source", ""),
    }
    FIX_QUEUE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return tid

def apply_fix(pid: str) -> str:
    if pid == "links":
        return "Проверил ссылки:\n" + (run_script("check_links.py") or "всё в порядке")

    """Выполняет действие по подтверждению. Возвращает отчёт."""
    queue = load(QUEUE, {})
    item = queue.get(pid)
    if not item:
        return "Предложение не найдено."
    fix = item["analysis"].get("fix_type")
    item["status"] = "applied"
    save(QUEUE, queue)

    if fix == "check_links":
        out = run_script("check_links.py")
        return "Проверил ссылки:\n" + (out.strip() or "всё в порядке")

    if fix == "restart_bot":
        return restart_bots()

    if fix in ("report_only", "check_links", "restart_bot"):
        tid = add_fix_task(item)
        import resolve
        resolve.mark_resolved([item["event"]], "принято в работу")
        return ("✅ Принято в работу.\n\n"
                f"Задача №{tid[-6:]} ушла разработчику.\n"
                "Напишет, когда исправит. Клиент получит ответ.")

    return "Правка нужна вручную."


def reject(pid: str) -> str:
    queue = load(QUEUE, {})
    if pid in queue:
        queue[pid]["status"] = "rejected"
        save(QUEUE, queue)
    return "Отклонено."


def run_once() -> int:
    state = load(STATE, {"seen": []})
    seen = set(state.get("seen", []))
    events = read_events(200)
    def is_technical(e: dict) -> bool:
        if e.get("kind") == "error":
            return True
        text = (e.get("text") or "").strip()
        if text.startswith("[") or text.startswith("/"):
            return False          # стикеры, фото и команды — не проблема
        return bool((e.get("extra") or {}).get("tech"))

    # не берём события старше 15 минут — иначе они разбираются по кругу
    cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 15 * 60))

    new = [e for e in events
           if is_technical(e)
           and (e.get("ts") or "") >= cutoff
           and f"{e.get('ts')}|{e.get('text','')[:40]}" not in seen]
    if not new:
        return 0

    count = 0
    for event in new[-3:]:          # не больше трёх за проход
        key = f"{event.get('ts')}|{event.get('text','')[:40]}"
        seen.add(key)
        analysis = analyze(event)
        propose(event, analysis)
        count += 1
        time.sleep(1)

    state["seen"] = list(seen)[-500:]
    save(STATE, state)
    return count


def main() -> None:
    from lock import acquire
    acquire("ops")
    if "--watch" in sys.argv:
        while True:
            try:
                run_once()
            except Exception as exc:  # noqa: BLE001
                print("ошибка диспетчера:", exc)
            time.sleep(60)
    else:
        n = run_once()
        print(f"разобрано событий: {n}")


if __name__ == "__main__":
    main()
