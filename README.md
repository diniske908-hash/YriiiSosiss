# Зиныч IT — админка и боты записи

Админка для клиник: диалоги Telegram / MAX / WhatsApp / почта, сделки-канбан,
дела, холодные лиды, демо-страницы записи.

## Что внутри
- `admin_server.py` — админка (Python stdlib, http://127.0.0.1:8765)
- `bot.py`, `bot_max.py` — Telegram и MAX боты
- `relay.py`, `handoff.py` — ответы и пауза бота
- `mail_watch.py` — приём почты
- `wa_bridge/` — WhatsApp Web мост (Node.js)
- `demos/` — демо-страницы клиник
- `test_admin.py`, `test_bot.py`, `test_demo.js`, `check_links.py` — тесты

## Запуск
```bash
python run_all.py          # все службы
python run_all.py --status
python admin_server.py --port 8765
```

Настройки (не входят в репозиторий, создаются локально):
- `_mail.json` — SMTP/IMAP
- `_llm.json` — Gonka API
- `_lead_sources.json` — ключ 2ГИС
- `_events.jsonl`, `_crm.json`, `_cold_leads.json` — данные

Переменные окружения:
```
TG_TOKEN=...
MAX_TOKEN=...
MAIL_LOGIN=...
MAIL_PASSWORD=...
LLM_API_KEY=...
```

## WhatsApp
```bash
cd wa_bridge
npm install
node wa_bridge.js
```
Открыть http://127.0.0.1:8790/qr и отсканировать QR в WhatsApp →
Связанные устройства. Это неофициальный WhatsApp Web: используйте на свой риск.

## Тесты
```bash
python test_bot.py       # 77
python test_admin.py     # 42
node test_demo.js        # 68
python check_links.py    # 16
```

## Безопасность
В репозитории **нет** паролей, токенов, сессий WhatsApp и базы клиентов.
Перед публикацией проверьте свои локальные `_*.json` и `wa_bridge/_session`.
