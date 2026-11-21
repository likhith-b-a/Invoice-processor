"""Single background worker + helpers to create runs from any intake source."""
from __future__ import annotations

import hashlib
import queue
import shutil
import threading
import uuid
from pathlib import Path

from sqlmodel import select

from .config import UPLOADS_DIR
from .db import Run, audit, session
from .pipeline.runner import process

_q: "queue.Queue[int]" = queue.Queue()
_started = False


def _loop():
    while True:
        run_id = _q.get()
        try:
            process(run_id)
        finally:
            _q.task_done()


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="pipeline-worker").start()
    with session() as s:  # resume anything interrupted
        for r in s.exec(select(Run).where(Run.status.in_(["queued", "running"]))):
            _q.put(r.id)


def enqueue(run_id: int) -> None:
    _q.put(run_id)


def queue_size() -> int:
    return _q.qsize()


def create_run(data: bytes, filename: str, source: str, meta: dict | None = None) -> int:
    safe = "".join(ch for ch in filename if ch.isalnum() or ch in "._- ").strip() or "invoice.pdf"
    dest = UPLOADS_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
    dest.write_bytes(data)
    run = Run(source=source, source_meta=meta or {}, filename=safe, file_path=str(dest),
              file_hash=hashlib.sha256(data).hexdigest())
    with session() as s:
        s.add(run)
        s.commit()
        s.refresh(run)
    audit(run.id, "received", f"{source}: {safe}")
    enqueue(run.id)
    return run.id


def create_run_from_path(path: Path, source: str, meta: dict | None = None) -> int:
    return create_run(path.read_bytes(), path.name, source, meta)


def move(path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    if target.exists():
        target = dest_dir / f"{uuid.uuid4().hex[:6]}_{path.name}"
    shutil.move(str(path), str(target))
