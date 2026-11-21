"""Stage 2/3: detect text layer vs scan, render pages, run local OCR on scans."""
from __future__ import annotations

import io
from functools import lru_cache

import numpy as np
import pdfplumber
import pypdfium2 as pdfium

MIN_CHARS_PER_PAGE = 40


def detect(path: str) -> dict:
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        texts = [(p.extract_text() or "") for p in pdf.pages]
        images = sum(len(p.images) for p in pdf.pages)
    text = "\n".join(texts).strip()
    scanned = len(text) < MIN_CHARS_PER_PAGE * max(pages, 1)
    return {
        "pages": pages,
        "chars": len(text),
        "images": images,
        "doc_type": "scanned" if scanned else "text",
        "text": text,
    }


def render_pages(path: str, dpi: int = 220, max_pages: int = 3) -> list[bytes]:
    """Render PDF pages to PNG bytes (used for OCR and vision models)."""
    pdf = pdfium.PdfDocument(path)
    out = []
    for i in range(min(len(pdf), max_pages)):
        img = pdf[i].render(scale=dpi / 72).to_pil().convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())
    pdf.close()
    return out


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def ocr(png_pages: list[bytes]) -> dict:
    """OCR each page; rebuild reading-order lines from word boxes."""
    from PIL import Image

    engine = _ocr_engine()
    all_lines: list[str] = []
    scores: list[float] = []
    low_conf: list[dict] = []
    word_boxes: list[dict] = []
    for page_no, page_png in enumerate(png_pages):
        img = np.array(Image.open(io.BytesIO(page_png)).convert("RGB"))
        H, W = img.shape[:2]
        result, _ = engine(img)
        if not result:
            continue
        boxes = []
        for box, text, score in result:
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            boxes.append({"x": min(xs), "y": (min(ys) + max(ys)) / 2,
                          "h": max(ys) - min(ys), "text": text, "score": float(score)})
            word_boxes.append({"page": page_no, "text": text, "x0": min(xs) / W, "y0": min(ys) / H,
                               "x1": max(xs) / W, "y1": max(ys) / H})
            scores.append(float(score))
            if float(score) < 0.8:
                low_conf.append({"text": text, "score": round(float(score), 2)})
        all_lines.extend(_group_lines(boxes))
        all_lines.append("")
    avg = round(sum(scores) / len(scores), 3) if scores else 0.0
    return {"text": "\n".join(all_lines).strip(), "avg_confidence": avg,
            "words": len(scores), "low_confidence": low_conf[:15], "boxes": word_boxes}


def _group_lines(boxes: list[dict]) -> list[str]:
    boxes.sort(key=lambda b: b["y"])
    lines: list[list[dict]] = []
    for b in boxes:
        if lines and abs(lines[-1][-1]["y"] - b["y"]) < max(8, 0.5 * b["h"]):
            lines[-1].append(b)
        else:
            lines.append([b])
    return ["   ".join(x["text"] for x in sorted(l, key=lambda b: b["x"])) for l in lines]
