"""Run every sample invoice through the pipeline (no server) and compare to the expected decision.

Usage:  .venv/Scripts/python scripts/run_samples.py [--keep]   (--keep: don't reset DB first)
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("STAGE_DELAY_MS", "0")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import SAMPLES_DIR  # noqa: E402
from app.db import get_run, init_db  # noqa: E402
from app.pipeline.runner import process  # noqa: E402
from app.seed import reset_demo  # noqa: E402
from app.worker import create_run  # noqa: E402

init_db()
if "--keep" not in sys.argv:
    reset_demo()
import app.worker as w  # noqa: E402
w.enqueue = lambda rid: None  # run synchronously below

manifest = json.loads((SAMPLES_DIR / "manifest.json").read_text())
ok = 0
for m in manifest:
    p = SAMPLES_DIR / m["file"]
    rid = create_run(p.read_bytes(), p.name, "sample", {"from": m["simulated_sender"], "simulated": True})
    process(rid)
    r = get_run(rid)
    hit = r.decision == m["expect"]
    ok += hit
    print(f"{'PASS' if hit else 'MISS'}  {m['file']:<45} expected {m['expect']:<12} got {r.decision or r.status:<12} "
          f"[{r.extractor}] {r.error[:120] if r.error else r.headline}")
    if not hit or "-v" in sys.argv:
        for rule in r.rules:
            if rule["status"] in ("warn", "fail"):
                print(f"        {rule['id']} {rule['status']:<4} {rule['message'][:150]}")
print(f"\n{ok}/{len(manifest)} matched expectations")
