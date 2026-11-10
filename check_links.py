"""Быстрая проверка ссылок через curl (у него соединение с surge работает стабильно).

    python business/check_links.py
"""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LETTERS = ROOT / "letters.jsonl"
SITE = "https://ufa-zapis.surge.sh"
TIMEOUT = 8


def status(url: str) -> str:
    try:
        res = subprocess.run(
            ["curl.exe", "-s", "-o", "NUL", "-m", str(TIMEOUT), "-w", "%{http_code}", url],
            capture_output=True, timeout=TIMEOUT + 5,
        )
        code = (res.stdout or b"").decode("utf-8", "replace").strip()
        return code or "000"
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__


def main() -> None:
    urls = [SITE]
    if LETTERS.exists():
        for line in LETTERS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            url = json.loads(line).get("demo_url")
            if url:
                urls.append(url)

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(status, urls))

    bad = [(u, c) for u, c in zip(urls, codes) if c != "200"]
    print(f"проверено ссылок: {len(urls)}")
    if bad:
        print(f"не открываются: {len(bad)}")
        for url, code in bad[:10]:
            print(f"  {code}  {url}")
    else:
        print("все ссылки открываются")


if __name__ == "__main__":
    main()
