"""Stage 4: turn raw document into structured invoice fields.

Extractor chain (first that succeeds wins):  Gemini -> local Ollama vision -> regex heuristics.
LLMs only *read* the document. Every decision downstream is made by deterministic rules.
"""
from __future__ import annotations

import base64
import json
import re
import time

import httpx

from .. import config

FIELDS_TEMPLATE = {
    "vendor_name": "string|null",
    "vendor_address": "string|null",
    "vendor_email": "string|null",
    "vendor_tax_id": "string|null",
    "invoice_number": "string|null",
    "invoice_date": "string|null  (exactly as printed)",
    "due_date": "string|null",
    "po_number": "string|null  (ONLY if a purchase order number is explicitly printed)",
    "order_reference_hint": "string|null  (any other order/contract/project reference text)",
    "currency": "string|null  (ISO code like USD/EUR or the symbol printed)",
    "bank_name": "string|null",
    "bank_account": "string|null  (IBAN as printed; for US style write '<routing>-<account>')",
    "bank_change_notice": "boolean  (true if the document says bank/payment details changed)",
    "line_items": [{"description": "string", "sku": "string|null", "quantity": "number|null",
                    "unit_price": "number|null", "amount": "number|null"}],
    "subtotal": "number|null",
    "tax_rate": "number|null  (percent, e.g. 19)",
    "tax_amount": "number|null",
    "tax_inclusive": "boolean  (true if prices/total are stated as including tax, e.g. 'incl. VAT', 'inkl. MwSt')",
    "total": "number|null",
    "notes": "string|null",
    "confidence": {"vendor_name": "0-1", "invoice_number": "0-1", "invoice_date": "0-1",
                   "total": "0-1", "po_number": "0-1", "bank_account": "0-1", "line_items": "0-1"},
}

PROMPT = f"""You are the extraction step of an accounts-payable system.
Read the attached vendor invoice and return ONE JSON object with exactly this shape:
{json.dumps(FIELDS_TEMPLATE, indent=1)}

Rules:
- Copy values only from the document. Never invent or infer missing values; use null.
- Amounts are plain numbers (convert "4.938,50" to 4938.50, drop currency symbols).
- Line item amounts are the printed line totals.
- confidence = how certain you are the value is printed and read correctly (1 = certain, 0 = absent/guess).
- If a field is missing, its confidence must be 0.
Return JSON only."""


class ExtractionError(Exception):
    pass


def extract(doc: dict, pdf_bytes: bytes, pages_png: list[bytes], file_hash: str = "") -> dict:
    """Returns {"data": {...}, "extractor": name, "attempts": [...]}"""
    attempts = []
    chain = []
    if config.GEMINI_API_KEY:
        for model in config.GEMINI_MODELS:
            chain.append((model, lambda d, b, p, m=model: _gemini(d, b, p, m)))
        chain.append(("cache", lambda d, b, p: _cache_get(file_hash)))
    chain.append(("ollama", _ollama))
    chain.append(("regex", _regex))

    for name, fn in chain:
        t0 = time.time()
        try:
            data = fn(doc, pdf_bytes, pages_png)
            data = coerce(data)
            attempts.append({"extractor": name, "ok": True, "ms": int((time.time() - t0) * 1000)})
            if name.startswith("gemini") and file_hash:
                _cache_put(file_hash, data)
            return {"data": data, "extractor": name, "attempts": attempts}
        except Exception as e:  # noqa: BLE001 - fall through to next extractor
            attempts.append({"extractor": name, "ok": False, "error": str(e)[:300],
                             "ms": int((time.time() - t0) * 1000)})
    raise ExtractionError(f"All extractors failed: {attempts}")


# ---------------------------------------------------------------- Gemini
def _gemini(doc: dict, pdf_bytes: bytes, pages_png: list[bytes], model: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY,
                          http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_S * 1000))
    parts: list = []
    if doc["doc_type"] == "scanned":
        parts += [types.Part.from_bytes(data=p, mime_type="image/png") for p in pages_png]
        parts.append(f"Local OCR text of the scan (may contain OCR errors):\n{doc.get('ocr_text', '')[:6000]}")
    else:
        parts.append(types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"))
    parts.append(PROMPT)

    base = dict(response_mime_type="application/json", temperature=0)
    configs = [types.GenerateContentConfig(**base)]
    if "2.5" in model:  # 2.5 models think by default; turning it off makes extraction ~3x faster
        configs.insert(0, types.GenerateContentConfig(**base, thinking_config=types.ThinkingConfig(thinking_budget=0)))

    last: Exception | None = None
    for attempt, cfg in enumerate(configs + configs[-1:]):  # last config gets one retry for transient 503s
        try:
            resp = client.models.generate_content(model=model, contents=parts, config=cfg)
            return _parse_json(resp.text or "")
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e)
            if "429" in msg or "404" in msg or "NOT_FOUND" in msg:
                raise  # quota / retired model: move to the next model immediately
            if "503" in msg or "UNAVAILABLE" in msg:
                time.sleep(2)
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------- Ollama (local)
def _ollama(doc: dict, pdf_bytes: bytes, pages_png: list[bytes]) -> dict:
    with httpx.Client(timeout=httpx.Timeout(120, connect=1.5)) as c:
        tags = c.get(f"{config.OLLAMA_URL}/api/tags").json()
        names = {m["name"] for m in tags.get("models", [])}
        if config.OLLAMA_MODEL not in names and f"{config.OLLAMA_MODEL}:latest" not in names:
            raise ExtractionError(f"ollama model {config.OLLAMA_MODEL} not pulled")
        text = doc.get("ocr_text") or doc.get("text") or ""
        msg = {"role": "user",
               "content": f"{PROMPT}\n\nDocument text:\n{text[:6000]}",
               "images": [base64.b64encode(p).decode() for p in pages_png[:1]]}
        r = c.post(f"{config.OLLAMA_URL}/api/chat", json={
            "model": config.OLLAMA_MODEL, "messages": [msg], "format": "json",
            "stream": False, "options": {"temperature": 0}})
        r.raise_for_status()
        return _parse_json(r.json()["message"]["content"])


# ---------------------------------------------------------------- Regex heuristics
_NUM = r"([€$£]?\s?-?[\d.,]+\d)"


def _find(pattern: str, text: str, flags=re.I) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _regex(doc: dict, pdf_bytes: bytes, pages_png: list[bytes]) -> dict:
    text = doc.get("ocr_text") or doc.get("text") or ""
    if len(text) < 30:
        raise ExtractionError("no text to parse")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    inv = _find(r"invoice\s*(?:no\.?|number|#|nr\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,})", text) \
        or _find(r"rechnungs?(?:nummer|nr\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,})", text)
    date = _find(r"(?:invoice\s*date|date\s*of\s*issue|rechnungsdatum|issued)\s*[:]?\s*([0-9A-Za-z ,./\-]{6,20}\d)", text)
    po = _find(r"\b(P[O0]-?\s?\d{3,6})\b", text)
    total = _find(r"(?:total\s*due|amount\s*due|grand\s*total|gesamtbetrag|total)\s*(?:\(?[A-Z]{3}\)?)?\s*[:]?\s*" + _NUM, text)
    subtotal = _find(r"(?:subtotal|net\s*amount|nettobetrag)\s*[:]?\s*" + _NUM, text)
    tax = _find(r"(?:sales\s*tax|vat|tax|mwst\.?)[^\n\d]{0,20}?(?:\d{1,2}(?:[.,]\d+)?\s*%)?\s*[:]?\s*" + _NUM, text)
    rate = _find(r"(\d{1,2}(?:[.,]\d+)?)\s*%", text)
    iban = _find(r"\b([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?)\b", text, 0)
    routing = _find(r"routing[^\d]{0,15}(\d{9})", text)
    acct = _find(r"account\s*(?:no\.?|number|#)?[^\d]{0,5}(\d{6,17})", text)
    email = _find(r"([\w.+-]+@[\w-]+\.[\w.-]+)", text)
    currency = "EUR" if "€" in text or "EUR" in text else "GBP" if "£" in text else "USD" if "$" in text or "USD" in text else None

    items = []
    row = re.compile(r"^(.*?[A-Za-z].*?)\s+(\d+(?:[.,]\d+)?)\s+[€$£]?\s?([\d.,]+\d)\s+[€$£]?\s?([\d.,]+\d)$")
    for l in lines:
        m = row.match(l)
        if m and not re.search(r"total|subtotal|tax|vat|balance", m.group(1), re.I):
            items.append({"description": m.group(1).strip(), "sku": None,
                          "quantity": m.group(2), "unit_price": m.group(3), "amount": m.group(4)})

    bank_account = iban or (f"{routing}-{acct}" if routing and acct else acct)
    vendor_name = lines[0] if lines else None
    c = lambda v, hi=0.6: hi if v else 0.0  # noqa: E731
    return {
        "vendor_name": vendor_name, "vendor_address": None, "vendor_email": email,
        "vendor_tax_id": None, "invoice_number": inv, "invoice_date": date, "due_date": None,
        "po_number": po, "order_reference_hint": None, "currency": currency,
        "bank_name": None, "bank_account": bank_account,
        "bank_change_notice": bool(re.search(r"(new|updated|changed)\s+(bank|banking|payment)", text, re.I)),
        "line_items": items, "subtotal": subtotal, "tax_rate": rate, "tax_amount": tax,
        "tax_inclusive": bool(re.search(r"incl\.?|inkl\.?|including\s+(vat|tax)", text, re.I)),
        "total": total, "notes": None,
        "confidence": {"vendor_name": c(vendor_name, 0.5), "invoice_number": c(inv), "invoice_date": c(date),
                       "total": c(total), "po_number": c(po), "bank_account": c(bank_account),
                       "line_items": 0.5 if items else 0.0},
    }


# ---------------------------------------------------------------- cache (only used when live models are exhausted)
def _cache_path(h: str):
    d = config.DATA / "cache"
    d.mkdir(exist_ok=True)
    return d / f"{h}.json"


def _cache_get(h: str) -> dict:
    p = _cache_path(h) if h else None
    if not p or not p.exists():
        raise ExtractionError("no cached extraction for this file")
    return json.loads(p.read_text(encoding="utf-8"))


def _cache_put(h: str, data: dict) -> None:
    _cache_path(h).write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------- helpers
def _parse_json(s: str) -> dict:
    s = s.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end < 0:
        raise ExtractionError("model returned no JSON")
    data = json.loads(s[start:end + 1])
    if isinstance(data, list):
        data = data[0]
    return data


def coerce(d: dict) -> dict:
    """Make sure every expected key exists with a sane type."""
    out = {k: d.get(k) for k in FIELDS_TEMPLATE if k not in ("line_items", "confidence")}
    out["line_items"] = [li for li in (d.get("line_items") or []) if isinstance(li, dict)]
    conf = d.get("confidence") or {}
    out["confidence"] = {k: _clamp(conf.get(k, 0.0)) for k in FIELDS_TEMPLATE["confidence"]}
    out["bank_change_notice"] = bool(d.get("bank_change_notice"))
    out["tax_inclusive"] = bool(d.get("tax_inclusive"))
    for k in ("vendor_name", "invoice_number", "po_number", "bank_account", "vendor_email"):
        if isinstance(out.get(k), str) and out[k].strip().lower() in ("", "null", "none", "n/a"):
            out[k] = None
    return out


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
