"""Пересобирает все демо из готовых данных в letters.jsonl — без нейросети.

Нужно, когда поменялся вид демо (шаблон), а данные клиник уже есть.

    python business/render_demos.py            # только пересобрать демо
    python business/render_demos.py --deploy   # пересобрать, собрать сайт и выложить
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from build_site import slug  # noqa: E402
from ufa import address_for  # noqa: E402

LETTERS = ROOT / "letters.jsonl"
TEMPLATE = ROOT / "demo_template.html"
DEMOS = ROOT / "demos"
HOSTING = ROOT / "_hosting.json"
BASE_URL = "https://ufa-zapis.surge.sh"

CSV_FILES = [
    "leads_ufa_dentist.csv",
    "leads_ufa_beauty.csv",
    "leads_ufa_clinic.csv",
    "leads_ufa_car_repair.csv",
    "leads_ufa_lawyer.csv",
]


def load_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for name in CSV_FILES:
        path = ROOT / name
        if not path.exists():
            continue
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            rows.setdefault(row["name"].strip().lower(), row)
    return rows


def render(entry: dict, row: dict | None) -> Path:
    html = TEMPLATE.read_text(encoding="utf-8")
    name = entry["name"].strip()
    profile = entry.get("profile") or {}
    address = (entry.get("address") or (row or {}).get("address") or "").replace('"', "").strip()
    if not address:
        address = address_for(name)
        entry["address"] = address
    phone = entry.get("phone") or (row or {}).get("phone") or ""
    html = (html
            .replace("__CLINIC__", name)
            .replace("__INIT__", (name[:1] or "К").upper())
            .replace("__PHONE__", phone.strip())
            .replace("__ADDRESS__", address)
            .replace("__HOURS__", (profile.get("hours") or "").replace('"', "").strip())
            .replace("__PRICES__", json.dumps(profile.get("prices") or [], ensure_ascii=False))
            .replace("__SERVICES__", json.dumps(profile.get("services") or [], ensure_ascii=False))
            .replace("__FAQ__", json.dumps(profile.get("faq") or [], ensure_ascii=False)))
    out = DEMOS / f"{slug(name)}.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true")
    args = ap.parse_args()

    rows = load_rows()
    entries = [json.loads(line) for line in LETTERS.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen, unique = set(), []
    for e in entries:
        key = e["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)

    for e in unique:
        path = render(e, rows.get(e["name"].strip().lower()))
        e["demo_url"] = f"{BASE_URL}/demos/{path.name}"
        print(f"  {e['name']:<32} {path.name}")

    LETTERS.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in unique) + "\n",
        encoding="utf-8",
    )
    print(f"демо пересобрано: {len(unique)}")

    if args.deploy:
        subprocess.run([sys.executable, str(ROOT / "build_site.py")], check=True)
        token = json.loads(HOSTING.read_text(encoding="utf-8"))["token"]
        import shutil
        env = dict(os.environ)
        env["SURGE_TOKEN"] = token
        subprocess.run([shutil.which("npx") or "npx", "--yes", "surge",
                        str(ROOT / "site"), BASE_URL.replace("https://", "")],
                       check=True, env=env)
        subprocess.run([sys.executable, str(ROOT / "make_send_page.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "pipeline.py"), "--limit", "0"], check=False)


if __name__ == "__main__":
    main()
