import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { LayoutGrid, Inbox, ClipboardCheck, FileStack, Moon, Sun, Upload } from "lucide-react";
import { api } from "./api";
import Dashboard from "./pages/Dashboard";
import RunView from "./pages/RunView";
import Intake from "./pages/Intake";
import Review from "./pages/Review";
import Orders from "./pages/Orders";

const RunsCtx = createContext(null);
export const useRuns = () => useContext(RunsCtx);

function useLiveRuns() {
  const [runs, setRuns] = useState([]);
  const [fresh, setFresh] = useState({});
  const [tick, setTick] = useState(0);
  useEffect(() => {
    api.runs().then(setRuns).catch(() => {});
    const es = new EventSource("/api/stream");
    es.addEventListener("run", (e) => {
      const r = JSON.parse(e.data);
      setRuns((prev) => {
        const i = prev.findIndex((x) => x.id === r.id);
        if (i === -1) return [r, ...prev].sort((a, b) => b.created_at.localeCompare(a.created_at));
        const next = prev.slice();
        next[i] = r;
        return next;
      });
      setFresh((f) => ({ ...f, [r.id]: Date.now() }));
      setTick((t) => t + 1);
    });
    return () => es.close();
  }, []);
  return { runs, fresh, tick, refresh: () => api.runs().then(setRuns) };
}

function useTheme() {
  const read = () => { try { return localStorage.getItem("theme"); } catch { return null; } };
  const [theme, setTheme] = useState(read);
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { theme ? localStorage.setItem("theme", theme) : localStorage.removeItem("theme"); } catch {}
  }, [theme]);
  const dark = theme ? theme === "dark" : window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return [dark, () => setTheme(dark ? "light" : "dark")];
}

export default function App() {
  const live = useLiveRuns();
  const [dark, toggleTheme] = useTheme();
  const navigate = useNavigate();
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);

  const attention = live.runs.filter(
    (r) => r.status === "done" && ["HOLD", "FRAUD_HOLD", "REQUEST_INFO"].includes(r.decision) && !r.review_status
  ).length;

  const onDrop = useCallback(async (e) => {
    e.preventDefault();
    depth.current = 0;
    setDragging(false);
    const files = [...(e.dataTransfer?.files || [])].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!files.length) return;
    const { run_ids } = await api.upload(files);
    navigate(`/runs/${run_ids[0]}`);
  }, [navigate]);

  return (
    <RunsCtx.Provider value={live}>
      <div
        className="min-h-screen md:grid md:grid-cols-[220px_1fr]"
        onDragEnter={(e) => { if (e.dataTransfer?.types?.includes("Files")) { depth.current++; setDragging(true); } }}
        onDragLeave={() => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDragging(false); }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        <aside className="md:sticky md:top-0 md:h-screen border-b md:border-b-0 md:border-r border-rule bg-sheet flex md:flex-col">
          <div className="px-5 py-4 md:py-6 flex items-center gap-2.5 shrink-0">
            <div className="w-7 h-7 rounded-[5px] border-[2.5px] border-carbon grid place-items-center -rotate-6">
              <span className="display text-carbon text-[11px] leading-none">AP</span>
            </div>
            <div className="leading-tight hidden sm:block">
              <div className="display text-[15px]">AP Desk</div>
              <div className="text-[11px] text-ink-3">Invoice agent</div>
            </div>
          </div>
          <nav className="flex md:flex-col gap-0.5 px-2 md:px-3 items-center md:items-stretch overflow-x-auto flex-1">
            <Nav to="/" icon={LayoutGrid} end>Dashboard</Nav>
            <Nav to="/intake" icon={Inbox}>Intake</Nav>
            <Nav to="/review" icon={ClipboardCheck} badge={attention}>Review queue</Nav>
            <Nav to="/orders" icon={FileStack}>Purchase orders</Nav>
          </nav>
          <div className="hidden md:block px-4 py-4 border-t border-rule text-[12px] text-ink-3 space-y-3">
            <div className="flex items-start gap-2">
              <Upload size={14} className="mt-0.5 shrink-0" />
              <span>Drop a PDF anywhere on this page to process it.</span>
            </div>
            <button onClick={toggleTheme} className="flex items-center gap-2 hover:text-ink">
              {dark ? <Sun size={14} /> : <Moon size={14} />} {dark ? "Light mode" : "Dark mode"}
            </button>
          </div>
        </aside>

        <main className="min-w-0 px-4 sm:px-6 lg:px-8 py-6 lg:py-8 max-w-[1500px]">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/runs/:id" element={<RunView />} />
            <Route path="/intake" element={<Intake />} />
            <Route path="/review" element={<Review />} />
            <Route path="/orders" element={<Orders />} />
          </Routes>
        </main>

        {dragging && (
          <div className="fixed inset-0 z-50 bg-paper/85 backdrop-blur-sm grid place-items-center pointer-events-none">
            <div className="sheet border-2 border-dashed !border-carbon px-10 py-8 text-center">
              <Upload className="mx-auto text-carbon mb-2" />
              <div className="display text-xl">Drop to process</div>
              <div className="text-ink-2 mt-1">PDF invoices only</div>
            </div>
          </div>
        )}
      </div>
    </RunsCtx.Provider>
  );
}

function Nav({ to, icon: Icon, children, badge, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-md px-3 py-2 text-[13.5px] font-medium whitespace-nowrap transition ${
          isActive ? "bg-carbon-soft text-carbon" : "text-ink-2 hover:bg-sheet-2 hover:text-ink"
        }`
      }
    >
      <Icon size={16} />
      <span className="hidden sm:inline">{children}</span>
      {badge > 0 && (
        <span className="ml-auto num text-[11px] rounded-full bg-warn text-white px-1.5 min-w-5 text-center">{badge}</span>
      )}
    </NavLink>
  );
}
