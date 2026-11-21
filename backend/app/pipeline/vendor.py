"""Stage 6: resolve vendor against master data, check bank details + sender domain."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from ..master import vendors
from .normalize import account_key, canonical_name

HOMOGLYPHS = str.maketrans({"1": "l", "0": "o", "3": "e", "5": "s", "|": "l"})


def _domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].strip().lower().strip(">").strip()


def _skeleton(domain: str) -> str:
    d = domain.lower().translate(HOMOGLYPHS).replace("rn", "m")
    return re.sub(r"[^a-z]", "", d.rsplit(".", 1)[0])


def domain_relation(candidate: str | None, official: str) -> str:
    """exact | lookalike | different | none"""
    if not candidate:
        return "none"
    if candidate == official or candidate.endswith("." + official):
        return "exact"
    a, b = _skeleton(candidate), _skeleton(official)
    if a == b or fuzz.ratio(a, b) >= 85:
        return "lookalike"
    return "different"


def resolve_vendor(norm: dict, sender_email: str | None) -> dict:
    name = norm.get("vendor_name_canonical", "")
    tax_id = re.sub(r"[^A-Z0-9]", "", (norm.get("vendor_tax_id") or "").upper())
    scored = []
    for v in vendors():
        names = [v["name"], *v.get("aliases", [])]
        name_score = max((fuzz.token_set_ratio(name, canonical_name(n)) for n in names), default=0) if name else 0
        evidence = []
        score = name_score
        if tax_id and tax_id == re.sub(r"[^A-Z0-9]", "", v["tax_id"].upper()):
            score = max(score, 99)
            evidence.append("tax ID matches")
        if norm.get("bank_account_key") and norm["bank_account_key"] == account_key(v["bank_account"]):
            score = max(score, 95)
            evidence.append("bank account matches")
        if name_score >= 80:
            evidence.append(f"name similarity {name_score:.0f}%")
        scored.append({"vendor": v, "score": score, "name_score": name_score, "evidence": evidence})
    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored and scored[0]["score"] >= 80 else None

    result = {
        "found": bool(best),
        "candidates": [{"id": s["vendor"]["id"], "name": s["vendor"]["name"], "score": round(s["score"])}
                       for s in scored[:3]],
    }
    if not best:
        return result

    v = best["vendor"]
    doc_domains = [_domain(e) for e in norm.get("document_emails") or []] or [_domain(norm.get("vendor_email"))]
    rels = {d: domain_relation(d, v["email_domain"]) for d in doc_domains if d}
    worst = next((d for d in rels if rels[d] == "lookalike"), None) or next((d for d in rels if rels[d] == "different"), None)
    inv_domain = worst or (doc_domains[0] if doc_domains else None)
    snd_domain = _domain(sender_email)
    master_key = account_key(v["bank_account"])
    inv_key = norm.get("bank_account_key") or ""
    if not inv_key:
        bank = "missing"
    elif inv_key == master_key or (len(inv_key) >= 8 and master_key.endswith(inv_key)):
        bank = "match"
    else:
        bank = "mismatch"

    result.update({
        "vendor_id": v["id"],
        "vendor_name": v["name"],
        "status": v["status"],
        "score": round(best["score"]),
        "evidence": best["evidence"],
        "official_domain": v["email_domain"],
        "invoice_email_domain": inv_domain,
        "invoice_domain_relation": domain_relation(inv_domain, v["email_domain"]),
        "sender_domain": snd_domain,
        "sender_domain_relation": domain_relation(snd_domain, v["email_domain"]),
        "bank_status": bank,
        "bank_on_file": _mask(v["bank_account"]),
        "bank_on_invoice": _mask(norm.get("bank_account") or ""),
        "bank_change_notice": norm.get("bank_change_notice", False),
        "contact_email": v["contact_email"],
        "currency": v["currency"],
    })
    return result


def _mask(acct: str) -> str:
    k = account_key(acct)
    return f"••••{k[-4:]}" if len(k) > 4 else k
