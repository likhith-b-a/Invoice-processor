import { useEffect, useRef, useState } from "react";
import { FileText, Crosshair, X } from "lucide-react";
import { fileUrl } from "../api";

/** Page images with highlight boxes for the field the user picked. */
export default function DocViewer({ run, highlight, onClear }) {
  const [pages, setPages] = useState(0);
  const firstHit = useRef(null);

  useEffect(() => {
    fetch(`/api/runs/${run.id}/pages`).then((r) => r.json()).then((d) => setPages(d.pages)).catch(() => setPages(1));
  }, [run.id]);

  useEffect(() => {
    if (highlight?.boxes?.length && firstHit.current) {
      firstHit.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlight]);

  const boxes = highlight?.boxes || [];
  let firstAssigned = false;

  return (
    <section className="sheet overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-rule">
        <span className="eyebrow">Source document</span>
        <a href={fileUrl(run.id)} target="_blank" rel="noreferrer" className="text-[12px] text-carbon inline-flex items-center gap-1 min-w-0">
          <FileText size={12} className="shrink-0" /> <span className="truncate">{run.filename}</span>
        </a>
      </div>

      <div className={`px-3 py-2 border-b border-rule text-[12px] flex items-center gap-2 ${highlight ? "bg-carbon-soft" : "text-ink-3"}`}>
        <Crosshair size={13} className={highlight ? "text-carbon" : ""} />
        {highlight ? (
          <>
            <span className="min-w-0 truncate">
              <span className="font-semibold text-ink">{highlight.label}</span>{" "}
              <span className="num">{String(highlight.value)}</span>{" "}
              <span className="text-ink-2">— {highlight.loading ? "locating…" : boxes.length ? `found in ${boxes.length} place${boxes.length > 1 ? "s" : ""}` : "not found verbatim on the page"}</span>
            </span>
            <button onClick={onClear} className="ml-auto text-ink-3 hover:text-ink" aria-label="Clear highlight"><X size={14} /></button>
          </>
        ) : (
          <span>Click a field in <b>Field extraction</b> to see where it was read on the page.</span>
        )}
      </div>

      <div className="max-h-[78vh] overflow-auto bg-sheet-2 p-3 space-y-3">
        {Array.from({ length: pages }).map((_, p) => (
          <div key={p} className="relative shadow-sm border border-rule bg-white">
            <img src={`/api/runs/${run.id}/page/${p}.png`} alt={`Page ${p + 1} of ${run.filename}`} className="block w-full h-auto" />
            {boxes.filter((b) => b.page === p).map((b, i) => {
              const ref = !firstAssigned ? ((firstAssigned = true), firstHit) : null;
              return (
                <div key={i} ref={ref} className="absolute rounded-[3px] hl-box"
                  style={{ left: `${b.x0 * 100 - 0.6}%`, top: `${b.y0 * 100 - 0.4}%`,
                    width: `${(b.x1 - b.x0) * 100 + 1.2}%`, height: `${(b.y1 - b.y0) * 100 + 0.8}%` }} />
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}
