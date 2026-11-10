"""Сбор холодных лидов: клиники без сайта и бота.

Источники:
  • готовые базы business/leads_ufa_*.csv (собраны из открытых карт);
  • 2ГИС / Яндекс.Карты — если в _lead_sources.json есть API-ключи
    (без ключей сервисы данные не отдают).

    python business/lead_scanner.py --scan
"""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_cold_leads.json"
LETTERS = ROOT / "letters.jsonl"
CONFIG = ROOT / "_lead_sources.json"

CSV_FILES = {
    "leads_ufa_clinic.csv": "клиники",
    "leads_ufa_dentist.csv": "стоматологии",
    "leads_ufa_beauty.csv": "красота",
}


def digits(phone: str) -> str:
    first = re.split(r"[;,/]", phone or "")[0]
    d = re.sub(r"\D", "", first)
    if len(d) == 11 and d.startswith("8"):
        d = "7" + d[1:]
    if len(d) == 10:
        d = "7" + d
    return d


def source_key() -> str:
    try:
        return (json.loads(CONFIG.read_text(encoding="utf-8")).get("twogis_key") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def twogis_search(query: str, key: str, page: int = 1) -> list[dict]:
    params = {"q": query, "region_id": "17", "key": key,
              "page_size": 10, "page": page, "type": "branch"}
    url = "https://catalog.api.2gis.com/3.0/items?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ai-trader-leads/1.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("result") or {}).get("items") or []


def twogis_contacts(firm_id: str) -> tuple[list[str], list[str], list[str], list[str], float | str, int]:
    """Телефоны, сайты, почты и мессенджеры из публичной карточки 2ГИС."""
    url = f"https://2gis.ru/ufa/firm/{firm_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode("utf-8", "replace")
    rating, reviews = "", 0
    rpos = html.find('"reviews":')
    if rpos >= 0:
        try:
            robj, _ = json.JSONDecoder().raw_decode(html[html.find("{", rpos):])
            rating = robj.get("general_rating", "")
            reviews = int(robj.get("general_review_count") or 0)
        except Exception:  # noqa: BLE001
            pass
    pos = html.find('"contact_groups":')
    if pos < 0:
        return [], [], [], [], rating, reviews
    start = html.find("[", pos)
    try:
        groups, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return [], [], [], [], rating, reviews
    phones, sites, emails, socials = [], [], [], []
    for group in groups:
        for c in group.get("contacts") or []:
            kind = c.get("type")
            val = c.get("value") or c.get("text") or ""
            if kind == "phone":
                phones.append(val)
            elif kind == "website":
                sites.append(val)
                socials.append((c.get("url") or val).lower())
            elif kind == "email":
                emails.append(val)
    return phones, sites, emails, socials, rating, reviews


def scan_2gis(data: dict, by_name: set[str], by_phone: set[str],
              contacted: set[str], added: int) -> int:
    key = source_key()
    if not key:
        return added
    for query in ("стоматология", "клиника", "салон красоты"):
      for page in (1, 2, 3):
        try:
            items = twogis_search(query, key, page)
        except Exception:  # noqa: BLE001
            continue
        for item in items:
            name = (item.get("name") or "").strip()
            purpose = (item.get("purpose_name") or "").lower()
            if purpose and not any(w in purpose for w in
                                   ("медицин", "стоматолог", "клиник", "красот", "салон")):
                continue
            low_name = name.lower()
            if any(w in low_name for w in ("баня", "сауна", "кафе", "ресторан", "магазин")):
                continue
            if not name or len(name) < 2 or name.isdigit() or low_name in by_name:
                continue
            if name.lower() in contacted:
                continue
            try:
                phones, sites, emails, socials, rating, reviews = twogis_contacts(item.get("id", ""))
            except Exception:  # noqa: BLE001
                continue
            if not phones or sites:
                continue
            phone = phones[0]
            d = digits(phone)
            if not d or d in by_phone:
                continue
            messengers = []
            if len(d) == 11 and d[1] == "9":
                messengers.append("whatsapp")
            if any("t.me" in s for s in socials):
                messengers.append("telegram")
            if any("max.ru" in s for s in socials):
                messengers.append("max")
            by_name.add(name.lower())
            by_phone.add(d)
            data["leads"].append({
                "id": "c" + str(int(time.time() * 1000)) + str(added),
                "name": name,
                "niche": "клиники",
                "city": "Уфа",
                "address": (item.get("address_name") or "").strip(),
                "phone": phone,
                "phone_digits": d,
                "email": emails[0] if emails else "",
                "website": "",
                "source": "2ГИС (каталог)",
                "messengers": messengers,
                "rating_2gis": rating, "reviews_2gis": reviews,
                "status": "new",
                "note": "",
                "added": time.strftime("%Y-%m-%d"),
            })
            added += 1
            time.sleep(0.15)
    return added


def load_existing() -> dict:
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("leads"), list):
                return data
        except json.JSONDecodeError:
            pass
    return {"leads": [], "updated": "", "sources": []}


def save(data: dict) -> None:
    data["updated"] = time.strftime("%Y-%m-%d %H:%M")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def known_names() -> set[str]:
    names: set[str] = set()
    if LETTERS.exists():
        for line in LETTERS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                names.add(json.loads(line)["name"].strip().lower())
            except Exception:  # noqa: BLE001
                pass
    return names


def scan() -> dict:
    data = load_existing()
    by_name = {x["name"].strip().lower() for x in data["leads"]}
    by_phone = {x.get("phone_digits", "") for x in data["leads"] if x.get("phone_digits")}
    contacted = known_names()
    added = 0

    for filename, niche in CSV_FILES.items():
        path = ROOT / filename
        if not path.exists():
            continue
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            name = (row.get("name") or "").strip()
            phone = (row.get("phone") or "").strip()
            email = (row.get("email") or "").strip()
            website = (row.get("website") or "").strip()
            if not name or len(name) < 2 or name.isdigit() or (not phone and not email):
                continue
            if website:                 # холодные — только без сайта
                continue
            low = name.lower()
            if low in by_name or low in contacted:
                continue
            d = digits(phone)
            if d and d in by_phone:
                continue
            by_name.add(low)
            if d:
                by_phone.add(d)
            data["leads"].append({
                "id": "c" + str(int(time.time() * 1000)) + str(added),
                "name": name,
                "niche": niche,
                "city": (row.get("city") or "Уфа").strip(),
                "address": (row.get("address") or "").strip(),
                "phone": phone,
                "phone_digits": d,
                "email": email,
                "website": "",
                "source": "открытые карты (OSM-база)",
                "messengers": ["whatsapp"] if (len(d) == 11 and d[1] == "9") else [],
                "status": "new",
                "note": "",
                "added": time.strftime("%Y-%m-%d"),
            })
            added += 1

    added = scan_2gis(data, by_name, by_phone, contacted, added)
    data["sources"] = sorted({x.get("source", "") for x in data["leads"]})
    save(data)
    return {"added": added, "total": len(data["leads"])}


def scan_web() -> dict:
    """Живой скан открытых карт (OSM). Долгий — запускать отдельно, не из кнопки."""
    data = load_existing()
    by_name = {x["name"].strip().lower() for x in data["leads"]}
    by_phone = {x.get("phone_digits", "") for x in data["leads"] if x.get("phone_digits")}
    contacted = known_names()
    added = 0
    from collect_leads import build_rows, overpass
    elements = []
    for niche in ("clinic", "dentist", "beauty"):
        elements += overpass(niche, "ufa", limit=60)
    for row in build_rows(elements, "ufa"):
        name = (row.get("name") or "").strip()
        phone = (row.get("phone") or "").strip()
        if not name or not phone or (row.get("website") or "").strip():
            continue
        low = name.lower()
        if low in by_name or low in contacted:
            continue
        d = digits(phone)
        if d and d in by_phone:
            continue
        by_name.add(low)
        if d:
            by_phone.add(d)
        data["leads"].append({
            "id": "c" + str(int(time.time() * 1000)) + str(added),
            "name": name, "niche": "клиники", "city": "Уфа",
            "address": (row.get("address") or "").strip(),
            "phone": phone, "phone_digits": d,
            "email": (row.get("email") or "").strip(), "website": "",
            "source": "OpenStreetMap (живой скан)", "status": "new",
            "note": "", "added": time.strftime("%Y-%m-%d"),
        })
        added += 1
    data["sources"] = sorted({x.get("source", "") for x in data["leads"]})
    save(data)
    return {"added": added, "total": len(data["leads"])}


if __name__ == "__main__":
    import sys

    if "--scan" in sys.argv:
        print(scan())
    else:
        print(f"лидов в базе: {len(load_existing()['leads'])}")
