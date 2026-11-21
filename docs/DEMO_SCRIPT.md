# Demo Script

How to demo AP Desk: setup, a 5-minute recorded walkthrough, a longer live interview version, recovery steps, and likely questions.

---

## 1. Before you start (about 30 minutes ahead)

1. **Fill the extraction cache.** Run this about an hour before. If Gemini's free quota runs out during the demo, the extractor falls back to these saved results (labelled `cache` in the trace), so the demo never stalls.

   ```powershell
   .venv\Scripts\python scripts\run_samples.py
   ```

2. **Tune for presenting.** In `.env`:

   ```
   IMAP_POLL_SECONDS=10     # email gets picked up faster
   STAGE_DELAY_MS=600       # stages animate slowly enough to talk over
   ```

3. **Start the app:** `.\start.ps1`, then open http://127.0.0.1:8000.

4. **Clean slate:** Intake page → **Reset demo data**.
   *This matters:* otherwise re-sent invoices are correctly rejected as duplicates.

5. **Pre-run the background cases** so the dashboard has content. On the Intake page, click **Run** on:
   - `04` Cobalt — split PO overrun
   - `05` Pixel & Pine — near-duplicate
   - `06` Northwind — missing invoice number
   - `07` Helix — inactive vendor

6. **Keep `01`, `02` and `03` unrun.** These are run live.

7. **Open two tabs:**
   - the app, on the Dashboard;
   - Gmail, signed in as the AP mailbox, with `data/samples/01_northwind_INV-NW-88213.pdf` ready to attach.

8. **Check** the Intake page: the email card should say **Listening**.

---

## 2. Five-minute video script

### 0:00–0:30 · The problem (Dashboard)

> "AP teams get hundreds of PDF invoices by email. Someone opens each one, finds the PO, checks the numbers and decides. This system does that end to end, and shows every step of its reasoning."

Point at the ledger strip (processed, auto-approved, needs attention, fraud blocked, average time) and the runs already on the dashboard.

### 0:30–1:45 · Happy path, live by email

1. In Gmail, write an email to the AP address, attach invoice `01`, and send.
2. Switch to the app. Within about 10 seconds a new row appears with a spinner. Click it.
3. Narrate the routing slip as the stages run:
   - "Digital PDF, so OCR is skipped."
   - "Gemini extracts the fields. Every field has a confidence score."
   - "The vendor matches master data: bank account and email domain both check out."
   - "The PO is printed on the invoice, and every line matches on price and quantity."
4. The **APPROVED** stamp lands. Read the next steps aloud: pay to the account on file per terms, book against PO-1001.

### 1:45–3:00 · Edge case: bank-change fraud (the main edge case)

1. Intake → **Run** sample `02` (Acme).
2. Say: *"Same PO, same prices, the math is perfect. A tired person approves this on a Friday afternoon."*
3. Click the **Vendor verification** stage:
   - bank account on file `••••3456` vs on the invoice `••••9934`;
   - email domain `acme-supp1ies.com`, labelled **lookalike**.
4. The **FRAUD HOLD** stamp lands. Show the side-by-side "on file vs on this invoice" panel.
5. Point out that it deliberately **does not reply to the sender**, because that mailbox may belong to the attacker. The next step is to call the contact already on file.
6. Tell the build story: *"While testing, Gemini quietly 'corrected' the fake domain to the real one. That's why fraud checks read the raw PDF text, never the model's output."*

### 3:00–3:50 · Edge case: scanned German invoice (drop this if short on time)

1. **Run** sample `03` (Brightline).
2. **OCR stage:** the PDF is a picture with no text layer; show the OCR confidence and text.
3. **Normalize stage:** prices include 19% VAT, so the embedded tax is removed: 4,938.50 gross becomes 4,150.00 net.
4. **PO matching stage:** no PO number is printed, so it's inferred. PO-1003 scores 0.85 against PO-1007 at 0.39.
5. The **APPROVED** stamp lands, with the inference visible.

### 3:50–4:30 · Human review

1. Open the **Review queue**, then the Cobalt invoice.
2. Show the PO balance bar: earlier invoices, this invoice, and a red overrun, 5.8% over PO-1004.
3. Add a comment, for example *"Extra 7h authorised by project lead"*, and click **Approve for payment**. The audit trail updates and the PO balance moves.
4. Optional: open the Northwind run with no invoice number and show the drafted vendor email (edit / send / discard).

### 4:30–5:00 · Wrap-up

> "The design principle: the LLM only reads, and 15 deterministic rules decide. Every decision points to a rule, so it can be explained and audited. If Gemini fails, it falls back to other models, then the cache, then a local model, then a simple parser, so the pipeline always produces a result."

---

## 3. Live interview demo (longer, interactive)

Follow the same flow, then add any of these as questions come up:

| Show | How |
|---|---|
| Drag-and-drop intake | Drag any PDF onto the page; it opens the live run |
| Watched folder | Copy a PDF into `data\inbox`; it appears on the dashboard within about 2 s |
| Exact duplicate | Email invoice `01` again; it's rejected by **R13** |
| Near-duplicate | Open the Pixel & Pine run, then "Open earlier invoice" to compare |
| All the checks | Scroll the 15 rules on any run |
| PO balances | **Purchase orders** page: invoiced vs total per PO and per line |
| Dark mode | Sidebar toggle |
| Their own PDF | Upload it. An unknown vendor is rejected with its closest candidates, showing the system handles invoices it has never seen |

---

## 4. If something breaks

| Problem | What to do |
|---|---|
| Email is slow to arrive | Run `.venv\Scripts\python scripts\send_test_emails.py 01`, or use the sample **Run** button |
| Gemini quota error (429) | Nothing; the cache kicks in and the trace shows it. Mention it on camera, because it shows the resilience |
| A run says "duplicate" unexpectedly | You forgot to reset. Intake → **Reset demo data**, then run it again |
| The app is down | Re-run `.\start.ps1` |
| The PDF pane is blank | Open the PDF in a new tab using the filename link above the pane |

---

## 5. Questions to expect

**Why not let the LLM make the decision?**
Decisions have to be explainable, reproducible and auditable. A model can be wrong without anyone noticing, and the domain "correction" is the proof. The model reads; rules decide.

**How do you stop made-up values?**
Three ways:
- per-field confidence scores;
- grounding: every critical value must appear in the document text;
- security fields (domains) are read from raw text, not from model output.

**Why these edge cases?**
Each one passes a check that only looks at the single invoice:
- bank change → needs memory of what's on file;
- split PO and near-duplicate → need history;
- the scan → needs OCR, tax reasoning and PO inference.

**How would it scale?**
Postgres instead of SQLite, a task queue instead of one thread, and a lock per PO. The pipeline itself doesn't change.

**What would you add next?**
- Three-way match with goods receipts.
- Integration with the ERP or procurement system.
- Approval limits by amount and by role.
- Learned mappings from vendor SKUs to PO lines.
- A proper vendor bank-change verification workflow.

**What happens with an invoice in a layout it's never seen?**
Extraction is layout-agnostic because the LLM reads the page. The confidence and grounding checks catch weak reads, and those go to review instead of being approved.
