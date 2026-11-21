"""Seed history: invoices already approved last month, so split-PO and near-duplicate logic has real context."""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlmodel import delete, select

from .config import SAMPLES_DIR
from .db import AuditLog, EmailDraft, Run, RunEvent, audit, session

HISTORY = [
    {
        "file": "history/cobalt_INV-C-0418.pdf", "created": "2026-10-08T10:12:00",
        "vendor_id": "V004", "vendor_name": "Cobalt Cloud Services Ltd", "invoice_number": "INV-C-0418",
        "invoice_date": "2026-10-06", "po_number": "PO-1004", "currency": "USD",
        "lines": [{"description": "Cloud migration consulting - Sep 22 to Oct 03", "quantity": 40,
                   "unit_price": 150.0, "amount": 6000.0, "matched_sku": "CC-MIG-HR"}],
        "subtotal": 6000.0, "tax": 0.0,
    },
    {
        "file": "history/cobalt_INV-C-0502.pdf", "created": "2026-10-27T09:40:00",
        "vendor_id": "V004", "vendor_name": "Cobalt Cloud Services Ltd", "invoice_number": "INV-C-0502",
        "invoice_date": "2026-10-24", "po_number": "PO-1004", "currency": "USD",
        "lines": [{"description": "Cloud migration consulting - Oct 06 to Oct 24", "quantity": 45,
                   "unit_price": 150.0, "amount": 6750.0, "matched_sku": "CC-MIG-HR"}],
        "subtotal": 6750.0, "tax": 0.0,
    },
    {
        "file": "history/pixelpine_PP-2291.pdf", "created": "2026-11-10T14:05:00",
        "vendor_id": "V005", "vendor_name": "Pixel & Pine Design Studio", "invoice_number": "PP-2291",
        "invoice_date": "2026-11-09", "po_number": "PO-1005", "currency": "USD",
        "lines": [{"description": "Brand refresh - Milestone 2: identity system and logo suite", "quantity": 1,
                   "unit_price": 4800.0, "amount": 4800.0, "matched_sku": "PP-BR-M2"}],
        "subtotal": 4800.0, "tax": 0.0,
    },
    {
        "file": "history/pixelpine_PP-2240.pdf", "created": "2026-10-02T11:30:00",
        "vendor_id": "V005", "vendor_name": "Pixel & Pine Design Studio", "invoice_number": "PP-2240",
        "invoice_date": "2026-09-30", "po_number": "PO-1005", "currency": "USD",
        "lines": [{"description": "Brand refresh - Milestone 1: discovery and moodboards", "quantity": 1,
                   "unit_price": 4800.0, "amount": 4800.0, "matched_sku": "PP-BR-M1"}],
        "subtotal": 4800.0, "tax": 0.0,
    },
]


def seed_history() -> None:
    with session() as s:
        if s.exec(select(Run).where(Run.source == "seed")).first():
            return
        for h in HISTORY:
            path = SAMPLES_DIR / h["file"]
            data = path.read_bytes() if path.exists() else h["invoice_number"].encode()
            total = h["subtotal"] + h["tax"]
            r = Run(
                created_at=datetime.fromisoformat(h["created"]), updated_at=datetime.fromisoformat(h["created"]),
                source="seed", source_meta={"note": "Historical invoice (pre-loaded)"},
                filename=path.name, file_path=str(path), file_hash=hashlib.sha256(data).hexdigest(),
                status="done", decision="APPROVE",
                headline=f"Approve {h['invoice_number']} from {h['vendor_name']} for {h['currency']} {total:,.2f}",
                explanation=["Historical invoice approved in a previous period."],
                vendor_id=h["vendor_id"], vendor_name=h["vendor_name"], invoice_number=h["invoice_number"],
                invoice_date=h["invoice_date"], po_number=h["po_number"], currency=h["currency"],
                subtotal=h["subtotal"], total=total, extractor="history", doc_type="text",
                normalized={"line_items": h["lines"], "subtotal": h["subtotal"], "total": total,
                            "invoice_number": h["invoice_number"], "invoice_date": h["invoice_date"],
                            "currency": h["currency"], "vendor_name": h["vendor_name"]},
            )
            s.add(r)
        s.commit()


def reset_demo() -> None:
    with session() as s:
        for model in (RunEvent, EmailDraft, AuditLog, Run):
            s.exec(delete(model))
        s.commit()
    seed_history()
    with session() as s:
        for r in s.exec(select(Run)):
            audit(r.id, "seeded", "historical invoice")
