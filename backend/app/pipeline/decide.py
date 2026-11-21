"""Stage 9: turn rule results into one decision, a human explanation, next actions, and (if needed) a vendor email."""
from __future__ import annotations

PRIORITY = ["fraud", "reject", "request_info", "review"]
DECISION_FOR = {"fraud": "FRAUD_HOLD", "reject": "REJECT", "request_info": "REQUEST_INFO", "review": "HOLD"}


def decide(norm: dict, vendor: dict, po: dict, rules: list[dict], source: dict) -> dict:
    issues = [r for r in rules if r["status"] in ("warn", "fail")]
    by_outcome = {o: [r for r in issues if r["outcome"] == o] for o in PRIORITY}
    top = next((o for o in PRIORITY if by_outcome[o]), None)
    decision = DECISION_FOR[top] if top else "APPROVE"

    vname = vendor.get("vendor_name") or norm.get("vendor_name") or "Unknown vendor"
    amt = f"{norm.get('currency') or ''} {norm['total']:,.2f}".strip() if norm.get("total") is not None else "unknown amount"
    inv = norm.get("invoice_number") or "(no number)"
    explanation = [f"{r['id']} {r['name']}: {r['message']}" for r in issues]
    next_actions: list[str] = []
    email = None

    if decision == "APPROVE":
        headline = f"Approve {inv} from {vname} for {amt}"
        explanation = [f"All {sum(1 for r in rules if r['status'] == 'pass')} applicable checks passed."]
        if po.get("method") == "inferred":
            explanation.append(f"PO {po['po_number']} was inferred (no PO printed) — score {po['score']:.2f}.")
        explanation += [n for n in norm.get("notes", []) if "tax" in n.lower()]
        next_actions = [f"Schedule payment to account on file ({vendor.get('bank_on_file')}) per {_terms(vendor)}.",
                        f"Book against {po.get('po_number')}; remaining after this: "
                        f"{po['remaining_before'] - (norm.get('subtotal') or 0):,.2f}."]
    elif decision == "FRAUD_HOLD":
        headline = f"Fraud hold: {inv} from {vname} — payment details can't be trusted"
        next_actions = [
            "Do NOT pay and do NOT reply to the sending address — it may be compromised.",
            f"Verify by phone with the contact already on file ({vendor.get('contact_email')}), not details on this invoice.",
            "Escalate to AP manager / security; keep bank details on file unchanged until verified.",
        ]
    elif decision == "REJECT":
        headline = f"Reject {inv} from {vname}"
        r = by_outcome["reject"][0]
        if r["id"] == "R13":
            next_actions = [f"No payment — already handled in run #{r['data'].get('duplicate_run_id')}.",
                            "Notify vendor only if they chase payment."]
        elif r["id"] == "R03":
            next_actions = ["Route to procurement for vendor onboarding before any payment."]
        elif r["id"] == "R07":
            next_actions = ["Ask procurement whether a new PO should be raised; vendor must re-invoice against it."]
    elif decision == "REQUEST_INFO":
        headline = f"Need info from {vname} before {inv} can be processed"
        asks = _asks(by_outcome["request_info"], norm)
        to = source.get("from") if source.get("from") and not source.get("internal_forward") \
            and vendor.get("sender_domain_relation") == "exact" \
            else vendor.get("contact_email")
        if to:
            email = _draft(to, vname, inv, norm, asks, source)
            next_actions = [f"Review and send the drafted email to {to}.", "Invoice parked until vendor replies."]
        else:
            next_actions = ["Vendor contact unknown — AP to follow up manually."]
    else:  # HOLD
        headline = f"Hold {inv} from {vname} for review"
        next_actions = [_question(r) for r in by_outcome["review"]]
        next_actions = [q for q in next_actions if q]

    return {"decision": decision, "headline": headline, "explanation": explanation,
            "next_actions": next_actions, "email": email,
            "counts": {s: sum(1 for r in rules if r["status"] == s) for s in ("pass", "warn", "fail", "skip")}}


def _terms(vendor: dict) -> str:
    from ..master import vendor_by_id
    v = vendor_by_id(vendor.get("vendor_id", "")) or {}
    return v.get("payment_terms", "standard terms")


def _question(r: dict) -> str:
    q = {
        "R02": "Reviewer: confirm low-confidence fields against the PDF.",
        "R05": "Reviewer: confirm the vendor uses this email domain.",
        "R08": "Reviewer: confirm currency with procurement.",
        "R09": "Reviewer: price variance — approve, or ask vendor for credit note?",
        "R10": "Reviewer: billed quantity exceeds what's left on the PO — was extra work authorized?",
        "R11": "Reviewer: invoice math doesn't add up — request corrected invoice?",
        "R12": "Reviewer: PO would be overrun — approve overrun, partially pay up to PO balance, or ask for PO amendment?",
        "R14": "Reviewer: compare side-by-side with the earlier invoice — genuine new charge or resubmission?",
        "R15": "Reviewer: check the invoice date.",
        "R07": "Reviewer: PO belongs to another vendor — misquoted PO?",
    }
    return q.get(r["id"], f"Reviewer: {r['message']}")


def _asks(rules: list[dict], norm: dict) -> list[str]:
    asks = []
    for r in rules:
        if r["id"] == "R01":
            labels = {"invoice_number": "a unique invoice number", "invoice_date": "the invoice date",
                      "total": "the total amount due", "vendor_name": "your registered company name"}
            asks += [labels[m] for m in r["data"].get("missing", [])]
        if r["id"] == "R06":
            asks.append("the purchase order (PO) number this invoice relates to")
    return asks or ["a corrected invoice"]


def _draft(to: str, vname: str, inv: str, norm: dict, asks: list[str], source: dict) -> dict:
    ref = f"invoice {inv}" if norm.get("invoice_number") else "the invoice you sent"
    when = f" dated {norm['invoice_date']}" if norm.get("invoice_date") else ""
    amt = f" for {norm.get('currency')} {norm['total']:,.2f}" if norm.get("total") is not None else ""
    bullets = "\n".join(f"  • {a}" for a in asks)
    body = (f"Hello {vname} team,\n\n"
            f"Thank you for {ref}{when}{amt}. Before we can process it for payment we need:\n\n"
            f"{bullets}\n\n"
            f"Please reply with a corrected invoice (PDF) including the above. "
            f"Once received, it will be processed automatically.\n\n"
            f"Regards,\nAccounts Payable")
    subj = source.get("subject")
    subject = f"Re: {subj}" if subj else f"Information needed for {ref}"
    return {"to": to, "subject": subject, "body": body, "in_reply_to": source.get("message_id", "")}
