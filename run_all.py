"""Один процесс — все службы Зиныч IT.

Поднимает и присматривает за всем сразу: бот, MAX-бот, диспетчер, сторож почты,
админка. Если служба упала — перезапускает. Логи в business/_logs/.

    python business/run_all.py            # запустить всё
    python business/run_all.py --status   # показать, что работает
    python business/run_all.py --stop     # остановить всё
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "_logs"
RUN = ROOT / "_run"
STOP_FLAG = RUN / "stop.flag"

SERVICES = [
    ("bot.py", ["bot.py"], "Телеграм-бот"),
    ("bot_max.py", ["bot_max.py"], "MAX-бот"),
    ("ops_agent.py", ["ops_agent.py", "--watch"], "Диспетчер"),
    ("mail_watch.py", ["mail_watch.py"], "Сторож почты"),
    ("wa_service.py", ["wa_service.py"], "WhatsApp"),
    ("admin_server.py", ["admin_server.py", "--port", "8765"], "Админка"),
]


def status() -> None:
    print("PID-файлы:")
    for name, _, title in SERVICES:
        pid_file = RUN / f"{name.replace('.py', '')}.pid"
        alive = "—"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                     capture_output=True, text=True).stdout
                alive = "работает" if str(pid) in out else "не работает"
            except Exception:  # noqa: BLE001
                alive = "?"
        print(f"  {title:16s} {alive}")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/api/clients", timeout=5) as r:
            print("админка отвечает:", r.status)
    except Exception:  # noqa: BLE001
        print("админка не отвечает")


def stop_all() -> None:
    STOP_FLAG.parent.mkdir(exist_ok=True)
    STOP_FLAG.write_text("stop", encoding="utf-8")
    for name, _, title in SERVICES:
        pid_file = RUN / f"{name.replace('.py', '')}.pid"
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            print("остановлен:", title)
        except Exception:  # noqa: BLE001
            pass


def run() -> None:
    LOGS.mkdir(exist_ok=True)
    RUN.mkdir(exist_ok=True)
    if STOP_FLAG.exists():
        STOP_FLAG.unlink()

    procs: dict[str, subprocess.Popen] = {}
    logfiles: dict[str, object] = {}

    def start(name: str, args: list[str], title: str) -> None:
        log = (LOGS / f"{name.replace('.py', '')}.log").open("a", encoding="utf-8")
        log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} запуск {title} ===\n")
        log.flush()
        proc = subprocess.Popen([sys.executable, *args], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT)
        procs[name] = proc
        logfiles[name] = log
        (RUN / f"{name.replace('.py', '')}.pid").write_text(str(proc.pid), encoding="utf-8")
        print(f"  ✓ {title} (pid {proc.pid})", flush=True)

    print("Запускаю все службы…", flush=True)
    for name, args, title in SERVICES:
        start(name, args, title)

    try:
        while True:
            if STOP_FLAG.exists():
                print("Получен сигнал остановки", flush=True)
                break
            for name, args, title in SERVICES:
                proc = procs.get(name)
                if proc and proc.poll() is None:
                    continue
                if proc:
                    print(f"  ⚠ {title} упал — перезапускаю", flush=True)
                    try:
                        logfiles[name].close()  # type: ignore[union-attr]
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(3)
                start(name, args, title)
            time.sleep(15)
    finally:
        for name, proc in procs.items():
            if proc.poll() is None:
                proc.terminate()
        print("Все службы остановлены.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.stop:
        stop_all()
    else:
        from lock import acquire
        acquire("run_all")
        run()


if __name__ == "__main__":
    main()
