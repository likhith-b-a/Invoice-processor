import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useRuns } from "../App";
import { Chip, money } from "../components/ui";

export default function Orders() {
  const { tick } = useRuns();
  const [pos, setPos] = useState([]);
  const [vendors, setVendors] = useState([]);
  useEffect(() => { api.pos().then(setPos); }, [tick]);
  useEffect(() => { api.vendors().then(setVendors); }, []);

  return (
    <div className="space-y-6">
      <header>
        <div className="eyebrow mb-1">Procurement master data</div>
        <h1 className="display text-[28px] leading-none">Purchase orders</h1>
        <p className="text-ink-2 mt-2">Balances update as invoices are approved, by the system or by a reviewer.</p>
      </header>

      <div className="grid xl:grid-cols-2 gap-4">
        {pos.map((p) => {
          const used = p.invoiced_amount / p.total_amount;
          return (
            <section key={p.po_number} className="sheet p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="num font-semibold text-[15px]">{p.po_number}</div>
                  <div className="text-ink-2 text-[13px]">{p.vendor_name}</div>
                </div>
                <div className="text-right">
                  <Chip tone={p.status === "open" ? "ok" : "muted"}>{p.status}</Chip>
                  <div className="num text-[12px] text-ink-3 mt-1">issued {p.issued}</div>
                </div>
              </div>
              <div className="mt-4">
                <div className="flex justify-between text-[12px] mb-1">
                  <span className="text-ink-3">Invoiced <span className="num text-ink">{money(p.invoiced_amount, p.currency)}</span></span>
                  <span className="text-ink-3">of <span className="num text-ink">{money(p.total_amount, p.currency)}</span></span>
                </div>
                <div className="h-2 rounded-full bg-muted-soft overflow-hidden">
                  <div className="h-full" style={{ width: `${Math.min(100, used * 100)}%`, background: used > 1 ? "var(--bad)" : "var(--carbon)" }} />
                </div>
              </div>
              <table className="w-full mt-4 text-[12.5px]">
                <thead><tr className="eyebrow border-b border-rule"><th className="text-left font-normal py-1">Line</th><th className="text-right font-normal">Unit</th><th className="text-right font-normal">Invoiced / ordered</th></tr></thead>
                <tbody>
                  {p.lines.map((l) => (
                    <tr key={l.sku} className="border-b border-rule last:border-0">
                      <td className="py-1.5 pr-2"><span className="num text-[11px] text-ink-3 mr-1.5">{l.sku}</span>{l.description}</td>
                      <td className="text-right num">{money(l.unit_price)}</td>
                      <td className={`text-right num ${l.remaining_qty < 0 ? "text-bad" : ""}`}>{l.invoiced_qty} / {l.quantity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {p.invoices.length > 0 && (
                <div className="mt-3 text-[12px] text-ink-3">
                  Invoices: {p.invoices.map((i, k) => <span key={i.run_id}>{k > 0 && ", "}<Link to={`/runs/${i.run_id}`} className="text-carbon num">{i.invoice_number}</Link></span>)}
                </div>
              )}
            </section>
          );
        })}
      </div>

      <section className="sheet overflow-hidden">
        <div className="px-5 py-3 border-b border-rule font-semibold">Approved vendors</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead><tr className="eyebrow border-b border-rule">
              <th className="text-left font-normal px-5 py-2">Vendor</th><th className="text-left font-normal">Email domain</th>
              <th className="text-left font-normal">Bank account on file</th><th className="text-left font-normal">Terms</th><th className="text-left font-normal px-5">Status</th></tr></thead>
            <tbody>
              {vendors.map((v) => (
                <tr key={v.id} className="border-b border-rule last:border-0">
                  <td className="px-5 py-2"><span className="num text-ink-3 mr-2">{v.id}</span>{v.name}</td>
                  <td className="num">{v.email_domain}</td>
                  <td className="num">{v.bank_name} ••••{v.bank_account.replace(/[^0-9A-Z]/gi, "").slice(-4)}</td>
                  <td>{v.payment_terms}</td>
                  <td className="px-5"><Chip tone={v.status === "active" ? "ok" : "muted"}>{v.status}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
