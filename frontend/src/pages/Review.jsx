import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Mail } from "lucide-react";
import { api } from "../api";
import { useRuns } from "../App";
import { Chip, DecisionChip, Empty, Money, timeAgo } from "../components/ui";

const ORDER = { FRAUD_HOLD: 0, HOLD: 1, NEEDS_APPROVAL: 2, REQUEST_INFO: 3 };

export default function Review() {
  const { runs, tick } = useRuns();
  const [drafts, setDrafts] = useState([]);
  const [details, setDetails] = useState({});

  const queue = runs
    .filter((r) => r.status === "done" && r.decision in ORDER && !r.review_status)
    .sort((a, b) => ORDER[a.decision] - ORDER[b.decision] || b.created_at.localeCompare(a.created_at));

  useEffect(() => { api.drafts().then(setDrafts).catch(() => {}); }, [tick]);
  useEffect(() => {
    queue.forEach((r) => {
      if (!details[r.id]) api.run(r.id).then((d) => setDetails((x) => ({ ...x, [r.id]: d })));
    });
  }, [queue.map((r) => r.id).join(",")]); // eslint-disable-line

  const pendingDrafts = drafts.filter((d) => d.status === "draft");

  return (
    <div className="space-y-6">
      <header>
        <div className="eyebrow mb-1">Review queue</div>
        <h1 className="display text-[28px] leading-none">Waiting on a person</h1>
        <p className="text-ink-2 mt-2">Fraud holds first, then reviews, then invoices above the approval limit, then invoices waiting on the vendor.</p>
      </header>

      <section className="sheet overflow-hidden">
        {queue.length === 0 ? (
          <Empty title="Queue is clear">Every processed invoice is either approved, rejected, or already reviewed.</Empty>
        ) : (
          <ul className="divide-y divide-rule">
            {queue.map((r) => {
              const d = details[r.id];
              const issues = d?.rules?.filter((x) => x.status === "warn" || x.status === "fail") || [];
              return (
                <li key={r.id}>
                  <Link to={`/runs/${r.id}`} className="block px-5 py-4 hover:bg-sheet-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <DecisionChip decision={r.decision} />
                      <span className="font-semibold">{r.vendor_name}</span>
                      <span className="num text-[12px] text-ink-3">{r.invoice_number || "no number"}</span>
                      <span className="ml-auto"><Money v={r.total} cur={r.currency} className="font-semibold" /></span>
                      <span className="text-[12px] text-ink-3 w-20 text-right">{timeAgo(r.created_at)}</span>
                    </div>
                    <div className="mt-1.5 text-[13px] text-ink-2">{r.headline}</div>
                    {issues.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {issues.map((x) => <Chip key={x.id} tone={x.status === "fail" ? "bad" : "warn"}><span className="num">{x.id}</span> {x.name}</Chip>)}
                      </div>
                    )}
                    {d?.next_actions?.[0] && <div className="mt-2 text-[12.5px] text-ink">→ {d.next_actions[0]}</div>}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="sheet overflow-hidden">
        <div className="px-5 py-3 border-b border-rule flex items-center gap-2 font-semibold"><Mail size={15} /> Vendor emails waiting to be sent <span className="num text-ink-3 font-normal">{pendingDrafts.length}</span></div>
        {pendingDrafts.length === 0 ? (
          <div className="px-5 py-6 text-ink-3 text-[13px]">No drafts. When an invoice is missing information, a draft request to the vendor appears here for you to check and send.</div>
        ) : (
          <ul className="divide-y divide-rule">
            {pendingDrafts.map((d) => (
              <li key={d.id}>
                <Link to={`/runs/${d.run_id}`} className="block px-5 py-3 hover:bg-sheet-2">
                  <div className="flex gap-3 items-baseline"><span className="num text-[12.5px]">{d.to}</span><span className="text-ink-3 text-[12px] ml-auto">run #{d.run_id}</span></div>
                  <div className="text-[13px] font-semibold mt-0.5">{d.subject}</div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
