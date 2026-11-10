"""Держит WhatsApp-мост (Node) живым; запускается из run_all.py."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT / "wa_bridge"


def main() -> None:
    while True:
        proc = subprocess.Popen(["node", "wa_bridge.js"], cwd=BRIDGE)
        proc.wait()
        time.sleep(5)


if __name__ == "__main__":
    main()
