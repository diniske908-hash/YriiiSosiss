"""Сбор базы клиентов из OpenStreetMap (бесплатно, без ключей).

python -m business.collect_leads --niche dentist --city ufa --out business/leads_ufa.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
import time
from pathlib import Path

# bbox: south, west, north, east
CITIES = {
    "ufa": ("54.60,55.75,54.90,56.20", "Уфа"),
    "moscow": ("55.55,37.35,55.95,37.95", "Москва"),
    "spb": ("59.75,30.10,60.10,30.65", "Санкт-Петербург"),
}

NICHES = {
    "dentist": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
    "car_repair": ['["shop"="car_repair"]', '["amenity"="car_repair"]'],
    "beauty": ['["shop"="beauty"]', '["leisure"="spa"]'],
    "lawyer": ['["office"="lawyer"]'],
    "clinic": ['["amenity"="clinic"]', '["healthcare"="clinic"]'],
    "restaurant": ['["amenity"="restaurant"]'],
    "fitness": ['["leisure"="fitness_centre"]'],
}


ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def overpass(niche: str, city: str, limit: int = 300) -> list[dict]:
    bbox, _ = CITIES[city]
    parts = []
    for tag in NICHES[niche]:
        parts.append(f"node{tag}({bbox});")
        parts.append(f"way{tag}({bbox});")
    query = ("[out:json][timeout:90];(" + "".join(parts) + f");out center tags {limit};")
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for ep in ENDPOINTS:
        for attempt in range(2):
            try:
                req = urllib.request.Request(ep, data=data,
                                             headers={"User-Agent": "ai-trader-leads/1.0",
                                                      "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode()).get("elements", [])
            except Exception as e:
                last = e
                time.sleep(3)
    raise RuntimeError(f"overpass недоступен: {last}")


def build_rows(elements: list[dict], city: str) -> list[dict]:
    rows, seen = [], set()
    for e in elements:
        t = e.get("tags", {})
        name = (t.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        street = t.get("addr:street", "")
        house = t.get("addr:housenumber", "")
        rows.append({
            "name": name,
            "city": CITIES[city][1],
            "address": f"{street} {house}".strip(),
            "phone": t.get("phone") or t.get("contact:phone") or "",
            "website": t.get("website") or t.get("contact:website") or "",
            "email": t.get("email") or t.get("contact:email") or "",
            "vk": t.get("contact:vk") or "",
            "instagram": t.get("contact:instagram") or "",
            "lat": e.get("lat") or (e.get("center") or {}).get("lat"),
            "lon": e.get("lon") or (e.get("center") or {}).get("lon"),
            "status": "new",
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--niche", default="dentist", choices=list(NICHES))
    ap.add_argument("--city", default="ufa", choices=list(CITIES))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    els = overpass(args.niche, args.city)
    rows = build_rows(els, args.city)
    out = Path(args.out or f"business/leads_{args.city}_{args.niche}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name"])
        w.writeheader()
        w.writerows(rows)
    have_phone = sum(1 for r in rows if r["phone"])
    have_site = sum(1 for r in rows if r["website"])
    print(f"{args.niche}/{args.city}: {len(rows)} компаний -> {out}")
    print(f"  с телефоном: {have_phone}, с сайтом: {have_site}")


if __name__ == "__main__":
    main()
