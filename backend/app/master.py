"""Procurement master data (vendors, POs) + live PO consumption derived from approved runs."""
from __future__ import annotations

import json
from functools import lru_cache

from .config import MASTER_DIR
from .db import Run, all_runs


@lru_cache
def vendors() -> list[dict]:
    return json.loads((MASTER_DIR / "vendors.json").read_text(encoding="utf-8"))


@lru_cache
def purchase_orders() -> list[dict]:
    pos = json.loads((MASTER_DIR / "purchase_orders.json").read_text(encoding="utf-8"))
    for po in pos:
        po["total_amount"] = round(sum(l["quantity"] * l["unit_price"] for l in po["lines"]), 2)
    return pos


def vendor_by_id(vid: str) -> dict | None:
    return next((v for v in vendors() if v["id"] == vid), None)


def po_by_number(num: str) -> dict | None:
    return next((p for p in purchase_orders() if p["po_number"] == num), None)


def is_effectively_approved(run: Run) -> bool:
    """Counts against PO balance: auto-approved (and not reversed) or approved by reviewer."""
    if run.review_status == "approved":
        return True
    if run.review_status == "rejected":
        return False
    return run.decision == "APPROVE" and run.status == "done"


def po_consumption(po_number: str, exclude_run_id: int | None = None) -> dict:
    """Amount + per-SKU quantity already invoiced against a PO by approved invoices."""
    amount = 0.0
    qty: dict[str, float] = {}
    invoices = []
    for r in all_runs():
        if r.id == exclude_run_id or r.po_number != po_number or not is_effectively_approved(r):
            continue
        amount += r.subtotal or 0.0
        for line in (r.normalized or {}).get("line_items", []):
            sku = line.get("matched_sku")
            if sku:
                qty[sku] = qty.get(sku, 0) + (line.get("quantity") or 0)
        invoices.append({"run_id": r.id, "invoice_number": r.invoice_number,
                         "date": r.invoice_date, "subtotal": r.subtotal})
    return {"amount": round(amount, 2), "qty": qty, "invoices": invoices}


def po_with_balance(po: dict) -> dict:
    c = po_consumption(po["po_number"])
    out = dict(po)
    out["invoiced_amount"] = c["amount"]
    out["remaining_amount"] = round(po["total_amount"] - c["amount"], 2)
    out["invoices"] = c["invoices"]
    out["lines"] = [
        {**l, "invoiced_qty": c["qty"].get(l["sku"], 0),
         "remaining_qty": l["quantity"] - c["qty"].get(l["sku"], 0)}
        for l in po["lines"]
    ]
    v = vendor_by_id(po["vendor_id"])
    out["vendor_name"] = v["name"] if v else po["vendor_id"]
    return out
