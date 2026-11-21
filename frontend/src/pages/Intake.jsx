import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Mail, FolderInput, Play, Cpu, RotateCcw } from "lucide-react";
import { api } from "../api";
import { Button, Chip, DECISIONS, money } from "../components/ui";

export default function Intake() {
  const [status, setStatus] = useState(null);
  const [samples, setSamples] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const input = useRef();
  const navigate = useNavigate();

  useEffect(() => {
    const load = () => api.intake().then(setStatus).catch(() => {});
    load();
    api.samples().then(setSamples).catch(() => {});
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const upload = async (files) => {
    const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!pdfs.length) { setErr("Choose a PDF file."); return; }
    setBusy(true); setErr("");
    try {
      const { run_ids } = await api.upload(pdfs);
      navigate(`/runs/${run_ids[0]}`);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  const runSample = async (file) => {
    const { run_id } = await api.runSample(file);
    navigate(`/runs/${run_id}`);
  };

  const em = status?.email;
  const fo = status?.folder;
  const ex = status?.extractors;

  return (
    <div className="space-y-6">
      <header>
        <div className="eyebrow mb-1">Intake</div>
        <h1 className="display text-[28px] leading-none">Get invoices in</h1>
        <p className="text-ink-2 mt-2 max-w-2xl">Invoices arrive three ways. All of them go through the same pipeline and show up in the ledger as they're processed.</p>
      </header>

      <div className="grid lg:grid-cols-3 gap-4">
        <section className="sheet p-5 flex flex-col">
          <SourceHead icon={Upload} title="Upload" live />
          <button onClick={() => input.current?.click()} disabled={busy}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); e.stopPropagation(); upload(e.dataTransfer.files); }}
            className="mt-3 flex-1 min-h-36 rounded-md border-2 border-dashed border-rule-strong hover:border-carbon hover:bg-carbon-soft/40 grid place-items-center p-4 text-center transition">
            <div>
              <div className="font-semibold">{busy ? "Uploading…" : "Choose PDFs or drop them here"}</div>
              <div className="text-[12.5px] text-ink-3 mt-1">Digital or scanned. Several at once is fine.</div>
            </div>
          </button>
          <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => upload(e.target.files)} />
          {err && <div className="text-bad text-[12.5px] mt-2">{err}</div>}
        </section>

        <section className="sheet p-5">
          <SourceHead icon={Mail} title="Email inbox" live={em?.enabled && !em?.last_error} warn={em?.enabled && em?.last_error} />
          {em?.enabled ? (
            <dl className="mt-3 space-y-1.5 text-[13px]">
              <Line k="Mailbox" v={<span className="num">{em.mailbox}</span>} />
              <Line k="Checks every" v={`${em.interval_s}s`} />
              <Line k="Last check" v={em.last_poll || "starting…"} />
              <Line k="Picked up" v={`${em.picked_up} PDF${em.picked_up === 1 ? "" : "s"}`} />
              {em.last_error && <div className="text-bad text-[12px] pt-1">{em.last_error}</div>}
              <p className="text-ink-3 text-[12px] pt-2">Email a PDF invoice to this address. Unread messages with PDF attachments are processed, then marked read.</p>
            </dl>
          ) : (
            <div className="mt-3 text-[13px] text-ink-2 space-y-2">
              <p>Not connected yet. Add a dedicated mailbox to <span className="num">.env</span>:</p>
              <pre className="num text-[11.5px] bg-sheet-2 border border-rule rounded-md p-2.5">IMAP_USER=ap-inbox@gmail.com{"\n"}IMAP_PASSWORD=&lt;16-char app password&gt;</pre>
              <p className="text-ink-3 text-[12px]">Then restart the server.</p>
            </div>
          )}
        </section>

        <section className="sheet p-5">
          <SourceHead icon={FolderInput} title="Watched folder" live={!!fo?.last_scan} />
          <dl className="mt-3 space-y-1.5 text-[13px]">
            <div className="num text-[12px] bg-sheet-2 border border-rule rounded-md p-2 break-all">{fo?.path || "…"}</div>
            <Line k="Last scan" v={fo?.last_scan || "—"} />
            <Line k="Picked up" v={`${fo?.picked_up ?? 0} PDF${fo?.picked_up === 1 ? "" : "s"}`} />
            <p className="text-ink-3 text-[12px] pt-2">Copy a PDF here (or point a scanner or shared drive at it). Processed files move to <span className="num">data/processed</span>.</p>
          </dl>
        </section>
      </div>

      {ex && (
        <section className="sheet px-5 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12.5px]">
          <span className="inline-flex items-center gap-1.5 font-semibold"><Cpu size={14} /> Extraction chain</span>
          <span className="inline-flex items-center gap-1.5">Gemini <span className="num text-ink-3">{ex.gemini_model}</span> {ex.gemini ? <Chip tone="ok">key set</Chip> : <Chip tone="muted">no key</Chip>}</span>
          <span className="text-ink-3">→ cached result → local <span className="num">{ex.ollama_model}</span> → regex parser</span>
          <span className="ml-auto text-ink-3">Queue: <span className="num text-ink">{status.queue}</span></span>
        </section>
      )}

      <section className="sheet overflow-hidden">
        <div className="px-5 py-3.5 border-b border-rule flex items-center justify-between gap-3">
          <div>
            <div className="font-semibold">Test invoices</div>
            <div className="text-[12.5px] text-ink-3">Seven real PDFs covering the happy path and each edge case. Each one runs as a sample with a simulated sender address.</div>
          </div>
          <Button onClick={async () => { if (confirm("Delete all runs and restore the history invoices?")) { await api.reset(); navigate("/"); window.location.reload(); } }}>
            <RotateCcw size={14} /> Reset demo data
          </Button>
        </div>
        <ul className="divide-y divide-rule">
          {samples.map((s) => (
            <li key={s.file} className="px-5 py-3 flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-[13.5px]">{s.title}</div>
                <div className="num text-[11.5px] text-ink-3 truncate">{s.file} · from {s.simulated_sender}</div>
              </div>
              <span className="num text-[12.5px] w-24 text-right">{money(s.total)}</span>
              <span className="w-32 text-[12px] text-ink-3">expect <span className="text-ink font-semibold">{DECISIONS[s.expect]?.label}</span></span>
              <Button variant="primary" onClick={() => runSample(s.file)}><Play size={13} /> Run</Button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function SourceHead({ icon: Icon, title, live, warn }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 font-semibold text-[15px]"><Icon size={17} className="text-carbon" /> {title}</div>
      <span className={`inline-flex items-center gap-1.5 text-[11.5px] font-semibold ${warn ? "text-bad" : live ? "text-ok" : "text-ink-3"}`}>
        <span className={`w-2 h-2 rounded-full ${warn ? "bg-bad" : live ? "bg-ok pulse-dot" : "bg-rule-strong"}`} />
        {warn ? "Error" : live ? "Listening" : "Off"}
      </span>
    </div>
  );
}

function Line({ k, v }) {
  return <div className="flex justify-between gap-3"><dt className="text-ink-3">{k}</dt><dd className="text-right">{v}</dd></div>;
}
