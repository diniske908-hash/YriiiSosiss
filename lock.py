"""Надёжная защита от двух копий: блокировка файла средствами Windows.

Пока процесс жив, файл заблокирован. Вторая копия не сможет его взять и выйдет.
PID-файл мог устареть после перезагрузки — блокировка ОС не устаревает.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "_run"

_handle = None  # держим открытым всю жизнь процесса


def acquire(name: str) -> None:
    global _handle
    RUN.mkdir(exist_ok=True)
    path = RUN / f"{name}.lock"
    try:
        import msvcrt
    except ImportError:  # не Windows
        return

    try:
        fh = open(path, "a+")
    except PermissionError:
        print(f"{name}: файл блокировки занят — уже работает другая копия", flush=True)
        sys.exit(0)
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print(f"{name}: уже работает другая копия — выхожу", flush=True)
        try:
            fh.close()
        except Exception:  # noqa: BLE001
            pass
        sys.exit(0)

    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _handle = fh
    (RUN / f"{name}.pid").write_text(str(os.getpid()), encoding="utf-8")


def release(name: str) -> None:
    global _handle
    if _handle is None:
        return
    try:
        import msvcrt
        _handle.seek(0)
        msvcrt.locking(_handle.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        _handle.close()
    except Exception:  # noqa: BLE001
        pass
    _handle = None
