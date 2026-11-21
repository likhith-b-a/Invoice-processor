import { Check, AlertTriangle, X, Loader2, Minus, Mail, Upload, FolderInput, FlaskConical, History, Circle } from "lucide-react";

export const DECISIONS = {
  APPROVE: { label: "Approved", stamp: "Approved", tone: "ok" },
  HOLD: { label: "On hold", stamp: "Hold", tone: "warn" },
  REQUEST_INFO: { label: "Info requested", stamp: "Info needed", tone: "info" },
  REJECT: { label: "Rejected", stamp: "Rejected", tone: "bad" },
  FRAUD_HOLD: { label: "Fraud hold", stamp: "Fraud hold", tone: "bad" },
};

const TONE_VAR = { ok: "var(--ok)", warn: "var(--warn)", bad: "var(--bad)", info: "var(--info)", muted: "var(--ink-3)" };
const TONE_CLS = {
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad",
  info: "bg-info-soft text-info", muted: "bg-muted-soft text-ink-2", carbon: "bg-carbon-soft text-carbon",
};

export function Stamp({ decision, sub, land = false, size = "lg" }) {
  const d = DECISIONS[decision];
  if (!d) return null;
  return (
    <div className={`stamp ${land ? "stamp-land" : ""}`} style={{ "--c": TONE_VAR[d.tone] }} role="status"
      aria-label={`Decision: ${d.label}`}>
      <span style={{ fontSize: size === "lg" ? 26 : 15, letterSpacing: "0.04em" }}>{d.stamp}</span>
      {sub && <span className="num" style={{ fontSize: size === "lg" ? 10.5 : 8.5, fontWeight: 500, letterSpacing: "0.1em" }}>{sub}</span>}
    </div>
  );
}

export function DecisionChip({ decision, reviewed }) {
  const d = DECISIONS[decision];
  if (!d) return <Chip tone="muted">—</Chip>;
  return (
    <Chip tone={d.tone}>
      {d.label}
      {reviewed && <span className="opacity-70 font-normal">· reviewed</span>}
    </Chip>
  );
}

export function Chip({ tone = "muted", children, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11.5px] font-semibold whitespace-nowrap ${TONE_CLS[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function StatusIcon({ status, size = 14 }) {
  const map = {
    ok: [Check, "text-ok bg-ok-soft"], pass: [Check, "text-ok bg-ok-soft"],
    warn: [AlertTriangle, "text-warn bg-warn-soft"], fail: [X, "text-bad bg-bad-soft"],
    skip: [Minus, "text-ink-3 bg-muted-soft"], started: [Loader2, "text-carbon bg-carbon-soft"],
    pending: [Circle, "text-rule-strong bg-transparent"],
  };
  const [Icon, cls] = map[status] || map.pending;
  return (
    <span className={`inline-grid place-items-center rounded-full shrink-0 ${cls}`} style={{ width: size + 8, height: size + 8 }}>
      <Icon size={size} strokeWidth={2.5} className={status === "started" ? "spin" : ""} />
    </span>
  );
}

export function SourceTag({ source, meta }) {
  const map = {
    email: [Mail, "Email"], upload: [Upload, "Upload"], folder: [FolderInput, "Folder"],
    sample: [FlaskConical, "Sample"], seed: [History, "History"],
  };
  const [Icon, label] = map[source] || [Upload, source];
  return (
    <span className="inline-flex items-center gap-1.5 text-ink-2 text-[12.5px]" title={meta?.from || ""}>
      <Icon size={13} /> {label}
    </span>
  );
}

export function money(v, cur) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return cur ? `${cur} ${s}` : s;
}

export function Money({ v, cur, className = "" }) {
  return <span className={`num ${className}`}>{money(v, cur)}</span>;
}

export function moneyMap(m) {
  const entries = Object.entries(m || {});
  if (!entries.length) return "—";
  return entries.map(([c, v]) => money(v, c)).join(" · ");
}

export function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function Button({ variant = "ghost", className = "", children, ...p }) {
  const v = {
    primary: "bg-carbon text-white hover:brightness-110 border-transparent",
    ghost: "bg-sheet text-ink hover:bg-sheet-2 border-rule",
    ok: "bg-ok text-white hover:brightness-110 border-transparent",
    bad: "bg-sheet text-bad hover:bg-bad-soft border-rule",
  }[variant];
  return (
    <button className={`inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-[13px] font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed ${v} ${className}`} {...p}>
      {children}
    </button>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="text-center py-14 px-6">
      <div className="display text-lg mb-1">{title}</div>
      <div className="text-ink-2 max-w-md mx-auto">{children}</div>
    </div>
  );
}
