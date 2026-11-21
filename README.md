# AP Desk — invoice processing, from PDF to decision

An automated accounts-payable process. An invoice PDF arrives by **email**, **upload**, or a **watched folder**. It is read (digital or scanned), matched to a purchase order, checked against 15 deterministic rules, and given a decision with the reasoning visible. Every stage streams live to the UI.

📘 **Full walkthrough: [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md)**: architecture, every stage, rules, edge cases, API, configuration and design decisions.
🎬 **Demo walkthrough: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)**

**Decisions:** `Approve` · `Awaiting approval` (over the limit) · `Hold for review` · `Request info` (drafts an email to the vendor) · `Reject` · `Fraud hold`

**Also:** four-eyes sign-off (AP reviewer + finance manager, two different people) for high-value and fraud cases · click any extracted field to highlight where it was read on the page (digital and scanned PDFs)

## Run it

```powershell
copy .env.example .env      # then set GEMINI_API_KEY (and optionally IMAP_USER / IMAP_PASSWORD)
.\start.ps1                 # creates venv, generates sample PDFs, builds UI, serves http://127.0.0.1:8000
```

Dev mode: `cd backend; ..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000` and `cd frontend; npm run dev` (port 5173, proxies `/api`).

To check every sample against its expected decision without the UI: `.venv\Scripts\python scripts\run_samples.py -v`

## How it works

```
 Email (IMAP) ─┐
 Upload (UI)  ─┼─► queue ─► 1 Intake ─► 2 Detect ─► 3 OCR ─► 4 Extract ─► 5 Normalize
 Folder drop  ─┘                                                              │
                     UI ◄─ SSE ◄─ 9 Decide ◄─ 8 Validate ◄─ 7 PO match ◄─ 6 Vendor
```

| Stage | What happens |
|---|---|
| Intake | SHA-256 fingerprint, source metadata (sender, subject) |
| Detect | Text layer present, or a scanned image? |
| OCR | Scans only: rendered at 220 dpi, RapidOCR (local, ONNX), per-word confidence |
| Extract | LLM reads fields into JSON with per-field confidence. Chain: Gemini (rotates models on quota errors), then cached result, then local Ollama vision model, then regex parser |
| Normalize | EU/US number formats, locale-aware dates, currency symbols, **tax-inclusive to net**, and **grounding**: critical values must appear verbatim in the document text, otherwise confidence is lowered |
| Vendor | Fuzzy match to the vendor master (name, aliases, tax ID, bank). Bank account and email domains are compared with what's on file, including **lookalike-domain detection** (`acme-supp1ies.com`) |
| PO match | Explicit PO number (OCR-tolerant: `P0-1003`), otherwise **inferred**: open POs are scored on line-description similarity (55%), unit-price fit (25%) and remaining balance (20%) |
| Validate | 15 rules, each with an ID, status and fixed outcome class |
| Decide | Highest-severity outcome wins: fraud > reject > request info > review > approve |

**Design principle: the LLM reads, the rules decide.** The model only turns a messy document into fields. Every decision is deterministic, explainable, and reproducible. That matters because during testing Gemini silently "corrected" a typo-squatted domain (`acme-supp1ies.com` became `acme-supplies.com`). Security checks therefore use the raw document text, never the LLM's output.

### Rules

| ID | Rule | If it fails |
|---|---|---|
| R01 | Required fields (vendor, invoice number, date, total) | request info |
| R02 | Critical-field extraction confidence ≥ 75% | review |
| R03 | Vendor approved and active | reject |
| R04 | Bank details match vendor master | **fraud** |
| R05 | Sender / invoice email domain authentic (lookalike → fraud, different → review) | fraud / review |
| R06 | PO identified (explicit or inferred ≥ 0.72) | request info |
| R07 | PO open and owned by this vendor | reject / review |
| R08 | Currency matches PO | review |
| R09 | Unit prices within ±2% of PO | review |
| R10 | Quantity ≤ remaining PO quantity (across earlier invoices) | review |
| R11 | Arithmetic: lines = subtotal, subtotal + tax = total, tax = rate × subtotal | review |
| R12 | Running total across all invoices on the PO ≤ PO value + 2% | review |
| R13 | Exact duplicate (same file, or same vendor + invoice number) | reject |
| R14 | Near-duplicate (same vendor, amount ±1%, ≤14 days, different number) | review |
| R15 | Date plausible (not future, ≤ 180 days old) | review |

## Edge cases

| # | Scenario | Why it's hard | What the process does |
|---|---|---|---|
| 1 | **Bank details changed + lookalike sender** (Acme) | Everything else is perfect: right PO, right prices, right math. A tired reviewer would approve it. | `FRAUD_HOLD`. Shows the account on file next to the account on the invoice. Deliberately **does not** email the sender, because that channel may be compromised. Next step: call the contact already on file. |
| 2 | **Scanned, no PO number, VAT-inclusive, EUR, German** (Brightline) | No text layer. Prices include 19% VAT, so the line prices don't match the net PO prices. Day-first dates and `4.938,50` number format. | OCR, then extraction, then embedded tax removed (`4,938.50 → 4,150.00 net`). PO **inferred** as PO-1003 over PO-1007 (0.85 vs 0.39). Approved, with the inference shown. |
| 3 | **Split PO overrun** (Cobalt, 3rd invoice) | The invoice on its own is valid. Only the cumulative view shows 42h billed against 35h remaining, taking the PO 5.8% over. | `HOLD` with the balance history (earlier invoices and their amounts). The reviewer can approve the overrun, pay up to the PO balance, or ask for a PO amendment. |
| 4 | **Near-duplicate resubmission** (Pixel & Pine) | New invoice number, new template, same milestone, 5 days later. An exact-match duplicate check misses it. | `HOLD`. R14 (amount, date window, 100% line overlap) and R10 (milestone already billed) both fire. Links to the earlier invoice. |

Also covered: missing invoice number (`REQUEST_INFO` plus a drafted vendor email a person reviews before sending), inactive vendor (`REJECT`), and history (invoices pre-loaded as approved last month, so cumulative checks have real context).

## Project layout

```
backend/app/
  main.py            REST + SSE + serves built UI
  pipeline/          documents (detect/OCR) · extract · normalize · vendor · match · rules · decide · runner
  intake/            email_intake (IMAP poll + SMTP send) · folder (watched folder)
  worker.py          background queue
  seed.py            history invoices
data/master/         vendors.json, purchase_orders.json
data/samples/        generated test invoices (+ manifest.json with expected outcomes)
data/inbox/          watched folder
frontend/src/        React UI: dashboard, live run view, intake, review queue, POs
scripts/             generate_invoices.py · run_samples.py · send_test_emails.py
```

## Known limits

- Single-tenant SQLite and one worker thread. Fine for hundreds of invoices a month; you'd swap in Postgres plus a task queue to scale.
- Line-item matching is fuzzy text; a production system would use a learned vendor-SKU mapping.
- The Gemini free tier is rate limited. The extractor rotates models, then falls back to cache, a local model, and regex, and the trace always shows which one ran.
