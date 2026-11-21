"""Stage 8: deterministic validation rules. Each rule is explainable and has a fixed outcome class.

status:  pass | warn | fail | skip
outcome (for non-pass): fraud | reject | request_info | review
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .. import config
from ..db import all_runs
from ..master import is_effectively_approved
from .normalize import days_between

CRITICAL_FIELDS = ("invoice_number", "invoice_date", "total")


def _r(rid, name, status, message, outcome=None, **data):
    return {"id": rid, "name": name, "status": status, "outcome": outcome if status in ("warn", "fail") else None,
            "message": message, "data": data}


def _key(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def run_rules(run_id: int, file_hash: str, norm: dict, vendor: dict, po: dict) -> list[dict]:
    R = []
    tol_price = config.PRICE_TOLERANCE_PCT
    tol_amt = config.AMOUNT_TOLERANCE_PCT

    # R01 required fields
    missing = [f for f in ("vendor_name", "invoice_number", "invoice_date", "total") if not norm.get(f)]
    R.append(_r("R01", "Required fields present",
                "fail" if missing else "pass",
                f"Missing: {', '.join(missing)}." if missing else "Vendor, invoice number, date and total all present.",
                "request_info", missing=missing))

    # R02 extraction confidence
    conf = norm.get("confidence", {})
    low = {f: conf.get(f, 0) for f in CRITICAL_FIELDS if norm.get(f) and conf.get(f, 0) < config.CONFIDENCE_THRESHOLD}
    R.append(_r("R02", "Extraction confidence",
                "warn" if low else "pass",
                ("Low confidence on " + ", ".join(f"{k} ({v:.0%})" for k, v in low.items()) + "; needs a human glance.")
                if low else f"All critical fields read with ≥{config.CONFIDENCE_THRESHOLD:.0%} confidence.",
                "review", low_fields=low))

    # R03 vendor approved
    if not vendor.get("found"):
        R.append(_r("R03", "Approved vendor", "fail",
                    f"'{norm.get('vendor_name') or 'Unknown'}' is not in the approved vendor master.",
                    "reject", candidates=vendor.get("candidates")))
    elif vendor.get("status") != "active":
        R.append(_r("R03", "Approved vendor", "fail",
                    f"{vendor['vendor_name']} exists but is {vendor['status']}; payments blocked.", "reject"))
    else:
        R.append(_r("R03", "Approved vendor", "pass",
                    f"Matched {vendor['vendor_name']} ({vendor['vendor_id']}) — {', '.join(vendor['evidence']) or 'name match'}."))

    # R04 bank details
    bs = vendor.get("bank_status")
    if not vendor.get("found"):
        R.append(_r("R04", "Bank details match master", "skip", "Vendor unknown."))
    elif bs == "mismatch":
        R.append(_r("R04", "Bank details match master", "fail",
                    f"Invoice asks for payment to {vendor['bank_on_invoice']} but account on file is "
                    f"{vendor['bank_on_file']}." + (" Invoice announces 'new bank details'." if vendor.get("bank_change_notice") else ""),
                    "fraud", on_file=vendor["bank_on_file"], on_invoice=vendor["bank_on_invoice"]))
    elif bs == "missing":
        R.append(_r("R04", "Bank details match master", "pass",
                    f"No bank details printed; payment will go to account on file {vendor['bank_on_file']}."))
    else:
        R.append(_r("R04", "Bank details match master", "pass",
                    f"Bank account {vendor['bank_on_file']} matches vendor master."))

    # R05 sender / invoice email domain
    if vendor.get("found"):
        rel = {vendor.get("sender_domain_relation"), vendor.get("invoice_domain_relation")}
        doms = ", ".join(d for d in {vendor.get("sender_domain"), vendor.get("invoice_email_domain")} if d)
        if "lookalike" in rel:
            R.append(_r("R05", "Sender domain authentic", "fail",
                        f"Domain {doms} imitates the vendor's real domain {vendor['official_domain']}.",
                        "fraud", seen=doms, official=vendor["official_domain"]))
        elif "different" in rel:
            R.append(_r("R05", "Sender domain authentic", "warn",
                        f"Domain {doms} differs from vendor domain {vendor['official_domain']}.",
                        "review", seen=doms, official=vendor["official_domain"]))
        elif rel == {"none"}:
            R.append(_r("R05", "Sender domain authentic", "skip", "No sender or invoice email to verify."))
        else:
            R.append(_r("R05", "Sender domain authentic", "pass", f"Domain matches {vendor['official_domain']}."))
    else:
        R.append(_r("R05", "Sender domain authentic", "skip", "Vendor unknown."))

    # R06 PO found
    if po.get("found"):
        R.append(_r("R06", "Purchase order identified", "pass", po["reason"], method=po["method"],
                    score=po.get("score")))
    else:
        R.append(_r("R06", "Purchase order identified", "fail" if vendor.get("found") else "skip",
                    po.get("reason", "No PO."), "request_info", candidates=po.get("candidates")))

    po_ok = po.get("found")
    # R07 PO open & belongs to vendor
    if po_ok:
        if po["po_status"] != "open":
            R.append(_r("R07", "PO open and owned by vendor", "fail",
                        f"{po['po_number']} is {po['po_status']}; cannot invoice against it.", "reject"))
        elif vendor.get("vendor_id") and po["po_vendor_id"] != vendor["vendor_id"]:
            R.append(_r("R07", "PO open and owned by vendor", "fail",
                        f"{po['po_number']} belongs to a different vendor ({po['po_vendor_id']}).", "review"))
        else:
            R.append(_r("R07", "PO open and owned by vendor", "pass", f"{po['po_number']} is open for this vendor."))
    else:
        R.append(_r("R07", "PO open and owned by vendor", "skip", "No PO."))

    # R08 currency
    if po_ok:
        same = norm.get("currency") == po["po_currency"]
        R.append(_r("R08", "Currency matches PO", "pass" if same else "warn",
                    f"Invoice in {norm.get('currency')}, PO in {po['po_currency']}.", "review"))
    else:
        R.append(_r("R08", "Currency matches PO", "skip", "No PO."))

    # R09 unit prices / R10 quantities
    if po_ok:
        lines = po["lines"]
        unmatched = [l for l in lines if not l.get("po_sku")]
        off_price = [l for l in lines if l.get("price_delta_pct") is not None and abs(l["price_delta_pct"]) > tol_price]
        if unmatched or off_price:
            msg = []
            if off_price:
                msg.append("; ".join(f"'{l['description']}' {l['unit_price']:,.2f} vs PO {l['po_unit_price']:,.2f} "
                                     f"({l['price_delta_pct']:+.1f}%)" for l in off_price))
            if unmatched:
                msg.append(f"{len(unmatched)} line(s) not on PO: " + ", ".join(f"'{l['description']}'" for l in unmatched))
            R.append(_r("R09", f"Unit prices within ±{tol_price:g}%", "warn", " | ".join(msg), "review",
                        off_price=off_price, unmatched=unmatched))
        else:
            R.append(_r("R09", f"Unit prices within ±{tol_price:g}%", "pass",
                        f"All {len(lines)} line(s) match PO prices."))
        over_qty = [l for l in lines if l.get("po_sku") and l.get("quantity") is not None
                    and l["quantity"] > l["remaining_qty"] + 1e-9]
        if over_qty:
            R.append(_r("R10", "Quantities within remaining PO quantity", "warn",
                        "; ".join(f"'{l['po_description']}' billed {l['quantity']:g}, only {l['remaining_qty']:g} "
                                  f"remaining of {l['po_quantity']:g}" for l in over_qty), "review", lines=over_qty))
        else:
            R.append(_r("R10", "Quantities within remaining PO quantity", "pass", "All quantities within remaining PO quantity."))
    else:
        R.append(_r("R09", f"Unit prices within ±{tol_price:g}%", "skip", "No PO."))
        R.append(_r("R10", "Quantities within remaining PO quantity", "skip", "No PO."))

    # R11 arithmetic
    issues = []
    if norm["line_items"] and norm.get("subtotal") is not None and not norm.get("tax_inclusive"):
        if abs(norm["lines_sum"] - norm["subtotal"]) > max(0.05, 0.005 * norm["subtotal"]):
            issues.append(f"line items sum to {norm['lines_sum']:,.2f} but subtotal says {norm['subtotal']:,.2f}")
    if None not in (norm.get("subtotal"), norm.get("total")):
        exp = round(norm["subtotal"] + (norm.get("tax_amount") or 0), 2)
        if abs(exp - norm["total"]) > 0.05:
            issues.append(f"subtotal + tax = {exp:,.2f} but total says {norm['total']:,.2f}")
    if norm.get("tax_rate") and norm.get("subtotal") and norm.get("tax_amount") is not None:
        exp_tax = round(norm["subtotal"] * norm["tax_rate"] / 100, 2)
        if abs(exp_tax - norm["tax_amount"]) > max(0.1, 0.01 * exp_tax):
            issues.append(f"tax {norm['tax_amount']:,.2f} ≠ {norm['tax_rate']:g}% of subtotal ({exp_tax:,.2f})")
    R.append(_r("R11", "Invoice arithmetic", "warn" if issues else "pass",
                "; ".join(issues) if issues else "Lines, subtotal, tax and total reconcile.", "review"))

    # R12 cumulative PO balance (split invoices)
    if po_ok and norm.get("subtotal") is not None:
        prev = po["previously_invoiced"]
        after = round(prev + norm["subtotal"], 2)
        cap = po["po_total"] * (1 + tol_amt / 100)
        over = round(after - po["po_total"], 2)
        n_prev = len(po["previous_invoices"])
        data = dict(po_total=po["po_total"], previously_invoiced=prev, this_invoice=norm["subtotal"],
                    after=after, overrun=max(0, over), previous_invoices=po["previous_invoices"])
        if after > cap + 0.01:
            R.append(_r("R12", "PO balance not exceeded", "warn",
                        f"With {n_prev} earlier invoice(s) ({prev:,.2f}) this brings {po['po_number']} to {after:,.2f} — "
                        f"{over:,.2f} ({over / po['po_total']:.1%}) over the PO value {po['po_total']:,.2f} "
                        f"(tolerance {tol_amt:g}%).", "review", **data))
        else:
            note = f" Within {tol_amt:g}% tolerance (+{over:,.2f})." if over > 0 else ""
            R.append(_r("R12", "PO balance not exceeded", "pass",
                        f"{po['po_number']}: {prev:,.2f} already invoiced ({n_prev} invoice(s)); after this "
                        f"{after:,.2f} of {po['po_total']:,.2f}.{note}", **data))
    else:
        R.append(_r("R12", "PO balance not exceeded", "skip", "No PO or subtotal."))

    # R13 / R14 duplicates
    others = [r for r in all_runs() if r.id != run_id and r.status == "done"
              and r.decision not in ("REJECT",) and r.review_status != "rejected"]
    same_file = [r for r in others if file_hash and r.file_hash == file_hash]
    inv_key = _key(norm.get("invoice_number"))
    exact = [r for r in others if inv_key and _key(r.invoice_number) == inv_key
             and (r.vendor_id == vendor.get("vendor_id") or not vendor.get("vendor_id"))]
    dup = (same_file or exact)
    if dup:
        d = dup[0]
        why = "identical file" if same_file else f"same vendor + invoice number {norm['invoice_number']}"
        R.append(_r("R13", "Not an exact duplicate", "fail",
                    f"Duplicate of run #{d.id} ({why}, {d.decision.replace('_', ' ').lower() or 'processed'} "
                    f"{d.created_at:%d %b}).", "reject", duplicate_run_id=d.id))
    else:
        R.append(_r("R13", "Not an exact duplicate", "pass", "No prior invoice with this number from this vendor."))

    near = []
    if vendor.get("vendor_id") and norm.get("total") is not None and not dup:
        for r in others:
            if r.vendor_id != vendor["vendor_id"] or not r.total or _key(r.invoice_number) == inv_key:
                continue
            amt_diff = abs(r.total - norm["total"]) / max(r.total, 1) * 100
            dd = days_between(r.invoice_date, norm.get("invoice_date"))
            if amt_diff <= config.FUZZY_DUP_AMOUNT_PCT and (dd is None or dd <= config.FUZZY_DUP_DAYS):
                sim_lines = _line_overlap(r.normalized.get("line_items", []), norm["line_items"])
                near.append({"run_id": r.id, "invoice_number": r.invoice_number, "date": r.invoice_date,
                             "total": r.total, "amount_diff_pct": round(amt_diff, 2), "days_apart": dd,
                             "line_overlap": sim_lines})
    if near:
        n = near[0]
        R.append(_r("R14", "Not a near-duplicate", "warn",
                    f"Looks like a resubmission of {n['invoice_number']} (run #{n['run_id']}): same vendor, "
                    f"amount within {n['amount_diff_pct']:g}%, {n['days_apart']} days apart, "
                    f"{n['line_overlap']:.0%} line-item overlap — but a different invoice number.",
                    "review", matches=near))
    else:
        R.append(_r("R14", "Not a near-duplicate", "pass" if not dup else "skip",
                    "No similar invoice (amount ±1%, 14 days) from this vendor." if not dup else "Exact duplicate already found."))

    # R15 date sanity
    d = norm.get("invoice_date")
    if d:
        dd = date.fromisoformat(d)
        today = date.today()
        if dd > today + timedelta(days=1):
            R.append(_r("R15", "Invoice date plausible", "warn", f"Invoice dated in the future ({d}).", "review"))
        elif (today - dd).days > config.MAX_INVOICE_AGE_DAYS:
            R.append(_r("R15", "Invoice date plausible", "warn",
                        f"Invoice is {(today - dd).days} days old (> {config.MAX_INVOICE_AGE_DAYS}).", "review"))
        else:
            amb = " (date format was ambiguous; interpreted by locale)" if norm.get("invoice_date_ambiguous") else ""
            R.append(_r("R15", "Invoice date plausible", "pass", f"Dated {d}{amb}."))
    else:
        R.append(_r("R15", "Invoice date plausible", "skip", "No date."))

    # R16 approval limit (policy, not a data problem)
    R.append(approval_limit_rule(norm.get("total"), norm.get("currency")))
    return R


def usd_equivalent(amount, currency) -> float | None:
    rate = config.FX_TO_USD.get((currency or "").upper())
    if amount is None or rate is None:
        return None
    return round(amount * rate, 2)


def approval_limit_rule(total, currency) -> dict:
    limit = config.APPROVAL_LIMIT_USD
    name = f"Within auto-approval limit (USD {limit:,.0f})"
    if total is None:
        return _r("R16", name, "skip", "No total.")
    usd = usd_equivalent(total, currency)
    if usd is None:
        return _r("R16", name, "warn", f"No FX rate for {currency}; cannot check the limit, so approval is required.",
                  "approval", limit_usd=limit)
    conv = "" if (currency or "").upper() == "USD" else f" (≈ USD {usd:,.2f})"
    if usd > limit:
        return _r("R16", name, "warn",
                  f"{currency} {total:,.2f}{conv} is above the USD {limit:,.0f} auto-approval limit — "
                  f"a finance manager must approve.", "approval", usd=usd, limit_usd=limit)
    return _r("R16", name, "pass", f"{currency} {total:,.2f}{conv} is within the USD {limit:,.0f} limit.",
              usd=usd, limit_usd=limit)


def _line_overlap(a: list, b: list) -> float:
    from rapidfuzz import fuzz
    if not a or not b:
        return 0.0
    hits = sum(1 for x in b if any(fuzz.token_set_ratio(x.get("description", ""), y.get("description", "")) >= 85 for y in a))
    return hits / len(b)
