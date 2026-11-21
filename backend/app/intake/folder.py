"""Watched folder intake: drop a PDF into data/inbox and it is picked up within seconds."""
from __future__ import annotations

import threading
import time

from ..config import INBOX_DIR, PROCESSED_DIR
from ..worker import create_run_from_path, move

state = {"last_scan": None, "picked_up": 0, "path": str(INBOX_DIR)}


def _loop():
    seen_sizes: dict[str, int] = {}
    while True:
        try:
            for p in sorted(INBOX_DIR.glob("*")):
                if p.suffix.lower() != ".pdf" or not p.is_file():
                    continue
                size = p.stat().st_size
                if seen_sizes.get(p.name) != size:  # wait until file finished copying
                    seen_sizes[p.name] = size
                    continue
                create_run_from_path(p, "folder", {"folder": str(INBOX_DIR)})
                move(p, PROCESSED_DIR)
                seen_sizes.pop(p.name, None)
                state["picked_up"] += 1
            state["last_scan"] = time.strftime("%H:%M:%S")
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)
        time.sleep(2)


def start() -> None:
    threading.Thread(target=_loop, daemon=True, name="folder-watcher").start()
