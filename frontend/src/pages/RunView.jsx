import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, RotateCcw, Send, Trash2, Mail, ShieldAlert, FileText, ChevronRight } from "lucide-react";
import { api, fileUrl } from "../api";
import DocViewer from "../components/DocViewer";
import { Stamp, StatusIcon, Chip, Money, money, SourceTag, Button, DECISIONS, timeAgo } from "../components/ui";

const STAGES = [
  ["intake", "Intake", "File received and fingerprinted"],
  ["detect", "Document type", "Text layer or scanned image"],
  ["ocr", "OCR", "Read scanned pages locally"],
  ["extract", "Field extraction", "LLM reads fields into JSON"],
  ["normalize", "Normalize", "Amounts, dates, tax, grounding"],
  ["vendor", "Vendor verification", "Master data, bank, domain"],
  ["match", "PO matching", "Explicit or inferred PO, line match"],
  ["validate", "Validation rules", "15 deterministic checks"],
  ["decide", "Decision", "Outcome, reasons, next steps"],
];

export default function RunView() {
  const { id } = useParams();
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [justLanded, setJustLanded] = useState(false);
  const [hl, setHl] = useState(null);
  const pinned = useRef(false);

  useEffect(() => {
    let es;
    setEvents([]);
    setRun(null);
    setSelected(null);
    pinned.current = false;
    api.run(id).then((r) => {
      setRun(r);
      setEvents(r.events);
      if (r.status === "done" || r.status === "error") return;
      es = new EventSource(`/api/runs/${id}/stream`);
      es.addEventListener("stage", (e) => {
        const ev = JSON.parse(e.data);
        setEvents((prev) => (prev.some((p) => p.id === ev.id) ? prev : [...prev, ev]));
        if (!pinned.current) setSelected(ev.stage);
        setRun((r0) => (r0 ? { ...r0, status: "running", current_stage: ev.stage } : r0));
      });
      es.addEventListener("done", (e) => {
        const full = JSON.parse(e.data);
        setRun(full);
        setEvents(full.events);
        setJustLanded(true);
        if (!pinned.current) setSelected(null);
        es.close();
      });
    });
    return () => es && es.close();
  }, [id]);

  const stageState = useMemo(() => {
    const m = {};
    for (const e of events) m[e.stage] = e;
    return m;
  }, [events]);

  if (!run) return <div className="text-ink-3 py-20 text-center">Loading run #{id}…</div>;

  const done = run.status === "done";
  const errored = run.status === "error";
  const view = selected || (done ? "decide" : run.current_stage || "intake");
  const reload = () => api.run(id).then((r) => { setRun(r); setEvents(r.events); });
  const pick = (k) => { pinned.current = true; setSelected(k); };
  const pickField = async (label, value) => {
    setHl({ label, value, loading: true, boxes: [] });
    try {
      const r = await fetch(`/api/runs/${run.id}/locate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }) });
      const d = await r.json();
      setHl({ label, value, boxes: d.boxes || [] });
    } catch { setHl({ label, value, boxes: [] }); }
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start gap-4 justify-between">
        <div className="min-w-0">
          <Link to="/" className="inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-carbon mb-1.5">
            <ArrowLeft size={13} /> Invoice ledger
          </Link>
          <h1 className="display text-[24px] leading-tight break-words">
            {run.vendor_name || run.filename}
            {run.invoice_number && <span className="num text-ink-3 text-[16px] font-medium ml-2">{run.invoice_number}</span>}
          </h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-[12.5px] text-ink-2">
            <span className="num text-ink-3">Run #{run.id}</span>
            <SourceTag source={run.source} meta={run.source_meta} />
            {run.source_meta?.from && (
              <span className="inline-flex items-center gap-1"><Mail size={12} /> {run.source_meta.from}
                {run.source_meta.simulated && <span className="text-ink-3">(simulated sender)</span>}
                {run.source_meta.internal_forward && <span className="text-ink-3">(forwarded by AP — sender-domain check skipped, invoice domains still checked)</span>}</span>
            )}
            {run.source_meta?.subject && <span className="truncate max-w-72">“{run.source_meta.subject}”</span>}
            <span>{timeAgo(run.created_at)}</span>
            {done && <span className="num">{(run.duration_ms / 1000).toFixed(1)}s end-to-end</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(done || errored) && run.source !== "seed" && (
            <Button onClick={() => api.rerun(run.id).then(() => window.location.reload())}>
              <RotateCcw size={14} /> Run again
            </Button>
          )}
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[300px_minmax(0,1fr)_440px] items-start">
        {/* routing slip */}
        <ol className="sheet slip pl-7 pr-2 py-2 lg:sticky lg:top-6" aria-label="Pipeline stages">
          <div className="eyebrow px-2 pt-1.5 pb-2">Routing slip</div>
          {STAGES.map(([key, name, hint], i) => {
            const ev = stageState[key];
            const status = ev ? ev.status : "pending";
            const active = view === key;
            return (
              <li key={key}>
                <button onClick={() => ev && pick(key)} disabled={!ev}
                  className={`w-full text-left flex gap-2.5 rounded-md px-2 py-2 transition ${active ? "bg-carbon-soft" : ev ? "hover:bg-sheet-2" : "opacity-55"}`}
                  aria-current={active ? "step" : undefined}>
                  <div className="flex flex-col items-center">
                    <StatusIcon status={status} size={12} />
                    {i < STAGES.length - 1 && <span className={`w-px flex-1 mt-1 ${ev && status !== "started" ? "bg-rule-strong" : "bg-rule"}`} />}
                  </div>
                  <div className="min-w-0 flex-1 pb-0.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className={`font-semibold text-[13px] ${active ? "text-carbon" : ""}`}>{name}</span>
                      {ev?.duration_ms > 0 && <span className="num text-[10.5px] text-ink-3">{fmtMs(ev.duration_ms)}</span>}
                    </div>
                    <div className="text-[12px] text-ink-2 leading-snug line-clamp-2">
                      {ev && ev.status !== "started" ? ev.title : status === "started" ? "Working…" : hint}
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
          {errored && <div className="m-2 rounded-md bg-bad-soft text-bad p-2 text-[12.5px]">Run failed: {run.error}</div>}
        </ol>

        {/* main panel */}
        <div className="space-y-5 min-w-0">
          {done && (view === "decide") ? (
            <DecisionPanel run={run} land={justLanded} onChange={reload} />
          ) : (
            <StagePanel stage={view} ev={stageState[view]} run={run} onPickField={pickField} activeField={hl?.label} />
          )}
          {done && view !== "decide" && (
            <button onClick={() => pick("decide")} className="text-carbon text-[13px] font-semibold inline-flex items-center gap-1">
              Back to decision <ChevronRight size={14} />
            </button>
          )}
        </div>

        {/* document */}
        <div className="lg:col-span-2 2xl:col-span-1 2xl:sticky 2xl:top-6">
          <DocViewer run={run} highlight={hl} onClear={() => setHl(null)} />
        </div>
      </div>
    </div>
  );
}

function fmtMs(ms) { return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`; }

/* ------------------------------------------------------------------ decision */
function DecisionPanel({ run, land, onChange }) {
  const d = DECISIONS[run.decision];
  const eff = run.effective_decision;
  const rulesBad = (run.rules || []).filter((r) => r.status === "warn" || r.status === "fail");
  const counts = (run.rules || []).reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {});
  return (
    <div className="space-y-5">
      <section className="sheet p-5 sm:p-6 relative overflow-hidden">
        <div className="flex flex-col-reverse sm:flex-row gap-5 sm:items-start justify-between">
          <div className="min-w-0">
            <div className="eyebrow mb-1.5">Decision</div>
            <h2 className="display text-[20px] leading-snug">{run.headline}</h2>
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-[12.5px] text-ink-2">
              <span>Total <Money v={run.total} cur={run.currency} className="text-ink font-semibold" /></span>
              {run.po_number && <span>PO <span className="num text-ink">{run.po_number}</span>
                {run.match?.method === "inferred" && <Chip tone="carbon" className="ml-1.5">inferred</Chip>}</span>}
              <span>Checks <span className="num text-ok">{counts.pass || 0} pass</span> · <span className="num text-warn">{counts.warn || 0} warn</span> · <span className="num text-bad">{counts.fail || 0} fail</span></span>
              <span>Read by <span className="num text-ink">{run.extractor}</span></span>
            </div>
          </div>
          <div className="shrink-0 sm:pr-2 sm:pt-1 self-start">
            <Stamp decision={run.decision} land={land} sub={new Date(run.updated_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase()} />
          </div>
        </div>

        {run.review_status && (
          <div className={`mt-4 rounded-md p-3 text-[13px] ${eff === "APPROVE" ? "bg-ok-soft" : "bg-bad-soft"}`}>
            <span className="font-semibold">{run.review_status === "approved" ? "Approved" : "Rejected"} by {(run.approvals || []).filter((a) => a.action === (run.review_status === "approved" ? "approve" : "reject")).map((a) => `${a.name} (${a.role === "finance_manager" ? "Finance manager" : "AP reviewer"})`).join(" + ") || "reviewer"}</span> — final status: {DECISIONS[eff]?.label}.
            {run.review_comment && <span className="text-ink-2"> “{run.review_comment}”</span>}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-5 mt-5">
          <div>
            <div className="eyebrow mb-2">Why</div>
            <ul className="space-y-2">
              {(rulesBad.length ? rulesBad : []).map((r) => (
                <li key={r.id} className="flex gap-2.5">
                  <StatusIcon status={r.status} size={11} />
                  <div className="text-[13px] leading-snug">
                    <span className="num text-[11px] text-ink-3 mr-1.5">{r.id}</span>
                    <span className="font-semibold">{r.name}.</span> <span className="text-ink-2">{r.message}</span>
                  </div>
                </li>
              ))}
              {!rulesBad.length && run.explanation?.map((e, i) => (
                <li key={i} className="flex gap-2.5"><StatusIcon status="ok" size={11} /><span className="text-[13px] text-ink-2 leading-snug">{e}</span></li>
              ))}
            </ul>
          </div>
          <div>
            <div className="eyebrow mb-2">Next steps</div>
            <ol className="space-y-2">
              {run.next_actions?.map((a, i) => (
                <li key={i} className="flex gap-2.5 text-[13px] leading-snug">
                  <span className="num text-[11px] text-ink-3 mt-0.5">{i + 1}.</span><span>{a}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        {run.decision === "FRAUD_HOLD" && <FraudCompare run={run} />}
      </section>

      {run.source !== "seed" && ["HOLD", "FRAUD_HOLD", "REQUEST_INFO", "NEEDS_APPROVAL"].includes(run.decision) && !run.review_status && (
        <ReviewBox run={run} onChange={onChange} />
      )}

      {run.drafts?.length > 0 && run.drafts.map((dr) => <DraftBox key={dr.id} draft={dr} onChange={onChange} />)}

      <section className="sheet p-5">
        <div className="eyebrow mb-3">All checks</div>
        <RulesTable rules={run.rules} />
      </section>

      <section className="sheet p-5">
        <div className="eyebrow mb-3">Audit trail</div>
        <ol className="space-y-1.5 text-[12.5px]">
          {run.audit?.map((a) => (
            <li key={a.id} className="flex gap-3">
              <span className="num text-ink-3 w-36 shrink-0">{new Date(a.ts).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
              <span className="w-20 shrink-0 text-ink-2">{a.actor}</span>
              <span><span className="font-semibold">{a.action.replaceAll("_", " ")}</span> <span className="text-ink-2">{a.note}</span></span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function FraudCompare({ run }) {
  const v = run.events?.find((e) => e.stage === "vendor" && e.status !== "started")?.detail || {};
  return (
    <div className="mt-5 rounded-md border border-bad/40 bg-bad-soft/50 p-4">
      <div className="flex items-center gap-2 text-bad font-semibold mb-3"><ShieldAlert size={16} /> Payment details don't match what we have on file</div>
      <div className="grid sm:grid-cols-2 gap-3 text-[13px]">
        <Compare label="Bank account" file={v.bank_on_file} seen={v.bank_on_invoice} bad={v.bank_status === "mismatch"} />
        <Compare label="Email domain" file={v.official_domain} seen={[v.invoice_email_domain, v.sender_domain].filter(Boolean).filter((x, i, a) => a.indexOf(x) === i).join(", ")}
          bad={[v.invoice_domain_relation, v.sender_domain_relation].includes("lookalike")} />
      </div>
    </div>
  );
}

function Compare({ label, file, seen, bad }) {
  return (
    <div className="sheet p-3">
      <div className="eyebrow mb-1.5">{label}</div>
      <div className="flex justify-between gap-2"><span className="text-ink-3">On file</span><span className="num">{file || "—"}</span></div>
      <div className="flex justify-between gap-2"><span className="text-ink-3">On this invoice</span><span className={`num ${bad ? "text-bad font-semibold" : ""}`}>{seen || "—"}</span></div>
    </div>
  );
}

function ReviewBox({ run, onChange }) {
  const steps = run.approval_progress?.steps || [];
  const needsManager = steps.some((x) => x.role === "finance_manager" && !x.by);
  const [comment, setComment] = useState("");
  const [name, setName] = useState(() => { try { return localStorage.getItem("approver") || ""; } catch { return ""; } });
  const [role, setRole] = useState(() => (steps.find((x) => !x.by)?.role || "reviewer"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const act = async (a) => {
    setBusy(true); setErr("");
    try { localStorage.setItem("approver", name); } catch {}
    try { await api.review(run.id, a, comment, name, role); setComment(""); await onChange(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <section className="sheet p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <div className="eyebrow">Sign-off</div>
        {steps.length > 1 && <span className="text-[12px] text-ink-3">Four-eyes rule: two different people</span>}
      </div>
      {steps.length > 0 && (
        <ol className="flex flex-wrap gap-2 mb-4">
          {steps.map((st, i) => (
            <li key={i} className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-[12.5px] ${st.by ? "border-ok/40 bg-ok-soft" : "border-rule"}`}>
              <StatusIcon status={st.by ? "ok" : "pending"} size={10} />
              <span className="font-semibold">{st.label}</span>
              <span className="text-ink-2">{st.by ? `approved by ${st.by}` : "waiting"}</span>
            </li>
          ))}
        </ol>
      )}
      <div className="grid sm:grid-cols-[1fr_200px] gap-2 mb-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name"
          className="rounded-md border border-rule bg-sheet-2 px-2.5 py-1.5 text-[13px]" aria-label="Your name" />
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Your role"
          className="rounded-md border border-rule bg-sheet-2 px-2 py-1.5 text-[13px]">
          <option value="reviewer">AP reviewer</option>
          <option value="finance_manager">Finance manager</option>
        </select>
      </div>
      <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2}
        placeholder={run.decision === "FRAUD_HOLD" ? "e.g. Called Acme on the number on file — bank change not genuine" : "Add a note for the audit trail"}
        className="w-full rounded-md border border-rule bg-sheet-2 p-2.5 text-[13px]" aria-label="Review comment" />
      {needsManager && role !== "finance_manager" && steps.every((x) => x.role === "finance_manager" || x.by) && (
        <div className="text-[12.5px] text-warn mt-1.5">Only a finance manager can give the remaining approval.</div>
      )}
      {err && <div className="text-[12.5px] text-bad mt-1.5">{err}</div>}
      <div className="flex flex-wrap gap-2 mt-2.5">
        <Button variant="ok" disabled={busy || !name.trim()} onClick={() => act("approve")}>Approve for payment</Button>
        <Button variant="bad" disabled={busy || !name.trim()} onClick={() => act("reject")}>Reject invoice</Button>
      </div>
    </section>
  );
}

function DraftBox({ draft, onChange }) {
  const [d, setD] = useState(draft);
  const [busy, setBusy] = useState(false);
  useEffect(() => setD(draft), [draft]);
  const editable = d.status === "draft" || d.status === "failed";
  const save = () => api.editDraft(d.id, { to: d.to, subject: d.subject, body: d.body });
  const send = async () => { setBusy(true); try { await save(); await api.sendDraft(d.id); await onChange(); } finally { setBusy(false); } };
  const discard = async () => { setBusy(true); try { await api.discardDraft(d.id); await onChange(); } finally { setBusy(false); } };
  return (
    <section className="sheet p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="eyebrow">Email to vendor</div>
        <Chip tone={{ draft: "carbon", sent: "ok", failed: "bad", discarded: "muted" }[d.status]}>
          {{ draft: "Draft — not sent", sent: "Sent", failed: "Send failed", discarded: "Discarded" }[d.status]}
        </Chip>
      </div>
      <div className="space-y-2 text-[13px]">
        <label className="flex items-center gap-2"><span className="w-14 text-ink-3">To</span>
          <input disabled={!editable} value={d.to} onChange={(e) => setD({ ...d, to: e.target.value })} className="flex-1 rounded-md border border-rule bg-sheet-2 px-2 py-1.5 num" /></label>
        <label className="flex items-center gap-2"><span className="w-14 text-ink-3">Subject</span>
          <input disabled={!editable} value={d.subject} onChange={(e) => setD({ ...d, subject: e.target.value })} className="flex-1 rounded-md border border-rule bg-sheet-2 px-2 py-1.5" /></label>
        <textarea disabled={!editable} rows={9} value={d.body} onChange={(e) => setD({ ...d, body: e.target.value })}
          className="w-full rounded-md border border-rule bg-sheet-2 p-2.5 leading-relaxed" aria-label="Email body" />
      </div>
      {d.error && <div className="text-bad text-[12.5px] mt-2">{d.error}</div>}
      {editable && (
        <div className="flex gap-2 mt-2.5">
          <Button variant="primary" disabled={busy} onClick={send}><Send size={14} /> Send email</Button>
          <Button disabled={busy} onClick={discard}><Trash2 size={14} /> Discard</Button>
        </div>
      )}
      {d.status === "sent" && <div className="text-[12.5px] text-ink-3 mt-2">Sent {timeAgo(d.sent_at)}. The vendor's reply with a corrected PDF will be picked up from the inbox automatically.</div>}
    </section>
  );
}

/* ------------------------------------------------------------------ stage detail */
function StagePanel({ stage, ev, run, onPickField, activeField }) {
  const meta = STAGES.find((s) => s[0] === stage);
  if (!ev) return <section className="sheet p-6 text-ink-3">Waiting for {meta?.[1] || stage}…</section>;
  const d = ev.detail || {};
  return (
    <section className="sheet p-5 sm:p-6">
      <div className="flex items-start gap-3 mb-4">
        <StatusIcon status={ev.status} size={14} />
        <div className="min-w-0">
          <div className="eyebrow">{meta?.[1]}</div>
          <h2 className="display text-[18px] leading-snug">{ev.status === "started" ? "Working…" : ev.title}</h2>
        </div>
      </div>
      {ev.status === "started" ? <div className="h-24 rounded-md bg-sheet-2 animate-pulse" /> : (
        <>
          {stage === "intake" && <KV obj={d} />}
          {stage === "detect" && <KV obj={d} />}
          {stage === "ocr" && <OcrView d={d} />}
          {stage === "extract" && <ExtractView d={d} onPick={onPickField} active={activeField} />}
          {stage === "normalize" && <NormalizeView d={d} />}
          {stage === "vendor" && <VendorView d={d} />}
          {stage === "match" && <MatchView d={d} currency={run.currency} />}
          {stage === "validate" && <RulesTable rules={d.rules} />}
          {stage === "decide" && <KV obj={{ decision: d.decision, headline: d.headline }} />}
          {stage === "error" && <pre className="text-bad text-[12px] whitespace-pre-wrap">{d.error}</pre>}
        </>
      )}
    </section>
  );
}

function KV({ obj }) {
  return (
    <dl className="grid grid-cols-[minmax(120px,auto)_1fr] gap-x-6 gap-y-1.5 text-[13px]">
      {Object.entries(obj || {}).map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-3">{k.replaceAll("_", " ")}</dt>
          <dd className="num break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Conf({ v }) {
  if (v === null || v === undefined) return <span className="text-ink-3">—</span>;
  const tone = v >= 0.85 ? "var(--ok)" : v >= 0.6 ? "var(--warn)" : "var(--bad)";
  return (
    <span className="inline-flex items-center gap-1.5" title={`confidence ${Math.round(v * 100)}%`}>
      <span className="w-12 h-1.5 rounded-full bg-muted-soft overflow-hidden"><span className="block h-full" style={{ width: `${v * 100}%`, background: tone }} /></span>
      <span className="num text-[11px] text-ink-3 w-8">{Math.round(v * 100)}%</span>
    </span>
  );
}

function OcrView({ d }) {
  if (!d.avg_confidence) return <Pre text={d.preview} label="Text layer preview" />;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-[13px]"><span className="text-ink-3">Average confidence</span><Conf v={d.avg_confidence} /></div>
      {d.low_confidence_words?.length > 0 && (
        <div>
          <div className="eyebrow mb-1.5">Low-confidence words</div>
          <div className="flex flex-wrap gap-1.5">{d.low_confidence_words.map((w, i) => <Chip key={i} tone="warn">{w.text} <span className="num opacity-70">{Math.round(w.score * 100)}%</span></Chip>)}</div>
        </div>
      )}
      <Pre text={d.preview} label="OCR output (reading order)" />
    </div>
  );
}

function Pre({ text, label }) {
  return (
    <div>
      <div className="eyebrow mb-1.5">{label}</div>
      <pre className="num text-[11.5px] leading-relaxed bg-sheet-2 border border-rule rounded-md p-3 max-h-80 overflow-auto whitespace-pre-wrap">{text}</pre>
    </div>
  );
}

function ExtractView({ d, onPick, active }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="eyebrow mb-1.5">Extractor chain</div>
        <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
          {d.attempts?.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-1.5">
              {i > 0 && <ChevronRight size={13} className="text-ink-3" />}
              <Chip tone={a.ok ? "ok" : "bad"}><span className="num">{a.extractor}</span> {a.ok ? `✓ ${fmtMs(a.ms)}` : "✗"}</Chip>
              {!a.ok && <span className="text-ink-3 text-[11.5px] max-w-64 truncate" title={a.error}>{shortErr(a.error)}</span>}
            </span>
          ))}
        </div>
      </div>
      <div className="text-[12px] text-ink-3">Click a value to highlight where it was read on the page.</div>
      <table className="w-full text-[13px]">
        <thead><tr className="eyebrow border-b border-rule"><th className="text-left font-normal py-1.5">Field</th><th className="text-left font-normal">Value</th><th className="text-left font-normal w-28">Confidence</th></tr></thead>
        <tbody>
          {d.fields?.map((f) => (
            <tr key={f.field} className={`border-b border-rule last:border-0 ${active === f.field.replaceAll("_", " ") ? "bg-carbon-soft" : ""}`}>
              <td className="py-1.5 text-ink-2">{f.field.replaceAll("_", " ")}</td>
              <td className="num break-all pr-3">{f.value === null || f.value === undefined ? <span className="text-ink-3">not found</span>
                : typeof f.value === "boolean" ? String(f.value)
                : <button onClick={() => onPick?.(f.field.replaceAll("_", " "), f.value)} title="Show on page"
                    className="text-left underline decoration-dotted decoration-ink-3 underline-offset-4 hover:text-carbon hover:decoration-carbon">{String(f.value)}</button>}</td>
              <td><Conf v={f.confidence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function shortErr(e = "") {
  if (e.includes("429")) return "quota exhausted";
  if (e.includes("timed out") || e.includes("connect")) return "not running";
  if (e.includes("not pulled")) return "model not installed";
  return e.slice(0, 60);
}

function NormalizeView({ d }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-3">
        {[["Net subtotal", d.subtotal], [d.tax_inclusive ? "Tax (embedded)" : "Tax", d.tax_amount], ["Total", d.total]].map(([l, v]) => (
          <div key={l} className="rounded-md bg-sheet-2 border border-rule p-3">
            <div className="eyebrow">{l}</div>
            <div className="num text-[16px] font-semibold mt-1">{money(v, d.currency)}</div>
          </div>
        ))}
      </div>
      {d.notes?.length > 0 && (
        <ul className="space-y-1.5 text-[13px]">
          {d.notes.map((n, i) => <li key={i} className="flex gap-2"><span className="text-carbon">→</span><span>{n}</span></li>)}
        </ul>
      )}
      {d.grounding && Object.keys(d.grounding).length > 0 && (
        <div>
          <div className="eyebrow mb-1.5">Grounding — value found verbatim in document text</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(d.grounding).map(([k, ok]) => <Chip key={k} tone={ok ? "ok" : "bad"}>{ok ? "✓" : "✗"} {k.replaceAll("_", " ")}</Chip>)}
          </div>
        </div>
      )}
    </div>
  );
}

function VendorView({ d }) {
  if (!d.found) return (
    <div className="text-[13px]">
      <p className="mb-3">No approved vendor matched. Closest candidates:</p>
      {d.candidates?.map((c) => <div key={c.id} className="flex justify-between border-b border-rule py-1.5"><span>{c.name}</span><span className="num">{c.score}%</span></div>)}
    </div>
  );
  const rel = (r) => ({ exact: ["ok", "matches"], lookalike: ["bad", "lookalike!"], different: ["warn", "different"], none: ["muted", "n/a"] }[r] || ["muted", r]);
  return (
    <div className="grid sm:grid-cols-2 gap-4 text-[13px]">
      <div className="rounded-md border border-rule p-3.5">
        <div className="eyebrow mb-1.5">Master record</div>
        <div className="font-semibold">{d.vendor_name} <span className="num text-ink-3 font-normal">{d.vendor_id}</span></div>
        <div className="text-ink-2 mt-1">Status: {d.status} · match {d.score}%</div>
        <div className="flex flex-wrap gap-1 mt-2">{d.evidence?.map((e) => <Chip key={e} tone="ok">{e}</Chip>)}</div>
      </div>
      <div className="rounded-md border border-rule p-3.5 space-y-1.5">
        <div className="eyebrow mb-1">Bank account</div>
        <Row k="On file" v={d.bank_on_file} />
        <Row k="On invoice" v={d.bank_on_invoice || "not printed"} tone={d.bank_status === "mismatch" ? "text-bad font-semibold" : ""} />
        {d.bank_change_notice && <Chip tone="bad">Invoice announces new bank details</Chip>}
      </div>
      <div className="rounded-md border border-rule p-3.5 space-y-1.5 sm:col-span-2">
        <div className="eyebrow mb-1">Email domains</div>
        <Row k="Vendor's real domain" v={d.official_domain} />
        <Row k="On invoice" v={<>{d.invoice_email_domain || "—"} <Chip tone={rel(d.invoice_domain_relation)[0]}>{rel(d.invoice_domain_relation)[1]}</Chip></>} />
        <Row k="Email sender" v={<>{d.sender_domain || "—"} <Chip tone={rel(d.sender_domain_relation)[0]}>{rel(d.sender_domain_relation)[1]}</Chip></>} />
      </div>
    </div>
  );
}

function Row({ k, v, tone = "" }) {
  return <div className="flex justify-between gap-3"><span className="text-ink-3">{k}</span><span className={`num text-right ${tone}`}>{v}</span></div>;
}

function MatchView({ d, currency }) {
  if (!d.found) return (
    <div className="text-[13px] space-y-3">
      <p>{d.reason}</p>
      {d.candidates && <Candidates c={d.candidates} />}
    </div>
  );
  const prev = d.previously_invoiced || 0;
  const self = d.lines?.reduce((a, l) => a + (l.amount || 0), 0) || 0;
  const total = d.po_total;
  const scale = Math.max(total, prev + self);
  const over = prev + self - total;
  return (
    <div className="space-y-5 text-[13px]">
      <p className="text-ink-2">{d.reason}</p>
      {d.candidates && <Candidates c={d.candidates} />}

      <div>
        <div className="flex justify-between items-baseline mb-1.5">
          <span className="eyebrow">PO balance — {d.po_number}</span>
          <span className="num text-[12px]">{money(prev + self, currency)} / {money(total, currency)}</span>
        </div>
        <div className="relative h-5 rounded bg-muted-soft overflow-hidden flex">
          <div style={{ width: `${(prev / scale) * 100}%` }} className="bg-ink-3/60" title="previously invoiced" />
          <div style={{ width: `${(Math.min(self, Math.max(0, total - prev)) / scale) * 100}%`, background: "var(--carbon)" }} title="this invoice" />
          {over > 0 && <div style={{ width: `${(over / scale) * 100}%`, background: "var(--bad)" }} title="overrun" />}
          <div className="absolute top-0 bottom-0 w-px bg-ink" style={{ left: `${(total / scale) * 100}%` }} />
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-[11.5px] text-ink-2">
          <Legend c="color-mix(in srgb, var(--ink-3) 60%, transparent)">Earlier invoices {money(prev)} ({d.previous_invoices?.length || 0})</Legend>
          <Legend c="var(--carbon)">This invoice {money(self)}</Legend>
          {over > 0 && <Legend c="var(--bad)">Over PO by {money(over)}</Legend>}
        </div>
        {d.previous_invoices?.length > 0 && (
          <div className="mt-2 text-[12px] text-ink-3">
            Earlier: {d.previous_invoices.map((p, i) => <span key={p.run_id}>{i > 0 && ", "}<Link className="text-carbon num" to={`/runs/${p.run_id}`}>{p.invoice_number}</Link> ({money(p.subtotal)})</span>)}
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead><tr className="eyebrow border-b border-rule">
            <th className="text-left font-normal py-1.5">Invoice line</th><th className="text-left font-normal">Matched PO line</th>
            <th className="text-right font-normal">Qty / left</th><th className="text-right font-normal">Unit vs PO</th></tr></thead>
          <tbody>
            {d.lines?.map((l, i) => {
              const overQ = l.po_sku && l.quantity > l.remaining_qty;
              const badP = l.price_delta_pct !== null && l.price_delta_pct !== undefined && Math.abs(l.price_delta_pct) > 2;
              return (
                <tr key={i} className="border-b border-rule last:border-0 align-top">
                  <td className="py-2 pr-3">{l.description}</td>
                  <td className="py-2 pr-3">{l.po_sku ? <><span className="num text-[11.5px] text-ink-3">{l.po_sku}</span> <span className="text-ink-2">{l.po_description}</span> <span className="num text-[11px] text-ink-3">({Math.round(l.score * 100)}%)</span></> : <Chip tone="warn">not on PO</Chip>}</td>
                  <td className={`py-2 text-right num whitespace-nowrap ${overQ ? "text-bad font-semibold" : ""}`}>{l.quantity} / {l.remaining_qty ?? "—"}</td>
                  <td className={`py-2 text-right num whitespace-nowrap ${badP ? "text-bad font-semibold" : ""}`}>{money(l.unit_price)} {l.po_unit_price !== undefined && <span className="text-ink-3">/ {money(l.po_unit_price)}</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Legend({ c, children }) {
  return <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />{children}</span>;
}

function Candidates({ c }) {
  return (
    <div>
      <div className="eyebrow mb-1.5">Candidate POs scored</div>
      <div className="space-y-1.5">
        {c.map((x) => (
          <div key={x.po_number} className="grid grid-cols-[80px_1fr_48px] items-center gap-3">
            <span className="num text-[12.5px]">{x.po_number}</span>
            <span className="h-2 rounded-full bg-muted-soft overflow-hidden"><span className="block h-full bg-carbon" style={{ width: `${x.score * 100}%` }} /></span>
            <span className="num text-[12px] text-right">{x.score.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className="text-[11.5px] text-ink-3 mt-1.5">Score = 55% line-description match + 25% unit-price fit + 20% fits remaining PO balance</div>
    </div>
  );
}

function RulesTable({ rules = [] }) {
  return (
    <ul className="divide-y divide-rule">
      {rules.map((r) => (
        <li key={r.id} className="flex gap-3 py-2">
          <StatusIcon status={r.status} size={11} />
          <span className="num text-[11px] text-ink-3 w-7 mt-0.5 shrink-0">{r.id}</span>
          <div className="min-w-0 text-[13px] leading-snug">
            <span className="font-semibold">{r.name}</span>
            {r.outcome && <Chip tone={{ fraud: "bad", reject: "bad", request_info: "info", review: "warn" }[r.outcome]} className="ml-2">{r.outcome.replace("_", " ")}</Chip>}
            <div className="text-ink-2">{r.message}</div>
            {r.id === "R14" && r.data?.matches?.[0] && (
              <Link to={`/runs/${r.data.matches[0].run_id}`} className="text-carbon text-[12px]">Open earlier invoice {r.data.matches[0].invoice_number} →</Link>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
