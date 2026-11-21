import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, ScanLine, FileText, Loader2, ArrowRight } from "lucide-react";
import { api } from "../api";
import { useRuns } from "../App";
import { DECISIONS, DecisionChip, Money, SourceTag, moneyMap, timeAgo, Empty, Button } from "../components/ui";

const FILTERS = [
  ["all", "All"], ["attention", "Needs attention"], ["APPROVE", "Approved"], ["NEEDS_APPROVAL", "Awaiting approval"], ["HOLD", "On hold"],
  ["REQUEST_INFO", "Info requested"], ["FRAUD_HOLD", "Fraud hold"], ["REJECT", "Rejected"],
];

export default function Dashboard() {
  const { runs, fresh, tick } = useRuns();
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState("all");
  const [source, setSource] = useState("all");
  const [q, setQ] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => api.stats().then(setStats).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [tick]);

  const inFlight = runs.filter((r) => r.status === "queued" || r.status === "running");
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return runs.filter((r) => {
      if (!showHistory && r.source === "seed") return false;
      const eff = r.effective_decision;
      if (filter === "attention" && !(r.status === "done" && ["HOLD", "FRAUD_HOLD", "REQUEST_INFO", "NEEDS_APPROVAL"].includes(r.decision) && !r.review_status)) return false;
      if (!["all", "attention"].includes(filter) && eff !== filter) return false;
      if (source !== "all" && r.source !== source) return false;
      if (needle && ![r.vendor_name, r.invoice_number, r.po_number, r.filename].join(" ").toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [runs, filter, source, q, showHistory]);

  const mix = stats?.by_decision || {};
  const mixTotal = Object.values(mix).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow mb-1">Accounts payable</div>
          <h1 className="display text-[28px] leading-none">Invoice ledger</h1>
        </div>
        <Button variant="primary" onClick={() => navigate("/intake")}>Process an invoice <ArrowRight size={15} /></Button>
      </header>

      {/* ledger strip */}
      <section className="sheet grid grid-cols-2 lg:grid-cols-5 divide-x divide-y lg:divide-y-0 divide-rule overflow-hidden">
        <Stat label="Processed" value={stats?.processed ?? "—"} sub={stats ? `${stats.in_flight} in flight · ${stats.errors} errors` : ""} />
        <Stat label="Auto-approved" value={stats ? `${Math.round(stats.auto_approve_rate * 100)}%` : "—"}
          sub="no human touch needed" />
        <Stat label="Needs attention" value={stats?.needs_attention ?? "—"} tone={stats?.needs_attention ? "warn" : null}
          sub={stats ? moneyMap(stats.value_on_hold) : ""} />
        <Stat label="Fraud blocked" value={stats ? moneyMap(stats.fraud_blocked) : "—"} small tone={Object.keys(stats?.fraud_blocked || {}).length ? "bad" : null}
          sub="payment stopped before release" />
        <Stat label="Avg. time per invoice" value={stats ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : "—"}
          sub="PDF to decision" />
      </section>

      {mixTotal > 0 && (
        <section aria-label="Decision mix">
          <div className="flex h-2.5 rounded-full overflow-hidden gap-[2px]">
            {Object.keys(DECISIONS).filter((k) => mix[k]).map((k) => (
              <div key={k} style={{ flex: mix[k], background: `var(--${k === "REJECT" ? "ink-3" : DECISIONS[k].tone})` }}
                title={`${DECISIONS[k].label}: ${mix[k]}`} />
            ))}
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-[12px] text-ink-2">
            {Object.keys(DECISIONS).filter((k) => mix[k]).map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: `var(--${k === "REJECT" ? "ink-3" : DECISIONS[k].tone})` }} />
                {DECISIONS[k].label} <span className="num text-ink">{mix[k]}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      {inFlight.length > 0 && (
        <section className="sheet !border-carbon/40 bg-carbon-soft/40 p-3 flex flex-wrap gap-2 items-center">
          <span className="eyebrow !text-carbon mr-1">Processing now</span>
          {inFlight.map((r) => (
            <Link key={r.id} to={`/runs/${r.id}`} className="inline-flex items-center gap-2 rounded-md bg-sheet border border-rule px-2.5 py-1 hover:border-carbon">
              <Loader2 size={13} className="spin text-carbon" />
              <span className="font-medium">{r.filename}</span>
              <span className="text-ink-3 text-[12px]">{r.current_stage || "queued"}</span>
            </Link>
          ))}
        </section>
      )}

      <section className="sheet overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 p-3 border-b border-rule">
          <div className="flex flex-wrap gap-1" role="tablist">
            {FILTERS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={filter === k} onClick={() => setFilter(k)}
                className={`rounded-md px-2.5 py-1 text-[12.5px] font-medium ${filter === k ? "bg-ink text-sheet" : "text-ink-2 hover:bg-sheet-2"}`}>
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source"
              className="rounded-md border border-rule bg-sheet px-2 py-1 text-[12.5px]">
              <option value="all">All sources</option>
              <option value="email">Email</option>
              <option value="upload">Upload</option>
              <option value="folder">Folder</option>
              <option value="sample">Sample</option>
            </select>
            <label className="relative">
              <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-ink-3" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Vendor, invoice, PO"
                className="rounded-md border border-rule bg-sheet pl-7 pr-2 py-1 text-[12.5px] w-44" />
            </label>
          </div>
        </div>

        {rows.length === 0 ? (
          <Empty title={runs.length ? "Nothing matches these filters" : "No invoices yet"}>
            {runs.length ? "Clear a filter to see more runs." : <>Upload a PDF, drop one in the watched folder, or email it to the AP inbox. <Link className="text-carbon underline" to="/intake">Go to intake</Link></>}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="eyebrow border-b border-rule">
                  <th className="font-normal px-4 py-2">Run</th>
                  <th className="font-normal px-3 py-2">Vendor / invoice</th>
                  <th className="font-normal px-3 py-2">PO</th>
                  <th className="font-normal px-3 py-2 text-right">Total</th>
                  <th className="font-normal px-3 py-2">Decision</th>
                  <th className="font-normal px-3 py-2">Source</th>
                  <th className="font-normal px-4 py-2 text-right">Received</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.id}-${fresh[r.id] || 0}`} onClick={() => navigate(`/runs/${r.id}`)}
                    className={`border-b border-rule last:border-0 cursor-pointer hover:bg-sheet-2 ${fresh[r.id] && Date.now() - fresh[r.id] < 2000 ? "row-flash" : ""}`}>
                    <td className="px-4 py-2.5">
                      <Link to={`/runs/${r.id}`} className="num text-ink-3 hover:text-carbon" onClick={(e) => e.stopPropagation()}>#{r.id}</Link>
                    </td>
                    <td className="px-3 py-2.5 min-w-56">
                      <div className="font-semibold flex items-center gap-1.5">
                        {r.doc_type === "scanned" ? <ScanLine size={13} className="text-ink-3" aria-label="scanned" /> : <FileText size={13} className="text-ink-3" />}
                        {r.vendor_name || r.filename}
                      </div>
                      <div className="num text-[12px] text-ink-3">{r.invoice_number || (r.status === "done" ? "no invoice number" : r.filename)}</div>
                    </td>
                    <td className="px-3 py-2.5 num text-[12.5px]">{r.po_number || <span className="text-ink-3">—</span>}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap"><Money v={r.total || null} cur={r.currency} /></td>
                    <td className="px-3 py-2.5">
                      {r.status === "done" ? <DecisionChip decision={r.effective_decision} reviewed={!!r.review_status} />
                        : r.status === "error" ? <span className="text-bad text-[12px] font-semibold">Error</span>
                        : <span className="inline-flex items-center gap-1.5 text-carbon text-[12px] font-semibold"><Loader2 size={12} className="spin" />{r.current_stage || "Queued"}</span>}
                    </td>
                    <td className="px-3 py-2.5"><SourceTag source={r.source} meta={r.source_meta} /></td>
                    <td className="px-4 py-2.5 text-right text-ink-3 text-[12.5px] whitespace-nowrap">{timeAgo(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="px-4 py-2.5 border-t border-rule text-[12px] text-ink-3 flex justify-between">
          <span>{rows.length} run{rows.length === 1 ? "" : "s"}</span>
          <label className="inline-flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} />
            Show invoices approved before this system (history)
          </label>
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, sub, tone, small }) {
  const c = tone === "warn" ? "text-warn" : tone === "bad" ? "text-bad" : "text-ink";
  return (
    <div className="px-4 py-3.5 min-w-0">
      <div className="eyebrow">{label}</div>
      <div className={`display ${small ? "text-[17px] mt-2" : "text-[26px] mt-1"} leading-tight truncate ${c}`}>{value}</div>
      <div className="text-[11.5px] text-ink-3 truncate mt-0.5">{sub}</div>
    </div>
  );
}
