"""Stage 7: find the purchase order (explicit or inferred) and match invoice lines to PO lines."""
from __future__ import annotations

from rapidfuzz import fuzz

from ..master import po_by_number, po_consumption, purchase_orders


def match_po(norm: dict, vendor: dict, run_id: int | None) -> dict:
    vendor_id = vendor.get("vendor_id")
    explicit = norm.get("po_number")
    if explicit:
        po = po_by_number(explicit)
        if po:
            return _with_lines(po, norm, run_id, method="explicit", score=1.0,
                               reason=f"PO number {explicit} printed on invoice.")
        result = {"found": False, "method": "explicit", "printed_po": explicit,
                  "reason": f"Printed PO {explicit} does not exist in procurement system."}
        inferred = _infer(norm, vendor_id, run_id)
        if inferred.get("found"):
            inferred["printed_po"] = explicit
            inferred["reason"] = (f"Printed PO {explicit} not found; best candidate inferred: "
                                  f"{inferred['po_number']}. " + inferred["reason"])
            inferred["method"] = "inferred"
            return inferred
        return result
    return _infer(norm, vendor_id, run_id)


def _infer(norm: dict, vendor_id: str | None, run_id: int | None) -> dict:
    if not vendor_id:
        return {"found": False, "method": "none", "reason": "No PO printed and vendor unknown."}
    candidates = [p for p in purchase_orders() if p["vendor_id"] == vendor_id and p["status"] == "open"]
    if not candidates:
        return {"found": False, "method": "inferred", "reason": "Vendor has no open purchase orders."}

    scored = []
    for po in candidates:
        lm = match_lines(norm["line_items"], po)
        line_score = sum(m["score"] for m in lm) / len(lm) if lm else 0
        cons = po_consumption(po["po_number"], exclude_run_id=run_id)
        remaining = po["total_amount"] - cons["amount"]
        sub = norm.get("subtotal") or 0
        if sub and remaining > 0:
            amount_fit = 1.0 if sub <= remaining * 1.02 else max(0.0, 1 - (sub - remaining) / remaining)
        else:
            amount_fit = 0.0
        price_fit = sum(1 for m in lm if m.get("price_delta_pct") is not None and abs(m["price_delta_pct"]) <= 2) / len(lm) if lm else 0
        total = 0.55 * line_score + 0.25 * price_fit + 0.20 * amount_fit
        scored.append({"po": po, "score": round(total, 3), "line_score": round(line_score, 3),
                       "price_fit": round(price_fit, 3), "amount_fit": round(amount_fit, 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0]
    cand_view = [{"po_number": s["po"]["po_number"], "score": s["score"], "line_score": s["line_score"],
                  "price_fit": s["price_fit"], "amount_fit": s["amount_fit"]} for s in scored]
    from ..config import PO_INFER_THRESHOLD
    margin = best["score"] - (scored[1]["score"] if len(scored) > 1 else 0)
    if best["score"] < PO_INFER_THRESHOLD:
        return {"found": False, "method": "inferred", "candidates": cand_view,
                "reason": f"No PO printed; best candidate {best['po']['po_number']} scored "
                          f"{best['score']:.2f} (< {PO_INFER_THRESHOLD})."}
    out = _with_lines(best["po"], norm, run_id, method="inferred", score=best["score"],
                      reason=f"No PO printed. Inferred {best['po']['po_number']} from line items "
                             f"({best['line_score']:.0%} description match), unit prices and remaining "
                             f"balance; margin over next candidate {margin:.2f}.")
    out["candidates"] = cand_view
    return out


def _with_lines(po: dict, norm: dict, run_id: int | None, method: str, score: float, reason: str) -> dict:
    cons = po_consumption(po["po_number"], exclude_run_id=run_id)
    return {
        "found": True, "method": method, "score": round(score, 3), "reason": reason,
        "po_number": po["po_number"], "po_vendor_id": po["vendor_id"], "po_status": po["status"],
        "po_currency": po["currency"], "po_total": po["total_amount"],
        "previously_invoiced": cons["amount"], "previous_invoices": cons["invoices"],
        "remaining_before": round(po["total_amount"] - cons["amount"], 2),
        "lines": match_lines(norm["line_items"], po, cons["qty"]),
    }


def match_lines(items: list[dict], po: dict, consumed_qty: dict | None = None) -> list[dict]:
    consumed_qty = consumed_qty or {}
    out = []
    for li in items:
        best, best_score = None, 0.0
        for pl in po["lines"]:
            if li.get("sku") and str(li["sku"]).strip().upper() == pl["sku"]:
                s = 100.0
            else:
                s = fuzz.token_set_ratio((li.get("description") or "").lower(), pl["description"].lower())
            if s > best_score:
                best, best_score = pl, s
        m = {"description": li.get("description"), "quantity": li.get("quantity"),
             "unit_price": li.get("unit_price"), "amount": li.get("amount"),
             "score": round(best_score / 100, 3)}
        if best and best_score >= 60:
            li["matched_sku"] = best["sku"]
            remaining_qty = best["quantity"] - consumed_qty.get(best["sku"], 0)
            delta = None
            if li.get("unit_price") is not None and best["unit_price"]:
                delta = round((li["unit_price"] - best["unit_price"]) / best["unit_price"] * 100, 2)
            m.update({"po_sku": best["sku"], "po_description": best["description"],
                      "po_unit_price": best["unit_price"], "po_quantity": best["quantity"],
                      "remaining_qty": remaining_qty, "price_delta_pct": delta})
        else:
            li["matched_sku"] = None
        out.append(m)
    return out
