"""Find where an extracted value sits on the page, so the UI can highlight it.

Digital PDFs: word positions from the text layer (pdfplumber).
Scans: word boxes saved by the OCR stage.
All boxes are returned as page fractions (0..1) so the UI can overlay them at any zoom.
"""
from __future__ import annotations

import io
import json
import re
from functools import lru_cache

import pdfplumber
import pypdfium2 as pdfium

from .. import config


def _cache_file(file_hash: str):
    d = config.DATA / "cache"
    d.mkdir(exist_ok=True)
    return d / f"{file_hash}_ocrboxes.json"


def save_ocr_boxes(file_hash: str, boxes: list[dict]) -> None:
    _cache_file(file_hash).write_text(json.dumps(boxes), encoding="utf-8")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9@.]", "", str(s).lower())


def variants(value) -> list[str]:
    """Different ways the same value may be printed."""
    out: list[str] = []
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        v = float(value)
        us = f"{v:,.2f}"
        out += [us, f"{v:.2f}", us.replace(",", "X").replace(".", ",").replace("X", ".")]
        if v.is_integer():
            out.append(f"{int(v):,}")
        return out
    s = str(value).strip()
    out.append(s)
    if "-" in s and re.fullmatch(r"[\d\-]+", s):  # routing-account -> account part
        out += [p for p in s.split("-") if len(p) >= 6]
    if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", s.replace(" ", "")):  # IBAN printed in blocks of 4
        compact = s.replace(" ", "")
        out.append(" ".join(compact[i:i + 4] for i in range(0, len(compact), 4)))
    return out


def page_count(path: str) -> int:
    pdf = pdfium.PdfDocument(path)
    n = len(pdf)
    pdf.close()
    return n


@lru_cache(maxsize=64)
def render_png(path: str, page: int, dpi: int = 130) -> bytes:
    pdf = pdfium.PdfDocument(path)
    img = pdf[page].render(scale=dpi / 72).to_pil().convert("RGB")
    pdf.close()
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def locate(path: str, file_hash: str, doc_type: str, value) -> list[dict]:
    cands = [v for v in variants(value) if len(_norm(v)) >= 2]
    if not cands:
        return []
    if doc_type == "scanned":
        return _locate_ocr(file_hash, cands)
    return _locate_text(path, cands)


def _locate_text(path: str, cands: list[str]) -> list[dict]:
    hits = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            W, H = float(page.width), float(page.height)
            for c in cands:
                try:
                    found = page.search(c, regex=False, case=False)
                except Exception:  # noqa: BLE001
                    found = []
                for f in found:
                    hits.append({"page": pno, "x0": f["x0"] / W, "y0": f["top"] / H,
                                 "x1": f["x1"] / W, "y1": f["bottom"] / H})
            if hits:
                break
    return _dedupe(hits)[:6]


def _locate_ocr(file_hash: str, cands: list[str]) -> list[dict]:
    f = _cache_file(file_hash)
    if not f.exists():
        return []
    boxes = json.loads(f.read_text(encoding="utf-8"))
    hits = []
    for c in cands:
        n = _norm(c)
        for b in boxes:
            t = _norm(b["text"])
            if not t:
                continue
            if n in t or (len(t) >= 4 and t in n and len(t) >= 0.35 * len(n)):
                hits.append({k: b[k] for k in ("page", "x0", "y0", "x1", "y1")})
        if hits:
            break
    return _dedupe(hits)[:6]


def _dedupe(hits: list[dict]) -> list[dict]:
    out, seen = [], set()
    for h in hits:
        k = (h["page"], round(h["x0"], 3), round(h["y0"], 3))
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out
