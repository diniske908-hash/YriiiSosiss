"""Клиент нейросети (OpenAI-совместимый API Easy GonkaAI).

Ключ и адрес лежат в business/_llm.json. Ключ можно переопределить
переменной окружения LLM_API_KEY.

    from llm import chat, chat_json
    chat_json([{"role": "user", "content": "верни json"}])
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "_llm.json"


def _config() -> dict:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if os.environ.get("LLM_API_KEY"):
        cfg["api_key"] = os.environ["LLM_API_KEY"]
    if os.environ.get("LLM_BASE_URL"):
        cfg["base_url"] = os.environ["LLM_BASE_URL"]
    return cfg


def clean(text: str) -> str:
    """Убирает служебные блоки рассуждений (MiniMax) из ответа."""
    import re as _re
    text = _re.sub(r"<think[\s\S]*?</think\s*>", "", text or "", flags=_re.I)
    text = _re.sub(r"^[\s\S]*?</think\s*>", "", text, flags=_re.I) if "<think" in (text or "").lower() and "</think" not in (text or "").lower() else text
    return text.strip()


def chat(messages: list[dict], model: str | None = None, max_tokens: int = 2000,
         temperature: float = 0.4, retries: int = 2) -> str:
    """Возвращает текст ответа модели."""
    cfg = _config()
    payload = {
        "model": model or cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"

    last_error = ""
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": "Bearer " + cfg["api_key"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=int(cfg.get("timeout", 25))) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return clean(body["choices"][0]["message"].get("content") or "")
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError("нейросеть не ответила: " + last_error)


def extract_json(text: str) -> dict:
    """Достаёт первый JSON-объект из ответа (модель любит обрамлять его текстом)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                chunk = text[start:i + 1]
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    start = None
    raise ValueError("в ответе модели нет JSON: " + text[:300])


def chat_json(messages: list[dict], **kwargs) -> dict:
    return extract_json(chat(messages, **kwargs))


if __name__ == "__main__":
    print(chat([{"role": "user", "content": "Скажи одним словом: работает?"}], max_tokens=50))
