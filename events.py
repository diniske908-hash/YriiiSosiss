"""Сбор событий от ботов: сообщения клиентов и ошибки.

Пишет в business/_events.jsonl по одному событию на строку:
    {"ts": "...", "source": "telegram", "kind": "message"|"error", "text": "...", "who": "..."}
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "_events.jsonl"


def log(source: str, kind: str, text: str, who: str = "", extra: dict | None = None) -> None:
    event = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "kind": kind,
        "who": who,
        "text": (text or "")[:1000],
    }
    if extra:
        event["extra"] = extra
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_exception(source: str, exc: Exception, who: str = "") -> None:
    log(source, "error", f"{type(exc).__name__}: {exc}", who,
        {"trace": traceback.format_exc()[-1500:]})


def read_events(limit: int = 500) -> list[dict]:
    if not EVENTS.exists():
        return []
    lines = EVENTS.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
