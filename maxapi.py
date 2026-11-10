"""Работа с API MAX: правильные сертификаты и простые вызовы.

MAX использует российский корневой сертификат (Минцифры), которого нет в обычном
наборе. Скрипт склеивает его с обычными и подставляет Python.

    from maxapi import api, TOKEN
    api("GET", "/me")
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("MAX_TOKEN", "")
BASE = "https://platform-api2.max.ru"

ROOT = Path(__file__).resolve().parent
RU_CA = ROOT / "brand" / "russian_trusted_root_ca.crt"
BUNDLE = ROOT / "_ca_bundle.pem"


def ca_bundle() -> str:
    """Собирает общий набор сертификатов: обычные + российский корневой."""
    if BUNDLE.exists():
        return str(BUNDLE)
    parts: list[str] = []
    try:
        import certifi  # type: ignore

        parts.append(Path(certifi.where()).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        try:
            default = ssl.get_default_verify_paths().cafile
            if default:
                parts.append(Path(default).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    if RU_CA.exists():
        parts.append(RU_CA.read_text(encoding="utf-8"))
    BUNDLE.write_text("\n".join(parts), encoding="utf-8")
    return str(BUNDLE)


os.environ.setdefault("SSL_CERT_FILE", ca_bundle())
os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle())


def api(method: str, path: str, body: dict | None = None, token: str | None = None,
        timeout: int = 30) -> tuple[int, object]:
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": token or TOKEN,
        "Content-Type": "application/json",
    })
    ctx = ssl.create_default_context(cafile=ca_bundle())
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            text = resp.read().decode()
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:400]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


if __name__ == "__main__":
    print("сертификаты:", ca_bundle())
    print(api("GET", "/me"))
