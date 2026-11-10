"""Единственный список команд бота — для Telegram (кнопка «☰» слева) и для MAX.

Раньше список жил в трёх местах: setup_bot.py, bot_max.py и разовом _cmds2.py.
Из-за этого меню в Telegram расползалось до 7 пунктов, и клиент жаловался,
что «кнопок слишком много и непонятно, как ориентироваться».

Правило: меняем команды только здесь. Оба бота и setup_bot.py берут список отсюда,
поэтому меню в Telegram и MAX всегда одинаковое и короткое.
"""
from __future__ import annotations

# Порядок = порядок в меню. Пять пунктов: те же, что в кнопочном меню, плюс «Помощь».
# /what и /bug остаются рабочими командами, но в меню не висят — они есть в /help.
COMMANDS = [
    {"command": "start", "description": "Меню"},
    {"command": "price", "description": "Цены и что входит"},
    {"command": "demo", "description": "Пример записи"},
    {"command": "order", "description": "Оставить заявку"},
    {"command": "help", "description": "Помощь и контакты"},
]

# Telegram ждёт ключ «command», MAX — «name». Один и тот же смысл, разный формат.
for_max = lambda: [{"name": c["command"], "description": c["description"]}  # noqa: E731
                   for c in COMMANDS]
