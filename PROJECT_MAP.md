# Карта проекта «Зиныч IT»

## Корень
`C:\Users\Пользователь\Documents\deepseek-harness\default-workspace\ai-trader\business`

## Запуск
- `run_all.py` — запускает все службы (Telegram, MAX, диспетчер, почта, WhatsApp, админка).
- `start_all.vbs` — запуск без окна.
- Автозагрузка: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Зиныч IT — службы.vbs`
- Ярлык: рабочий стол → `Зиныч IT — админка.url`
- Админка: http://127.0.0.1:8765
- WhatsApp QR: http://127.0.0.1:8790/qr

## Основной код
- `admin_server.py` — админка (интерфейс, API, сделки, дела, холодные лиды, слияние).
- `bot.py` — Telegram-бот. `bot_max.py` — MAX-бот.
- `commands.py`, `answers.py`, `sales.py` — меню и тексты ботов.
- `relay.py` — отправка ответов в TG/MAX/почту/WhatsApp.
- `handoff.py` — пауза бота и передача владельцу.
- `mail_watch.py` — приём почты. `wa_service.py` — запуск WhatsApp-моста.
- `wa_bridge/wa_bridge.js` — WhatsApp Web (Node), сессия в `wa_bridge/_session`.
- `lead_scanner.py` — сбор лидов, `ratings.py` — рейтинги 2ГИС/Яндекс, `llm.py` — Gonka.

## Данные (JSON/JSONL)
`_events.jsonl` — все сообщения и ошибки.
`_crm.json` — сделки, дела, заметки.
`_sections.json` — разделы. `_archive.json` — архив.
`_merges.json` — объединённые клиенты. `_names.json` — переименования.
`_cold_leads.json` — холодные лиды. `_cold_script.json` — базовый скрипт.
`_lead_sources.json` — ключ 2ГИС. `_mail.json` — почта. `_llm.json` — нейросеть.
`_handoff.json` — паузы ботов. `_mail_seen.json` — обработанные письма.

## Демо и сайт
- `demos/` — 27 демо-страниц клиник.
- `site/` — собранная копия для выкладки на Surge.
- `demo_template.html` — шаблон демо.
- `build_site.py` — сборка сайта.

## Тесты и отчёты
- `test_bot.py` — 77 проверок ботов.
- `test_admin.py` — 42 проверки API/логики админки.
- `test_demo.js` — 68 проверок демо-записи.
- `check_links.py` — 16 ссылок.
- `_reports/` — отчёты QA и Replica/REA.
- `_shots/` — скриншоты.

## Логи и служебное
- `_logs/` — логи служб (`admin_server.log`, `bot.log`, …).
- `_run/` — PID-файлы и старые тестовые прогоны.
- `_chrome_profile/` — профиль Chrome для скриншотов.

## Документы
`RELEASE.md` — инструкция запуска, `HANDOFF.md` — память проекта,
`PROJECT_MAP.md` — эта карта, `OUTREACH.md`, `PLAYBOOK.md`, `SESSION_BRIEF.md`.

## Replica/REA
`C:\Users\Пользователь\Documents\deepseek-harness\default-workspace\replica`
(`recon.md`, `features.csv`, `reviews.md`, `parity.md`).

## Важно
- `_mail.json`, `_llm.json`, `_lead_sources.json`, `wa_bridge/_session` — секреты,
  не пересылать и не выкладывать.
- В корне много временных `_*.py` (отладка/тесты). Их можно удалить, если не нужны.
