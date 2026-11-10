"""Рейтинги холодных лидов: 2ГИС + Яндекс.Карты.

    python business/ratings.py
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLD = ROOT / "_cold_leads.json"
CONFIG = ROOT / "_lead_sources.json"


def norm(s: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", (s or "").lower()).strip()


def key() -> str:
    try:
        return (json.loads(CONFIG.read_text(encoding="utf-8")).get("twogis_key") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def twogis_id(name: str) -> str:
    params = {"q": name, "region_id": "17", "key": key(), "page_size": 5, "type": "branch"}
    url = "https://catalog.api.2gis.com/3.0/items?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ai-trader/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    target = norm(name)
    for item in (data.get("result") or {}).get("items") or []:
        n = norm(item.get("name", ""))
        if n == target or n.startswith(target[:12]) or target.startswith(n[:12]):
            return item.get("id", "")
    return ""


def twogis_rating(firm_id: str) -> tuple[float | str, int]:
    url = f"https://2gis.ru/ufa/firm/{firm_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode("utf-8", "replace")
    pos = html.find('"reviews":')
    if pos < 0:
        return "", 0
    start = html.find("{", pos)
    try:
        data, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return "", 0
    return data.get("general_rating", ""), int(data.get("general_review_count") or 0)


def yandex_rating(name: str) -> tuple[float | str, int]:
    url = "https://yandex.ru/maps/?text=" + urllib.parse.quote(name + " Уфа")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode("utf-8", "replace")
    target = norm(name)
    for m in re.finditer("ratingData", html):
        pos = m.start()
        before = html[max(0, pos - 3000):pos]
        names = re.findall(r'"(?:shortTitle|title|name)":"([^"]{2,150})"', before)
        if not names:
            continue
        candidate = norm(names[-1])
        if not (candidate == target or candidate.startswith(target[:12]) or target.startswith(candidate[:12])):
            continue
        start = html.find("{", pos)
        try:
            data, _ = json.JSONDecoder().raw_decode(html[start:])
        except json.JSONDecodeError:
            continue
        return data.get("ratingValue", ""), int(data.get("reviewCount") or 0)
    return "", 0


def main() -> None:
    data = json.loads(COLD.read_text(encoding="utf-8"))
    leads = data.get("leads") or []
    done = 0
    for lead in leads:
        name = lead.get("name", "")
        if not name:
            continue
        if not lead.get("rating_2gis"):
            try:
                fid = twogis_id(name)
                if fid:
                    lead["rating_2gis"], lead["reviews_2gis"] = twogis_rating(fid)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.15)
        if not lead.get("rating_yandex"):
            try:
                lead["rating_yandex"], lead["reviews_yandex"] = yandex_rating(name)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.2)
        done += 1
        if done % 5 == 0:
            COLD.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print("обработано", done, flush=True)
    COLD.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    have2 = sum(1 for l in leads if l.get("rating_2gis"))
    havey = sum(1 for l in leads if l.get("rating_yandex"))
    print(f"готово: лидов {len(leads)}, с 2ГИС {have2}, с Яндексом {havey}")


if __name__ == "__main__":
    main()
