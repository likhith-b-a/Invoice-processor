"""FastAPI app: REST + Server-Sent Events + serves the built React UI."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from . import config, worker
from .db import AuditLog, EmailDraft, Run, RunEvent, audit, init_db, session, update_run
from .intake import email_intake, folder
from .master import purchase_orders, po_with_balance, vendors
from .seed import reset_demo, seed_history

app = FastAPI(title="Invoice Agent")


@app.on_event("startup")
def _startup():
    init_db()
    seed_history()
    worker.start()
    folder.start()
    email_intake.start()


# ------------------------------------------------------------------ serializers
EFFECTIVE = {"approved": "APPROVE", "rejected": "REJECT"}


def summary(r: Run) -> dict:
    return {
        "id": r.id, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
        "source": r.source, "source_meta": r.source_meta, "filename": r.filename,
        "status": r.status, "current_stage": r.current_stage, "error": r.error,
        "decision": r.decision, "effective_decision": EFFECTIVE.get(r.review_status, r.decision),
        "headline": r.headline, "review_status": r.review_status,
        "vendor_id": r.vendor_id, "vendor_name": r.vendor_name, "invoice_number": r.invoice_number,
        "invoice_date": r.invoice_date, "po_number": r.po_number, "currency": r.currency,
        "subtotal": r.subtotal, "total": r.total, "duration_ms": r.duration_ms,
        "doc_type": r.doc_type, "extractor": r.extractor,
    }


def detail(r: Run) -> dict:
    with session() as s:
        events = list(s.exec(select(RunEvent).where(RunEvent.run_id == r.id).order_by(RunEvent.id)))
        drafts = list(s.exec(select(EmailDraft).where(EmailDraft.run_id == r.id)))
        logs = list(s.exec(select(AuditLog).where(AuditLog.run_id == r.id).order_by(AuditLog.id)))
    return {**summary(r), "explanation": r.explanation, "next_actions": r.next_actions, "rules": r.rules,
            "extracted": r.extracted, "normalized": r.normalized, "match": r.match,
            "review_comment": r.review_comment,
            "events": [ev(e) for e in events],
            "drafts": [d.model_dump(mode="json") for d in drafts],
            "audit": [a.model_dump(mode="json") for a in logs]}


def ev(e: RunEvent) -> dict:
    return {"id": e.id, "ts": e.ts.isoformat(), "stage": e.stage, "status": e.status, "title": e.title,
            "detail": e.detail, "duration_ms": e.duration_ms}


# ------------------------------------------------------------------ runs
@app.get("/api/runs")
def list_runs():
    with session() as s:
        return [summary(r) for r in s.exec(select(Run).order_by(Run.created_at.desc()))]


@app.get("/api/runs/{run_id}")
def get_run_detail(run_id: int):
    with session() as s:
        r = s.get(Run, run_id)
    if not r:
        raise HTTPException(404)
    return detail(r)


@app.get("/api/runs/{run_id}/file")
def run_file(run_id: int):
    with session() as s:
        r = s.get(Run, run_id)
    if not r:
        raise HTTPException(404)
    return FileResponse(r.file_path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{r.filename}"'})


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: int):
    async def gen():
        last = 0
        idle = 0
        while True:
            with session() as s:
                r = s.get(Run, run_id)
                events = list(s.exec(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > last)
                                     .order_by(RunEvent.id)))
            for e in events:
                last = e.id
                yield f"event: stage\ndata: {json.dumps(ev(e), default=str)}\n\n"
            if r and r.status in ("done", "error"):
                yield f"event: done\ndata: {json.dumps(detail(r), default=str)}\n\n"
                return
            idle += 1
            if idle % 30 == 0:
                yield ": ping\n\n"
            await asyncio.sleep(0.25)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/stream")
async def stream_all():
    """Dashboard feed: pushes run summaries whenever any run changes."""
    async def gen():
        since = datetime.min
        while True:
            with session() as s:
                rows = list(s.exec(select(Run).where(Run.updated_at > since).order_by(Run.updated_at)))
            for r in rows:
                since = max(since, r.updated_at)
                yield f"event: run\ndata: {json.dumps(summary(r), default=str)}\n\n"
            await asyncio.sleep(0.8)
            yield ": ping\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    ids = []
    for f in files:
        data = await f.read()
        if not data[:5] == b"%PDF-":
            raise HTTPException(400, f"{f.filename} is not a PDF")
        ids.append(worker.create_run(data, f.filename or "upload.pdf", "upload"))
    return {"run_ids": ids}


class ReviewIn(BaseModel):
    action: str  # approve | reject
    comment: str = ""


@app.post("/api/runs/{run_id}/review")
def review(run_id: int, body: ReviewIn):
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve|reject")
    status = "approved" if body.action == "approve" else "rejected"
    update_run(run_id, review_status=status, review_comment=body.comment, reviewed_at=datetime.now())
    audit(run_id, f"review_{status}", body.comment or "(no comment)", actor="reviewer")
    return get_run_detail(run_id)


@app.post("/api/runs/{run_id}/rerun")
def rerun(run_id: int):
    with session() as s:
        for e in s.exec(select(RunEvent).where(RunEvent.run_id == run_id)):
            s.delete(e)
        for d in s.exec(select(EmailDraft).where(EmailDraft.run_id == run_id, EmailDraft.status == "draft")):
            s.delete(d)
        s.commit()
    update_run(run_id, status="queued", decision="", headline="", rules=[], review_status="", review_comment="")
    audit(run_id, "rerun", actor="reviewer")
    worker.enqueue(run_id)
    return {"ok": True}


# ------------------------------------------------------------------ drafts
class DraftIn(BaseModel):
    to: str | None = None
    subject: str | None = None
    body: str | None = None


@app.get("/api/drafts")
def drafts():
    with session() as s:
        return [d.model_dump(mode="json") for d in s.exec(select(EmailDraft).order_by(EmailDraft.id.desc()))]


@app.patch("/api/drafts/{draft_id}")
def edit_draft(draft_id: int, body: DraftIn):
    with session() as s:
        d = s.get(EmailDraft, draft_id)
        if not d:
            raise HTTPException(404)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(d, k, v)
        s.add(d)
        s.commit()
        return d.model_dump(mode="json")


@app.post("/api/drafts/{draft_id}/send")
def send_draft(draft_id: int):
    with session() as s:
        d = s.get(EmailDraft, draft_id)
        if not d:
            raise HTTPException(404)
        try:
            email_intake.send_email(d.to, d.subject, d.body, d.in_reply_to)
            d.status, d.sent_at, d.error = "sent", datetime.now(), ""
            audit(d.run_id, "vendor_email_sent", f"to {d.to}", actor="reviewer")
        except Exception as e:  # noqa: BLE001
            d.status, d.error = "failed", str(e)[:300]
        s.add(d)
        s.commit()
        return d.model_dump(mode="json")


@app.post("/api/drafts/{draft_id}/discard")
def discard_draft(draft_id: int):
    with session() as s:
        d = s.get(EmailDraft, draft_id)
        if not d:
            raise HTTPException(404)
        d.status = "discarded"
        s.add(d)
        s.commit()
        audit(d.run_id, "vendor_email_discarded", actor="reviewer")
        return d.model_dump(mode="json")


# ------------------------------------------------------------------ master data, stats, intake
@app.get("/api/vendors")
def list_vendors():
    return vendors()


@app.get("/api/pos")
def list_pos():
    return [po_with_balance(p) for p in purchase_orders()]


@app.get("/api/stats")
def stats():
    with session() as s:
        runs = list(s.exec(select(Run)))
    live = [r for r in runs if r.source != "seed"]
    done = [r for r in live if r.status == "done"]
    by = {}
    for r in done:
        k = EFFECTIVE.get(r.review_status, r.decision)
        by[k] = by.get(k, 0) + 1
    held = [r for r in done if r.decision in ("HOLD", "FRAUD_HOLD", "REQUEST_INFO") and not r.review_status]
    approved = [r for r in done if EFFECTIVE.get(r.review_status, r.decision) == "APPROVE"]
    auto = [r for r in done if r.decision == "APPROVE"]
    return {
        "total_runs": len(live), "processed": len(done),
        "in_flight": sum(1 for r in live if r.status in ("queued", "running")),
        "errors": sum(1 for r in live if r.status == "error"),
        "by_decision": by,
        "auto_approve_rate": round(len(auto) / len(done), 3) if done else 0,
        "needs_attention": len(held),
        "value_on_hold": _by_currency(held), "value_approved": _by_currency(approved),
        "fraud_blocked": _by_currency([r for r in done if r.decision == "FRAUD_HOLD"]),
        "avg_duration_ms": int(sum(r.duration_ms for r in done) / len(done)) if done else 0,
        "by_source": {src: sum(1 for r in live if r.source == src) for src in {r.source for r in live}},
    }


def _by_currency(rs: list[Run]) -> dict:
    out: dict = {}
    for r in rs:
        out[r.currency or "?"] = round(out.get(r.currency or "?", 0) + (r.total or 0), 2)
    return out


@app.get("/api/intake")
def intake_status():
    return {"email": {**email_intake.state}, "folder": folder.state,
            "extractors": {"gemini": bool(config.GEMINI_API_KEY), "gemini_model": config.GEMINI_MODEL,
                           "ollama_model": config.OLLAMA_MODEL},
            "queue": worker.queue_size()}


@app.get("/api/samples")
def samples():
    manifest = config.SAMPLES_DIR / "manifest.json"
    items = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    return [i for i in items if (config.SAMPLES_DIR / i["file"]).exists() and not i.get("history")]


@app.post("/api/samples/{name}/run")
def run_sample(name: str):
    p = config.SAMPLES_DIR / name
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise HTTPException(404)
    items = {i["file"]: i for i in samples()}
    sender = items.get(name, {}).get("simulated_sender")
    meta = {"from": sender, "simulated": True} if sender else {}
    rid = worker.create_run_from_path(p, "sample", meta)
    return {"run_id": rid}


@app.post("/api/admin/reset")
def admin_reset():
    reset_demo()
    return {"ok": True}


# ------------------------------------------------------------------ UI
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = config.FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
