"""Stage 5: normalize extracted values (amounts, dates, currency, tax) and ground them in source text."""
from __future__ import annotations

import re
from datetime import date

from dateutil import parser as dparser
from rapidfuzz import fuzz

CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "₹": "INR", "US$": "USD"}
DAYFIRST_CURRENCIES = {"EUR", "GBP", "INR"}
OWN_EMAILS = {"ap@meridian-retail.com"}  # our own bill-to address, never the vendor's
LEGAL_SUFFIXES = r"\b(inc|incorporated|llc|ltd|limited|gmbh|ag|co|corp|corporation|company|plc|pvt|private|sa|bv|srl)\b\.?"


def parse_amount(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:  # 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_date(raw, dayfirst: bool) -> dict:
    if not raw:
        return {"iso": None, "ambiguous": False}
    s = str(raw).strip()
    try:
        d = dparser.parse(s, dayfirst=dayfirst, fuzzy=True).date()
    except (ValueError, OverflowError):
        return {"iso": None, "ambiguous": False, "raw": s}
    nums = re.findall(r"\d+", s)
    ambiguous = (len(nums) >= 2 and not re.search(r"[A-Za-z]", s)
                 and int(nums[0]) <= 12 and int(nums[1]) <= 12 and nums[0] != nums[1]
                 and len(nums[0]) <= 2)
    return {"iso": d.isoformat(), "ambiguous": ambiguous, "raw": s}


def normalize_currency(v, fallback: str | None) -> str | None:
    if not v:
        return fallback
    s = str(v).strip().upper()
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in s:
            return code
    m = re.search(r"[A-Z]{3}", s)
    return m.group(0) if m else fallback


def canonical_name(name: str | None) -> str:
    if not name:
        return ""
    s = name.lower().replace("&", " and ")
    s = re.sub(LEGAL_SUFFIXES, " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def account_key(v: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (v or "").upper())


def normalize(ext: dict, source_text: str, vendor_currency_hint: str | None = None) -> dict:
    notes: list[str] = []
    currency = normalize_currency(ext.get("currency"), vendor_currency_hint)
    if not ext.get("currency") and currency:
        notes.append(f"Currency not printed; assumed {currency} from vendor master.")
    dayfirst = currency in DAYFIRST_CURRENCIES

    inv_date = parse_date(ext.get("invoice_date"), dayfirst)
    due_date = parse_date(ext.get("due_date"), dayfirst)
    if inv_date.get("ambiguous"):
        notes.append(f"Date '{inv_date['raw']}' is ambiguous (DD/MM vs MM/DD); read as "
                     f"{'day-first' if dayfirst else 'month-first'} based on currency {currency}.")

    tax_rate = parse_amount(ext.get("tax_rate"))
    tax_amount = parse_amount(ext.get("tax_amount"))
    total = parse_amount(ext.get("total"))
    subtotal = parse_amount(ext.get("subtotal"))
    inclusive = bool(ext.get("tax_inclusive"))

    lines = []
    for li in ext.get("line_items", []):
        q = parse_amount(li.get("quantity"))
        up = parse_amount(li.get("unit_price"))
        amt = parse_amount(li.get("amount"))
        if amt is None and q is not None and up is not None:
            amt = round(q * up, 2)
        if up is None and amt is not None and q:
            up = round(amt / q, 2)
        lines.append({"description": (li.get("description") or "").strip(), "sku": li.get("sku"),
                      "quantity": q, "unit_price": up, "amount": amt})
    lines_sum = round(sum(l["amount"] or 0 for l in lines), 2)

    # ---- tax handling: always produce a NET subtotal comparable to PO prices
    if inclusive:
        gross = total if total is not None else lines_sum
        if tax_amount is None and tax_rate:
            tax_amount = round(gross - gross / (1 + tax_rate / 100), 2)
        net = round(gross - (tax_amount or 0), 2)
        factor = net / gross if gross else 1
        for l in lines:
            l["gross_unit_price"], l["gross_amount"] = l["unit_price"], l["amount"]
            if l["unit_price"] is not None:
                l["unit_price"] = round(l["unit_price"] * factor, 2)
            if l["amount"] is not None:
                l["amount"] = round(l["amount"] * factor, 2)
        notes.append(f"Prices include tax ({tax_rate or '?'}%). Derived net subtotal {net:,.2f} "
                     f"by removing embedded tax {tax_amount or 0:,.2f}.")
        subtotal, total = net, gross
    else:
        if subtotal is None:
            subtotal = lines_sum if lines else (round(total - (tax_amount or 0), 2) if total is not None else None)
            if subtotal is not None:
                notes.append("Subtotal not printed; computed from line items.")
        if tax_amount is None and subtotal is not None and total is not None:
            tax_amount = round(total - subtotal, 2)
        if total is None and subtotal is not None:
            total = round(subtotal + (tax_amount or 0), 2)
            notes.append("Total not printed; computed as subtotal + tax.")

    # ---- grounding: are critical values actually present in the document text?
    grounding = ground(ext, source_text, total)
    confidence = dict(ext.get("confidence") or {})
    for field, ok in grounding.items():
        if ok is False and confidence.get(field, 0) > 0.4:
            confidence[field] = 0.4
            notes.append(f"'{field}' value could not be located in the document text; confidence lowered.")

    # emails taken verbatim from the document text (LLMs may silently "fix" typo-squatted domains)
    doc_emails = sorted({e.lower().rstrip(".") for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", source_text or "")}
                        - {e for e in OWN_EMAILS})
    llm_email = (ext.get("vendor_email") or "").lower() or None
    if llm_email and doc_emails and llm_email not in doc_emails:
        notes.append(f"Extractor returned '{llm_email}' but document text shows {', '.join(doc_emails)}; using document text.")
        llm_email = doc_emails[0]

    return {
        "vendor_name": ext.get("vendor_name"),
        "document_emails": doc_emails,
        "vendor_name_canonical": canonical_name(ext.get("vendor_name")),
        "vendor_email": llm_email or (doc_emails[0] if doc_emails else None),
        "vendor_tax_id": ext.get("vendor_tax_id"),
        "invoice_number": (ext.get("invoice_number") or "").strip() or None,
        "invoice_date": inv_date.get("iso"),
        "invoice_date_ambiguous": inv_date.get("ambiguous", False),
        "due_date": due_date.get("iso"),
        "po_number": normalize_po(ext.get("po_number")),
        "order_reference_hint": ext.get("order_reference_hint"),
        "currency": currency,
        "bank_name": ext.get("bank_name"),
        "bank_account": ext.get("bank_account"),
        "bank_account_key": account_key(ext.get("bank_account")),
        "bank_change_notice": ext.get("bank_change_notice", False),
        "line_items": lines,
        "lines_sum": lines_sum,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "tax_inclusive": inclusive,
        "total": total,
        "confidence": confidence,
        "grounding": grounding,
        "notes": notes,
    }


def normalize_po(v) -> str | None:
    if not v:
        return None
    s = str(v).upper().replace(" ", "")
    s = re.sub(r"^P[O0]", "PO", s)  # OCR: P0-1003 -> PO-1003
    m = re.search(r"(\d{3,6})", s)
    return f"PO-{m.group(1)}" if m else s


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def ground(ext: dict, text: str, total: float | None) -> dict:
    t = _norm_text(text)
    if not t:
        return {}
    res: dict = {}
    for f in ("invoice_number", "po_number", "vendor_email"):
        v = ext.get(f)
        if v:
            needle = _norm_text(str(v))
            res[f] = needle in t or fuzz.partial_ratio(needle, t) >= 90
    acct = account_key(ext.get("bank_account"))
    if acct:
        tt = account_key(text)
        tail = acct[-6:]
        res["bank_account"] = tail in tt
    if total is not None:
        variants = {f"{total:,.2f}", f"{total:.2f}", f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}
        res["total"] = any(_norm_text(v) in t for v in variants)
    return res


def days_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
