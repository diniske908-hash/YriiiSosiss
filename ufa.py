"""Выдуманные, но правдоподобные адреса в Уфе — для демо.

Адрес детерминированный: одна и та же клиника всегда получает один и тот же адрес.
Настоящие адреса в базу OSM часто не попадают, а демо без адреса выглядит недоделанным.

    from ufa import address_for
    address_for("Мой доктор")  ->  "Уфа, ул. Ленина, 42"
"""
from __future__ import annotations

STREETS = [
    "ул. Ленина",
    "пр. Октября",
    "ул. Цюрупы",
    "ул. Коммунистическая",
    "ул. Карла Маркса",
    "ул. Пушкина",
    "ул. Гоголя",
    "ул. Заки Валиди",
    "ул. Мажита Гафури",
    "ул. Чернышевского",
    "ул. Аксакова",
    "ул. Свердлова",
    "ул. Революционная",
    "ул. Мира",
    "ул. Степана Кувыкина",
    "ул. Российской",
    "ул. Менделеева",
    "ул. 50 лет Октября",
    "ул. Бабушкина",
    "ул. Кремлёвская",
]

DISTRICTS = ["", "", "", " (Советский р-н)", " (Кировский р-н)", " (Ленинский р-н)"]


def _hash(text: str) -> int:
    h = 2166136261
    for ch in text:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h


def address_for(name: str) -> str:
    """Стабильный адрес в Уфе по названию клиники."""
    h = _hash((name or "клиника").strip().lower())
    street = STREETS[h % len(STREETS)]
    number = 5 + (h // 7) % 95
    district = DISTRICTS[(h // 13) % len(DISTRICTS)]
    return f"Уфа, {street}, {number}{district}"


def maps_links(address: str) -> dict[str, str]:
    """Ссылки на карты: откроются и в браузере, и в приложении на телефоне."""
    import urllib.parse

    q = urllib.parse.quote(address)
    return {
        "yandex": f"https://yandex.ru/maps/?text={q}",
        "google": f"https://maps.google.com/?q={q}",
        "2gis": f"https://2gis.ru/ufa/search/{q}",
        "geo": f"geo:0,0?q={q}",
    }


if __name__ == "__main__":
    for city_name in ["Мой доктор", "Колибри", "Галадент", "32 карата"]:
        print(city_name, "->", address_for(city_name))
