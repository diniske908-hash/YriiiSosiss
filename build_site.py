"""Сборка статического сайта с демо для отправки клиентам.

Берёт все HTML из business/demos, кладёт в business/site/demos/ под латинскими
именами (чтобы ссылки в письмах были читаемыми) и делает index.html.

python -m business.build_site
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_PUBLIC = "https://ufa-zapis.surge.sh/demos/moj-doktor.html"
DEMOS = ROOT / "demos"
SITE = ROOT / "site"

# Русские буквы -> латиница. Нужна только для имён файлов в ссылках.
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slug(text: str) -> str:
    """'32 карата' -> '32-karata'."""
    out = []
    for ch in text.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug_ = "".join(out)
    while "--" in slug_:
        slug_ = slug_.replace("--", "-")
    return slug_.strip("-")


CARD = """
    <a class="card" href="demos/{file}">
      <div class="ava">{initial}</div>
      <div class="meta">
        <div class="name">{name}</div>
        <div class="sub">демо-бот записи</div>
      </div>
      <div class="arrow">→</div>
    </a>"""


def load_display_names() -> dict[str, str]:
    """slug -> настоящее название клиники (из letters.jsonl)."""
    import json

    path = ROOT / "letters.jsonl"
    names: dict[str, str] = {}
    if not path.exists():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        names[slug(entry["name"])] = entry["name"].strip()
    return names


def main() -> None:
    SITE.mkdir(exist_ok=True)
    demos_out = SITE / "demos"
    if demos_out.exists():
        for old in demos_out.glob("*.html"):
            old.unlink()
    demos_out.mkdir(exist_ok=True)

    display = load_display_names()
    cards = []
    mapping = []
    used = set()
    for f in sorted(DEMOS.glob("*.html")):
        key = slug(f.stem)
        name = display.get(key) or f.stem.replace("-", " ").title()
        new_name = key + ".html"
        if new_name in used:
            continue
        used.add(new_name)
        cards.append(CARD.format(file=new_name, initial=name[:1].upper(), name=name))
        shutil.copy(f, demos_out / new_name)
        mapping.append(f"{f.name} -> {new_name}")

    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Зиныч IT — запись для клиник</title>
<style>
  :root{{--bg:#f2f5f9;--card:#fff;--txt:#111a24;--dim:#5f6b7a;--line:#e6ecf3;--acc:#2f6bff}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--txt);
       font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;padding:26px 16px 60px}}
  .wrap{{max-width:560px;margin:0 auto}}
  .brand{{display:flex;align-items:center;gap:11px;margin-bottom:26px}}
  h1{{font-size:30px;line-height:1.15;margin:0 0 12px;letter-spacing:-.02em}}
  .lead{{color:var(--dim);font-size:16px;line-height:1.5;margin-bottom:22px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;
        box-shadow:0 2px 10px rgba(17,26,36,.05);margin-bottom:12px}}
  .num{{display:flex;gap:12px;align-items:flex-start;margin-bottom:14px}}
  .num:last-child{{margin-bottom:0}}
  .n{{width:26px;height:26px;border-radius:50%;background:#e7f0ff;color:var(--acc);font-weight:700;
      font-size:13px;display:flex;align-items:center;justify-content:center;flex:none}}
  .t{{font-size:14.5px;line-height:1.4}}
  .cta{{display:block;text-align:center;background:linear-gradient(135deg,#2f6bff,#1ac2b6);color:#fff;
        text-decoration:none;border-radius:14px;padding:16px;font-weight:700;font-size:16px;
        box-shadow:0 6px 18px rgba(47,107,255,.28);margin-bottom:10px}}
  .ghost{{display:block;text-align:center;background:#fff;border:1px solid var(--line);color:var(--txt);
          text-decoration:none;border-radius:14px;padding:14px;font-size:14.5px;margin-bottom:18px}}
  .price{{font-size:13.5px;color:var(--dim);text-align:center;margin-bottom:22px}}
  .foot{{color:var(--dim);font-size:12.5px;text-align:center;line-height:1.5}}
</style></head>
<body><div class="wrap">
  <div class="brand">
    <svg width="40" height="40" viewBox="0 0 512 512" aria-hidden="true">
      <defs><linearGradient id="bg1" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#2F6BFF"/><stop offset="1" stop-color="#1AC2B6"/></linearGradient></defs>
      <rect width="512" height="512" rx="118" fill="url(#bg1)"/>
      <text x="256" y="300" text-anchor="middle" font-family="Segoe UI,Arial" font-weight="800"
            font-size="356" fill="#fff">З</text>
      <circle cx="392" cy="392" r="26" fill="#fff" opacity=".92"/>
    </svg>
    <div><div style="font-weight:800;font-size:17px">ЗИНЫЧ IT</div>
         <div style="font-size:11.5px;color:var(--dim)">боты и компьютерная помощь · Уфа</div></div>
  </div>

  <h1>Запись в клинику за 40 секунд — без звонков</h1>
  <div class="lead">Клиент сам выбирает услугу и время, заявка сразу приходит администратору.
  Работает в MAX и Telegram, в любое время суток.</div>

  <a class="cta" href="{BASE_PUBLIC}">Посмотреть, как это работает</a>
  <a class="ghost" href="mailto:danzinowjev@yandex.ru?subject=Хочу такой бот для клиники">Хочу такой же — написать</a>

  <div class="card">
    <div class="num"><div class="n">1</div><div class="t">Клиент открывает бота и выбирает услугу с ценой</div></div>
    <div class="num"><div class="n">2</div><div class="t">Выбирает день и свободное время — видит только реальные окна</div></div>
    <div class="num"><div class="n">3</div><div class="t">Вам приходит готовая заявка, клиенту — подтверждение и напоминание</div></div>
  </div>

  <div class="price">Бот — 10 000 ₽ · бот с сайтом — 20 000 ₽ · запуск 5–10 дней</div>

  <div class="foot">Зиныч IT · Уфа · <a href="https://t.me/zinych_zapis_bot" style="color:var(--acc)">@zinych_zapis_bot</a></div>
</div></body></html>"""
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (ROOT / "_mapping.txt").write_text("\n".join(mapping), encoding="utf-8")
    print(f"сайт собран: {SITE}")
    print(f"демо внутри: {len(cards)}")
    for line in mapping:
        print("  " + line)


if __name__ == "__main__":
    main()
