"""Учёт исправленных ошибок: помечаем и убираем из активного журнала.

    python business/resolve.py            # показать активные и исправленные
    python business/resolve.py --all      # отметить все текущие как исправленные
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESOLVED = ROOT / "_resolved.json"


def key(event: dict) -> str:
    return f"{event.get('ts')}|{event.get('source')}|{(event.get('text') or '')[:80]}"


def load() -> dict:
    if RESOLVED.exists():
        try:
            return json.loads(RESOLVED.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save(data: dict) -> None:
    RESOLVED.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_resolved(events: list[dict], note: str = "") -> int:
    data = load()
    n = 0
    for e in events:
        k = key(e)
        if k in data:
            continue
        data[k] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note}
        n += 1
    save(data)
    return n


def is_resolved(event: dict) -> bool:
    return key(event) in load()


def active_errors() -> list[dict]:
    from events import read_events

    return [e for e in read_events(500) if e["kind"] == "error" and not is_resolved(e)]


def main() -> None:
    from events import read_events

    errors = [e for e in read_events(500) if e["kind"] == "error"]
    active = [e for e in errors if not is_resolved(e)]

    if "--all" in sys.argv:
        n = mark_resolved(active, "исправлено вручную")
        print(f"отмечено исправленными: {n}")
        return

    print(f"всего ошибок: {len(errors)} | исправлено: {len(errors) - len(active)} | активных: {len(active)}")
    for e in active[-8:]:
        print(f"  {e['ts']} · {e['source']} · {(e['text'] or '')[:70]}")


if __name__ == "__main__":
    main()
