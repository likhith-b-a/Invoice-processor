"""Generate realistic sample invoices (4 layouts, 1 scanned) + history invoices + manifest.json.

Run:  .venv/Scripts/python scripts/generate_invoices.py
"""
from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "samples"
(OUT / "history").mkdir(parents=True, exist_ok=True)

BILL_TO = ["Meridian Retail Group Inc.", "Accounts Payable", "500 Harbor Blvd, Suite 1200",
           "San Francisco, CA 94111", "ap@meridian-retail.com"]


def money(v: float, fmt: str, sym: str = "") -> str:
    s = f"{v:,.2f}"
    if fmt == "eu":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {sym}".strip()
    return f"{sym}{s}"


def compute(inv: dict) -> dict:
    rows = []
    for desc, sku, qty, unit in inv["lines"]:
        rows.append({"desc": desc, "sku": sku, "qty": qty, "unit": unit, "amount": round(qty * unit, 2)})
    sub = round(sum(r["amount"] for r in rows), 2)
    rate = inv.get("tax_rate", 0)
    if inv.get("tax_inclusive"):  # line prices printed gross; sub here is the net value
        tax = round(sub * rate / 100, 2)
        total = round(sub + tax, 2)
    else:
        tax = round(sub * rate / 100, 2)
        total = round(sub + tax, 2)
    return {"rows": rows, "subtotal": sub, "tax": tax, "total": total}


# --------------------------------------------------------------------------- layouts
def layout_classic(c: canvas.Canvas, inv: dict, calc: dict):
    W, H = LETTER
    v = inv["vendor"]
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, H - 25 * mm, v["name"])
    c.setFont("Helvetica", 9)
    y = H - 31 * mm
    for line in v["address"] + [v["email"], v.get("phone", "")]:
        c.drawString(20 * mm, y, line)
        y -= 4.2 * mm
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawRightString(W - 20 * mm, H - 26 * mm, "INVOICE")
    c.setFillColor(colors.black)
    meta = [("Invoice No.", inv.get("number")), ("Invoice Date", inv["date"]), ("Due Date", inv.get("due")),
            ("PO Number", inv.get("po")), (v.get("tax_label", "Tax ID"), v.get("tax_id"))]
    y = H - 36 * mm
    for k, val in meta:
        if not val:
            continue
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(W - 55 * mm, y, k + ":")
        c.setFont("Helvetica", 9)
        c.drawRightString(W - 20 * mm, y, str(val))
        y -= 5 * mm
    y = H - 72 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "BILL TO")
    c.setFont("Helvetica", 9)
    for line in BILL_TO:
        y -= 4.5 * mm
        c.drawString(20 * mm, y, line)
    y -= 12 * mm
    _table(c, inv, calc, y, W, header_fill="#e2e8f0")


def layout_modern(c: canvas.Canvas, inv: dict, calc: dict):
    W, H = LETTER
    v = inv["vendor"]
    accent = colors.HexColor(inv.get("accent", "#0f766e"))
    c.setFillColor(accent)
    c.rect(0, H - 38 * mm, W, 38 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(18 * mm, H - 18 * mm, v["name"])
    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, H - 25 * mm, " · ".join(v["address"]))
    c.drawString(18 * mm, H - 30 * mm, f"{v['email']}  ·  {v.get('phone', '')}")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(W - 18 * mm, H - 18 * mm, "TAX INVOICE")
    c.setFillColor(colors.black)
    y = H - 50 * mm
    cols = [("INVOICE #", inv.get("number") or "—"), ("ISSUED", inv["date"]), ("DUE", inv.get("due") or "—"),
            ("PURCHASE ORDER", inv.get("po") or "—")]
    x = 18 * mm
    for k, val in cols:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(x, y, k)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y - 5 * mm, str(val))
        x += 45 * mm
    y -= 18 * mm
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(18 * mm, y, "BILLED TO")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    for line in BILL_TO[:4]:
        y -= 4.5 * mm
        c.drawString(18 * mm, y, line)
    if inv.get("ref_hint"):
        c.drawRightString(W - 18 * mm, y + 13.5 * mm, inv["ref_hint"])
    y -= 12 * mm
    _table(c, inv, calc, y, W, header_fill="#ccfbf1", left=18 * mm)


def layout_minimal(c: canvas.Canvas, inv: dict, calc: dict):
    W, H = A4
    v = inv["vendor"]
    c.setFont("Courier-Bold", 13)
    c.drawString(20 * mm, H - 22 * mm, v["name"].upper())
    c.setFont("Courier", 8.5)
    y = H - 28 * mm
    for line in v["address"] + [v["email"], f"{v.get('tax_label', 'Tax ID')}: {v.get('tax_id')}"]:
        c.drawString(20 * mm, y, line)
        y -= 4 * mm
    y -= 6 * mm
    c.setFont("Courier-Bold", 10)
    c.drawString(20 * mm, y, f"INVOICE {inv.get('number') or ''}".strip())
    c.setFont("Courier", 9)
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Date: {inv['date']}    Terms: {inv.get('terms', 'Net 15')}")
    if inv.get("po"):
        y -= 5 * mm
        c.drawString(20 * mm, y, f"Your PO: {inv['po']}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Client: {BILL_TO[0]}")
    y -= 12 * mm
    _table(c, inv, calc, y, W, header_fill=None, font="Courier")


def layout_german(c: canvas.Canvas, inv: dict, calc: dict):
    W, H = A4
    v = inv["vendor"]
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, H - 22 * mm, v["name"])
    c.setFont("Helvetica", 8.5)
    c.drawString(20 * mm, H - 27 * mm, " | ".join(v["address"]) + f" | {v['email']}")
    c.drawString(20 * mm, H - 31 * mm, f"USt-IdNr.: {v['tax_id']}")
    c.setFont("Helvetica", 9)
    y = H - 48 * mm
    for line in BILL_TO[:4]:
        c.drawString(20 * mm, y, line)
        y -= 4.5 * mm
    c.setFont("Helvetica-Bold", 15)
    c.drawString(20 * mm, H - 82 * mm, "RECHNUNG / INVOICE")
    c.setFont("Helvetica", 9)
    meta = [("Rechnungsnr. / Invoice No.", inv["number"]), ("Rechnungsdatum / Date", inv["date"]),
            ("Leistungszeitraum / Period", inv.get("period", "")), ("Ihre Referenz / Your ref.", inv.get("ref_hint", ""))]
    y = H - 90 * mm
    for k, val in meta:
        c.drawString(20 * mm, y, k)
        c.drawString(85 * mm, y, val)
        y -= 5 * mm
    y -= 8 * mm
    _table(c, inv, calc, y, W, header_fill="#e5e7eb", german=True)


def _table(c, inv, calc, y, W, header_fill=None, left=20 * mm, font="Helvetica", german=False):
    fmt, sym = inv.get("fmt", "us"), inv.get("sym", "$")
    right = W - left
    heads = ["Pos. / Description", "Art.-Nr.", "Menge", "Einzelpreis (brutto)", "Betrag (brutto)"] if german \
        else ["Description", "Item", "Qty", "Unit Price", "Amount"]
    xs = [left + 2 * mm, right - 98 * mm, right - 62 * mm, right - 30 * mm, right - 2 * mm]
    if header_fill:
        c.setFillColor(colors.HexColor(header_fill))
        c.rect(left, y - 2 * mm, right - left, 7 * mm, stroke=0, fill=1)
        c.setFillColor(colors.black)
    c.setFont(f"{font}-Bold" if font != "Courier" else "Courier-Bold", 8.5)
    c.drawString(xs[0], y, heads[0])
    c.drawString(xs[1], y, heads[1])
    for i in (2, 3, 4):
        c.drawRightString(xs[i], y, heads[i])
    y -= 8 * mm
    c.setFont(font, 8.5)
    rate = inv.get("tax_rate", 0)
    for r in calc["rows"]:
        unit = r["unit"] * (1 + rate / 100) if inv.get("tax_inclusive") else r["unit"]
        amount = round(r["qty"] * round(unit, 2), 2)
        c.drawString(xs[0], y, r["desc"][:58])
        if not inv.get("hide_sku"):
            c.drawString(xs[1], y, r["sku"])
        c.drawRightString(xs[2], y, f"{r['qty']:g}")
        c.drawRightString(xs[3], y, money(unit, fmt, "" if german else ""))
        c.drawRightString(xs[4], y, money(amount, fmt, "" if german else ""))
        y -= 6 * mm
    c.line(left, y + 3 * mm, right, y + 3 * mm)
    y -= 3 * mm
    if inv.get("tax_inclusive"):
        totals = [("Gesamtbetrag inkl. MwSt. / Total incl. VAT", money(calc["total"], fmt, sym), True),
                  (f"darin enthaltene MwSt. {rate:g}% / incl. VAT {rate:g}%", money(calc["tax"], fmt, sym), False)]
    else:
        tl = inv.get("tax_label_line", f"Sales Tax ({rate:g}%)")
        totals = [("Subtotal", money(calc["subtotal"], fmt, sym), False), (tl, money(calc["tax"], fmt, sym), False),
                  (inv.get("total_label", "Total Due"), money(calc["total"], fmt, sym), True)]
    for label, val, bold in totals:
        c.setFont((f"{font}-Bold" if font != "Courier" else "Courier-Bold") if bold else font, 10 if bold else 9)
        c.drawRightString(right - 35 * mm, y, label)
        c.drawRightString(right - 2 * mm, y, val)
        y -= 6 * mm
    if inv.get("currency_line"):
        c.setFont(font, 8)
        c.drawRightString(right - 2 * mm, y, inv["currency_line"])
        y -= 6 * mm
    y -= 6 * mm
    if inv.get("notice"):
        c.setFillColor(colors.HexColor("#b91c1c"))
        c.setFont(f"{font}-Bold" if font != "Courier" else "Courier-Bold", 9)
        for line in inv["notice"]:
            c.drawString(left, y, line)
            y -= 4.8 * mm
        c.setFillColor(colors.black)
        y -= 2 * mm
    c.setFont(f"{font}-Bold" if font != "Courier" else "Courier-Bold", 9)
    c.drawString(left, y, "Bankverbindung / Payment details" if german else "Payment details")
    c.setFont(font, 8.5)
    for line in inv["bank"]:
        y -= 4.5 * mm
        c.drawString(left, y, line)
    if inv.get("footer"):
        c.setFont(font, 7.5)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(left, 15 * mm, inv["footer"])
        c.setFillColor(colors.black)


LAYOUTS = {"classic": (layout_classic, LETTER), "modern": (layout_modern, LETTER),
           "minimal": (layout_minimal, A4), "german": (layout_german, A4)}


def render(inv: dict, path: Path):
    calc = compute(inv)
    fn, size = LAYOUTS[inv["style"]]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    c.setTitle(f"Invoice {inv.get('number') or ''}")
    fn(c, inv, calc)
    c.showPage()
    c.save()
    data = buf.getvalue()
    if inv.get("scanned"):
        data = to_scan(data)
    path.write_bytes(data)
    return calc


def to_scan(pdf_bytes: bytes) -> bytes:
    """Rasterize, tilt, add noise + blur, JPEG-compress -> image-only PDF (no text layer)."""
    import numpy as np
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    img = pdf[0].render(scale=170 / 72).to_pil().convert("L")
    img = img.rotate(-0.9, resample=Image.BICUBIC, expand=False, fillcolor=255)
    arr = np.array(img).astype(np.int16)
    rng = np.random.default_rng(7)
    arr = arr + rng.normal(0, 9, arr.shape).astype(np.int16)
    specks = rng.random(arr.shape) < 0.0008
    arr[specks] = 40
    arr = np.clip(arr * 0.96 + 6, 0, 255).astype(np.uint8)  # slightly grey paper
    img = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(0.5))
    jpg = io.BytesIO()
    img.save(jpg, format="JPEG", quality=55)
    out = io.BytesIO()
    Image.open(jpg).save(out, format="PDF", resolution=170)
    return out.getvalue()


# --------------------------------------------------------------------------- vendors as printed
NORTHWIND = {"name": "Northwind Office Supplies Inc.", "address": ["1840 Commerce Way", "Oakland, CA 94607"],
             "email": "billing@northwind-supplies.com", "phone": "(510) 555-0144", "tax_label": "EIN", "tax_id": "94-3127745"}
ACME_FAKE = {"name": "Acme Industrial Supplies LLC", "address": ["77 Foundry Road", "Columbus, OH 43215"],
             "email": "accounts@acme-supp1ies.com", "phone": "(614) 555-0199", "tax_label": "EIN", "tax_id": "47-2210983"}
BRIGHTLINE = {"name": "Brightline Logistics GmbH", "address": ["Am Sandtorkai 41", "20457 Hamburg", "Deutschland"],
              "email": "rechnung@brightline-logistics.de", "tax_id": "DE298471560"}
COBALT = {"name": "Cobalt Cloud Services Ltd", "address": ["14 Clerkenwell Close", "London EC1R 0AA", "United Kingdom"],
          "email": "invoices@cobaltcloud.io", "tax_label": "VAT No", "tax_id": "GB284917362"}
PIXEL = {"name": "Pixel & Pine Design Studio", "address": ["220 Alder St, Studio 4", "Portland, OR 97204"],
         "email": "studio@pixelandpine.co", "phone": "(503) 555-0123", "tax_label": "EIN", "tax_id": "81-4429017"}
HELIX = {"name": "Helix Lab Equipment Co.", "address": ["9 Innovation Pkwy", "Durham, NC 27703"],
         "email": "accounts@helixlab.com", "tax_label": "EIN", "tax_id": "33-9918274"}

BANK_NW = ["JPMorgan Chase Bank, N.A.", "Routing (ABA): 021000021   Account: 4471829035", "Reference: invoice number"]
BANK_COBALT = ["Barclays Bank UK PLC", "IBAN: GB33 BUKB 2020 1555 5555 55   SWIFT: BUKBGB22", "Account name: Cobalt Cloud Services Ltd"]
BANK_PIXEL = ["Silicon Valley Bank", "Routing: 121140399   Account: 3300918274"]

SAMPLES = [
    {
        "file": "01_northwind_INV-NW-88213.pdf", "title": "Happy path — clean digital invoice",
        "scenario": "happy", "simulated_sender": "billing@northwind-supplies.com",
        "expect": "APPROVE",
        "inv": {"style": "classic", "vendor": NORTHWIND, "number": "INV-NW-88213", "date": "November 18, 2026",
                "due": "December 18, 2026", "po": "PO-1001", "tax_rate": 8.25, "sym": "$",
                "lines": [("A4 copy paper, 80gsm (box of 5 reams)", "NW-PAP-A4", 50, 42.00),
                          ("Toner cartridge HP 26X black", "NW-TON-26X", 20, 89.50),
                          ("Ergonomic mesh office chair", "NW-CHR-ERG", 10, 245.00)],
                "bank": BANK_NW, "footer": "Thank you for your business. Late payments subject to 1.5% monthly fee."},
    },
    {
        "file": "02_acme_INV-AC-55102_bank_change.pdf", "title": "Edge case — bank details changed + lookalike domain",
        "scenario": "fraud", "simulated_sender": "accounts@acme-supp1ies.com", "expect": "FRAUD_HOLD",
        "inv": {"style": "modern", "accent": "#1e3a8a", "vendor": ACME_FAKE, "number": "INV-AC-55102",
                "date": "11/17/2026", "due": "12/01/2026", "po": "PO-1002", "tax_rate": 7.0, "sym": "$",
                "lines": [("Nitrile safety gloves (box of 100)", "AC-GLV-N", 200, 6.25),
                          ("Hard hat, white, ANSI Type I", "AC-HAT-W", 50, 18.40),
                          ("Hi-vis safety vest, class 2", "AC-VST-HV", 100, 9.80)],
                "notice": ["IMPORTANT: Our banking details have changed effective immediately.",
                           "Please update your records and remit all payments to the new account below."],
                "bank": ["First Horizon Bank", "Routing: 084000026   Account: 7720019934",
                         "Account name: Acme Industrial Supplies"]},
    },
    {
        "file": "03_brightline_scan_RE-2026-1187.pdf", "title": "Edge case — scanned, no PO number, VAT-inclusive (EUR)",
        "scenario": "scan_infer_po", "simulated_sender": "rechnung@brightline-logistics.de", "expect": "APPROVE",
        "inv": {"style": "german", "scanned": True, "vendor": BRIGHTLINE, "number": "RE-2026-1187",
                "date": "14.11.2026", "period": "01.11.2026 - 12.11.2026", "ref_hint": "Transporte HH-RTM KW 45/46",
                "tax_rate": 19.0, "tax_inclusive": True, "fmt": "eu", "sym": "€", "hide_sku": True,
                "lines": [("FTL Transport Hamburg - Rotterdam", "BL-FRT-HR", 2, 1850.00),
                          ("Zollabfertigung / customs handling", "BL-CUS-HD", 2, 225.00)],
                "bank": ["Commerzbank AG", "IBAN: DE89 3704 0044 0532 0130 00   BIC: COBADEFFXXX"],
                "footer": "Zahlbar innerhalb 30 Tagen ohne Abzug. Geschäftsführer: K. Albers · HRB 154870 Hamburg"},
    },
    {
        "file": "04_cobalt_INV-C-0577_split_po.pdf", "title": "Edge case — 3rd invoice on split PO overruns it",
        "scenario": "split_po_overrun", "simulated_sender": "invoices@cobaltcloud.io", "expect": "HOLD",
        "inv": {"style": "minimal", "vendor": COBALT, "number": "INV-C-0577", "date": "2026-11-19", "po": "PO-1004",
                "tax_rate": 0, "tax_label_line": "VAT 0% (reverse charge)", "total_label": "Amount due (USD)", "sym": "$",
                "lines": [("Cloud migration consulting - Oct 27 to Nov 14", "CC-MIG-HR", 42, 150.00)],
                "bank": BANK_COBALT, "terms": "Net 15"},
    },
    {
        "file": "05_pixelpine_PP-2297_resubmission.pdf", "title": "Edge case — near-duplicate resubmission (new number)",
        "scenario": "near_duplicate", "simulated_sender": "studio@pixelandpine.co", "expect": "HOLD",
        "inv": {"style": "classic", "vendor": PIXEL, "number": "PP-2297", "date": "14 Nov 2026", "due": "14 Dec 2026",
                "po": "PO-1005", "tax_rate": 0, "tax_label_line": "Tax (0%)", "sym": "$", "hide_sku": True,
                "lines": [("Brand refresh - Milestone 2: identity system & logo suite", "", 1, 4800.00)],
                "bank": BANK_PIXEL},
    },
    {
        "file": "06_northwind_missing_invoice_number.pdf", "title": "Missing invoice number — ask vendor",
        "scenario": "request_info", "simulated_sender": "billing@northwind-supplies.com", "expect": "REQUEST_INFO",
        "inv": {"style": "classic", "vendor": NORTHWIND, "number": None, "date": "Nov 20, 2026", "due": "Dec 20, 2026",
                "po": "PO-1006", "tax_rate": 8.25, "sym": "$",
                "lines": [("27-inch IPS monitor, QHD", "NW-MON-27", 15, 189.00),
                          ("Dual monitor arm, desk clamp", "NW-ARM-DL", 8, 64.00)],
                "bank": BANK_NW},
    },
    {
        "file": "07_helix_HLX-30091_inactive_vendor.pdf", "title": "Inactive vendor — reject",
        "scenario": "inactive_vendor", "simulated_sender": "accounts@helixlab.com", "expect": "REJECT",
        "inv": {"style": "minimal", "vendor": HELIX, "number": "HLX-30091", "date": "2026-11-12", "tax_rate": 0,
                "tax_label_line": "Tax", "sym": "$",
                "lines": [("Benchtop centrifuge, 24-place", "HX-CEN-24", 1, 3890.00)],
                "bank": ["Wells Fargo", "Routing: 121000248   Account: 5512093384"]},
    },
]

HISTORY = [
    {"file": "history/cobalt_INV-C-0418.pdf",
     "inv": {"style": "minimal", "vendor": COBALT, "number": "INV-C-0418", "date": "2026-10-06", "po": "PO-1004",
             "tax_rate": 0, "tax_label_line": "VAT 0% (reverse charge)", "sym": "$",
             "lines": [("Cloud migration consulting - Sep 22 to Oct 03", "CC-MIG-HR", 40, 150.00)], "bank": BANK_COBALT}},
    {"file": "history/cobalt_INV-C-0502.pdf",
     "inv": {"style": "minimal", "vendor": COBALT, "number": "INV-C-0502", "date": "2026-10-24", "po": "PO-1004",
             "tax_rate": 0, "tax_label_line": "VAT 0% (reverse charge)", "sym": "$",
             "lines": [("Cloud migration consulting - Oct 06 to Oct 24", "CC-MIG-HR", 45, 150.00)], "bank": BANK_COBALT}},
    {"file": "history/pixelpine_PP-2240.pdf",
     "inv": {"style": "modern", "accent": "#166534", "vendor": PIXEL, "number": "PP-2240", "date": "Sep 30, 2026",
             "po": "PO-1005", "tax_rate": 0, "tax_label_line": "Tax (0%)", "sym": "$",
             "lines": [("Brand refresh - Milestone 1: discovery and moodboards", "PP-BR-M1", 1, 4800.00)], "bank": BANK_PIXEL}},
    {"file": "history/pixelpine_PP-2291.pdf",
     "inv": {"style": "modern", "accent": "#166534", "vendor": PIXEL, "number": "PP-2291", "date": "Nov 9, 2026",
             "po": "PO-1005", "tax_rate": 0, "tax_label_line": "Tax (0%)", "sym": "$",
             "lines": [("Brand refresh - Milestone 2: identity system and logo suite", "PP-BR-M2", 1, 4800.00)],
             "bank": BANK_PIXEL}},
]


def main():
    random.seed(1)
    manifest = []
    for s in SAMPLES:
        calc = render(s["inv"], OUT / s["file"])
        manifest.append({k: s[k] for k in ("file", "title", "scenario", "simulated_sender", "expect")}
                        | {"total": calc["total"]})
        print(f"  {s['file']:<48} total {calc['total']:>10,.2f}")
    for h in HISTORY:
        render(h["inv"], OUT / h["file"])
        print(f"  {h['file']}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {len(SAMPLES)} samples + {len(HISTORY)} history invoices to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
