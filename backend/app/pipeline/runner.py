"""Orchestrates one invoice run through all stages, emitting a visible event per stage."""
from __future__ import annotations

import time
import traceback
from pathlib import Path

from .. import config
from ..db import EmailDraft, add_event, audit, get_run, session, update_run
from . import decide as decide_mod
from .documents import detect, ocr, render_pages
from .extract import extract
from .match import match_po
from .normalize import normalize
from .rules import run_rules
from .vendor import resolve_vendor

STAGES = [
    ("intake", "Intake"),
    ("detect", "Document type"),
    ("ocr", "OCR"),
    ("extract", "Field extraction"),
    ("normalize", "Normalize"),
    ("vendor", "Vendor verification"),
    ("match", "PO matching"),
    ("validate", "Validation rules"),
    ("decide", "Decision"),
]


class Stage:
    def __init__(self, run_id: int, key: str):
        self.run_id, self.key = run_id, key
        self.t0 = time.time()
        update_run(run_id, current_stage=key)
        add_event(run_id, key, "started", dict(STAGES)[key])

    def done(self, status: str, title: str, detail: dict | None = None):
        elapsed = time.time() - self.t0
        pad = config.STAGE_DELAY_MS / 1000 - elapsed  # pacing so the live view is readable
        if pad > 0:
            time.sleep(pad)
        add_event(self.run_id, self.key, status, title, detail or {}, int((time.time() - self.t0) * 1000))


def process(run_id: int) -> None:
    run = get_run(run_id)
    if not run:
        return
    t_start = time.time()
    update_run(run_id, status="running", error="")
    audit(run_id, "run_started", f"source={run.source}")
    try:
        _process(run_id)
        update_run(run_id, status="done", current_stage="", duration_ms=int((time.time() - t_start) * 1000))
    except Exception as e:  # noqa: BLE001
        add_event(run_id, "error", "fail", "Run failed", {"error": str(e), "trace": traceback.format_exc()[-1500:]})
        update_run(run_id, status="error", error=str(e), current_stage="",
                   duration_ms=int((time.time() - t_start) * 1000))
        audit(run_id, "run_failed", str(e))


def _process(run_id: int) -> None:
    run = get_run(run_id)
    src = run.source_meta or {}

    # 1 intake
    st = Stage(run_id, "intake")
    path = Path(run.file_path)
    pdf_bytes = path.read_bytes()
    st.done("ok", f"Received {run.filename} via {run.source}", {
        "source": run.source, "filename": run.filename, "size_kb": round(len(pdf_bytes) / 1024, 1),
        "sha256": run.file_hash[:16] + "…", **({k: src[k] for k in ("from", "subject", "received") if k in src})})

    # 2 detect
    st = Stage(run_id, "detect")
    doc = detect(str(path))
    update_run(run_id, doc_type=doc["doc_type"])
    st.done("ok", "Scanned image — no text layer" if doc["doc_type"] == "scanned"
            else f"Digital PDF — {doc['chars']} chars of text",
            {"pages": doc["pages"], "chars": doc["chars"], "embedded_images": doc["images"],
             "route": "OCR + vision" if doc["doc_type"] == "scanned" else "text layer"})

    # 3 OCR
    st = Stage(run_id, "ocr")
    pages_png = render_pages(str(path))
    if doc["doc_type"] == "scanned":
        o = ocr(pages_png)
        doc["ocr_text"] = o["text"]
        st.done("ok" if o["avg_confidence"] >= 0.85 else "warn",
                f"OCR read {o['words']} text regions, avg confidence {o['avg_confidence']:.0%}",
                {"avg_confidence": o["avg_confidence"], "low_confidence_words": o["low_confidence"],
                 "preview": o["text"][:800]})
    else:
        st.done("skip", "Not needed — text layer present", {"preview": doc["text"][:800]})
    source_text = doc.get("ocr_text") or doc.get("text") or ""

    # 4 extract
    st = Stage(run_id, "extract")
    ex = extract(doc, pdf_bytes, pages_png, run.file_hash)
    data = ex["data"]
    update_run(run_id, extractor=ex["extractor"], extracted=data)
    fell_back = any(not a["ok"] for a in ex["attempts"])
    st.done("warn" if ex["extractor"] in ("regex", "cache") else "ok",
            f"Extracted with {ex['extractor']}" + (" (fallback)" if fell_back else "") +
            f" — {len(data['line_items'])} line item(s)",
            {"extractor": ex["extractor"], "attempts": ex["attempts"], "fields": _field_view(data)})

    # 5 normalize
    st = Stage(run_id, "normalize")
    from ..master import vendors
    hint = None
    vn = (data.get("vendor_name") or "").lower()
    for v in vendors():
        if v["name"].split()[0].lower() in vn:
            hint = v["currency"]
            break
    norm = normalize(data, source_text, hint)
    update_run(run_id, normalized=norm, invoice_number=norm.get("invoice_number") or "",
               invoice_date=norm.get("invoice_date") or "", currency=norm.get("currency") or "",
               subtotal=norm.get("subtotal") or 0.0, total=norm.get("total") or 0.0)
    st.done("ok", f"Net {_m(norm.get('subtotal'))} + tax {_m(norm.get('tax_amount'))} = "
                  f"{norm.get('currency') or ''} {_m(norm.get('total'))}",
            {"notes": norm["notes"], "invoice_date": norm.get("invoice_date"),
             "currency": norm.get("currency"), "tax_inclusive": norm.get("tax_inclusive"),
             "subtotal": norm.get("subtotal"), "tax_amount": norm.get("tax_amount"), "total": norm.get("total"),
             "grounding": norm.get("grounding")})

    # 6 vendor
    st = Stage(run_id, "vendor")
    vendor = resolve_vendor(norm, None if src.get("internal_forward") else src.get("from"))
    update_run(run_id, vendor_id=vendor.get("vendor_id", ""),
               vendor_name=vendor.get("vendor_name") or norm.get("vendor_name") or "")
    if not vendor["found"]:
        st.done("fail", f"'{norm.get('vendor_name')}' not in vendor master", vendor)
    else:
        bad = vendor["bank_status"] == "mismatch" or "lookalike" in (
            vendor["sender_domain_relation"], vendor["invoice_domain_relation"])
        st.done("fail" if bad else "ok",
                f"{vendor['vendor_name']} ({vendor['vendor_id']})" + (" — payment details anomaly" if bad else ""),
                vendor)

    # 7 match
    st = Stage(run_id, "match")
    po = match_po(norm, vendor, run_id)
    update_run(run_id, match=po, po_number=po.get("po_number", ""), normalized=norm)  # norm now has matched_sku
    if po.get("found"):
        st.done("ok" if po["method"] == "explicit" else "warn",
                f"{po['po_number']} ({'printed on invoice' if po['method'] == 'explicit' else f'inferred, score {po['score']:.2f}'})",
                po)
    else:
        st.done("fail", po.get("reason", "No PO match"), po)

    # 8 validate
    st = Stage(run_id, "validate")
    rules = run_rules(run_id, run.file_hash, norm, vendor, po)
    update_run(run_id, rules=rules)
    fails = sum(1 for r in rules if r["status"] == "fail")
    warns = sum(1 for r in rules if r["status"] == "warn")
    passes = sum(1 for r in rules if r["status"] == "pass")
    st.done("fail" if fails else "warn" if warns else "ok",
            f"{passes} passed · {warns} warnings · {fails} failed", {"rules": rules})

    # 9 decide
    st = Stage(run_id, "decide")
    d = decide_mod.decide(norm, vendor, po, rules, src)
    update_run(run_id, decision=d["decision"], headline=d["headline"],
               explanation=d["explanation"], next_actions=d["next_actions"])
    if d["email"]:
        with session() as s:
            s.add(EmailDraft(run_id=run_id, **d["email"]))
            s.commit()
    audit(run_id, "decision", f"{d['decision']}: {d['headline']}")
    st.done({"APPROVE": "ok", "HOLD": "warn", "REQUEST_INFO": "warn"}.get(d["decision"], "fail"),
            d["headline"], d)


def _m(v) -> str:
    return "—" if v is None else f"{v:,.2f}"


def _field_view(d: dict) -> list[dict]:
    c = d.get("confidence", {})
    keys = ["vendor_name", "invoice_number", "invoice_date", "po_number", "currency", "subtotal",
            "tax_rate", "tax_amount", "total", "tax_inclusive", "bank_account", "vendor_email"]
    return [{"field": k, "value": d.get(k), "confidence": c.get(k)} for k in keys]
