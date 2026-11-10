"""Управление компьютером: скриншоты, клики, ввод, окна.

    from pc import shot, click, type_text, hotkey, open_url, find_text

Всё координаты — в тех же пикселях, что отдаёт pyautogui.screenshot().
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pyautogui
import pywinauto  # noqa: F401  (нужен для поиска окон)
from pywinauto import Desktop

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.15

ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "_shots"
SHOTS.mkdir(exist_ok=True)


def shot(name: str = "pc.png") -> str:
    """Снимок экрана в файл, возвращает путь."""
    path = SHOTS / name
    pyautogui.screenshot().save(path)
    return str(path)


def size() -> tuple[int, int]:
    return pyautogui.size()


def click(x: int, y: int, double: bool = False) -> None:
    pyautogui.click(x, y, clicks=2 if double else 1, interval=0.08)
    time.sleep(0.35)


def move(x: int, y: int) -> None:
    pyautogui.moveTo(x, y, duration=0.15)


def type_text(text: str, interval: float = 0.02) -> None:
    pyautogui.write(text, interval=interval)


def hotkey(*keys: str) -> None:
    pyautogui.hotkey(*keys)
    time.sleep(0.3)


def press(*keys: str) -> None:
    for k in keys:
        pyautogui.press(k)
        time.sleep(0.1)


def open_url(url: str, new_tab: bool = True) -> None:
    """Открывает адрес в активном Chrome (он должен быть в фокусе)."""
    if new_tab:
        hotkey("ctrl", "t")
    hotkey("ctrl", "l")
    type_text(url, interval=0.005)
    press("enter")
    time.sleep(2.0)


def windows() -> list[tuple[str, str]]:
    """Список видимых окон: (заголовок, класс)."""
    out = []
    for w in Desktop(backend="uia").windows():
        try:
            title = w.window_text()
            if title:
                out.append((title, w.element_info.class_name))
        except Exception:  # noqa: BLE001
            continue
    return out


def focus_window(title_part: str) -> bool:
    """Поднимает окно, в заголовке которого есть строка."""
    for w in Desktop(backend="uia").windows():
        try:
            if title_part.lower() in (w.window_text() or "").lower():
                w.set_focus()
                time.sleep(0.5)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def run(cmd: list[str] | str) -> str:
    """Запускает программу и возвращает вывод."""
    result = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True)
    return (result.stdout or "") + (result.stderr or "")


if __name__ == "__main__":
    print("экран:", size())
    print("окна:")
    for title, cls in windows()[:10]:
        print("  -", title, "|", cls)
