import { memo, useCallback, useEffect, useRef, useState } from "react";
import { api, fmtT, nextSyntheticCode, useSnapshot, type AlertItem } from "./api";
import { Air } from "./components/Air";
import { Devices } from "./components/Devices";
import { Incidents } from "./components/Incidents";
import { Learning } from "./components/Learning";
import { Overview } from "./components/Overview";
import { Icon, providerLabel, usePalette } from "./components/ui";

type Tab = "overview" | "incidents" | "devices" | "air" | "learning";
const SPEEDS = [1, 10, 30, 60, 0];

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(() => { try { return localStorage.getItem("af-theme") ?? ""; } catch { return ""; } });
  useEffect(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme); else document.documentElement.removeAttribute("data-theme");
    try { if (theme) localStorage.setItem("af-theme", theme); } catch { /* storage unavailable */ }
  }, [theme]);
  const isDark = theme ? theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  return [theme || (isDark ? "dark" : "light"), () => setTheme(isDark ? "light" : "dark")];
}

const CriticalToast = memo(function CriticalToast({ alert, isMin, onOpen, onDismiss }:
  { alert: AlertItem; isMin: boolean; onOpen: (id: string) => void; onDismiss: (id: string) => void }) {
  return (
    <div className={`toast ${isMin ? "toast-min" : "pulse"}`} onClick={() => isMin && onOpen(alert.incident_id)}>
      <span className="toast-badge" aria-hidden>!</span>
      <div className="toast-frame">
        <div className="toast-frame-inner">
          <button className="toast-body" onClick={() => onOpen(alert.incident_id)}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="sev critical">Critical</span>
              <span className="pill">{alert.priority}</span>
            </div>
            <strong>{alert.title}</strong>
            <div className="muted small">{alert.catalog_id} · Sensors: {alert.sensors.join(", ") || "n/a"}</div>
            <div className="muted tabnum small">detected {fmtT(alert.created_t)}</div>
          </button>
          <button className="toast-close" aria-label="Dismiss" onClick={(e) => { e.stopPropagation(); onDismiss(alert.incident_id); }}>✕</button>
        </div>
      </div>
    </div>
  );
});

export default function App() {
  const { snap, conn } = useSnapshot();
  const [tab, setTab] = useState<Tab>("overview");
  const [incident, setIncident] = useState<string | null>(null);
  const [theme, toggleTheme] = useTheme();
  const pal = usePalette(theme);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [minimized, setMinimized] = useState<Set<string>>(new Set());
  const minimizeTimers = useRef<Record<string, number>>({});
  const openIncident = useCallback((id: string) => { setIncident(id); setTab("incidents"); }, []);

  const c = snap?.clock;
  const progress = c?.duration ? Math.min(100, (100 * c.t) / c.duration) : 0;
  const running = c?.state === "running";
  const openCount = snap?.incidents.filter((i) => i.status === "open").length ?? 0;
  const criticalAlerts = [...(snap?.alerts?.filter((a) => a.severity === "critical" && !dismissed.has(a.incident_id)) ?? [])]
    .sort((a, b) => b.created_t - a.created_t);
  const dismiss = useCallback((id: string) => setDismissed((cur) => new Set(cur).add(id)), []);
  const criticalIds = criticalAlerts.map((a) => a.incident_id).join(",");
  const injectedOnStart = useRef(false);
  useEffect(() => {
    // Demonstrates the catalog-learning loop unprompted: as soon as the app is up,
    // seed one batch of synthetic unmatched events so the Learning tab always has a
    // live "unknown error being found and adopted" flow to show, whenever it's opened.
    if (!snap || injectedOnStart.current) return;
    injectedOnStart.current = true;
    api.inject(25, nextSyntheticCode()).catch(() => {});
  }, [snap]);
  useEffect(() => {
    // real wall-clock timing, independent of replay speed: pop up full-size, then
    // minimize to a small badge after a few seconds - it never disappears on its own.
    for (const id of criticalIds ? criticalIds.split(",") : []) {
      if (minimizeTimers.current[id] == null) {
        minimizeTimers.current[id] = window.setTimeout(() => {
          setMinimized((cur) => new Set(cur).add(id));
        }, 6000);
      }
    }
  }, [criticalIds]);

  return (
    <>
      <header className="top">
        <div className="top-row">
          <div className="brand"><div className="brand-mark">{Icon.wifi}</div><div><b>Airframe</b><small>Live Wi-Fi diagnostics · header-only · multi-sensor</small></div></div>
          <span className="pill"><span className="dot" style={{ background: conn === "live" ? "var(--good)" : conn === "offline" ? "var(--critical)" : "var(--warning)" }} />{conn === "live" ? "Live" : conn === "offline" ? "Disconnected" : "Connecting"}</span>
          {c && <span className="pill tabnum">{c.state === "finished" ? "Replay finished" : c.state} · capture time {fmtT(c.t)}{c.duration ? ` / ${fmtT(c.duration)}` : ""} · {c.fps.toLocaleString()} frames/s</span>}
          <div className="controls">
            {running
              ? <button className="btn" onClick={() => api.replay("pause")}>{Icon.pause} Pause</button>
              : <button className="btn" disabled={c?.state === "finished"} onClick={() => api.replay("resume")}>{Icon.play} Resume</button>}
            <div className="seg" aria-label="Replay speed">
              {SPEEDS.map((s) => <button key={s} className={c?.speed === s ? "on" : ""} onClick={() => api.replay("speed", s)}>{s === 0 ? "Max" : `${s}×`}</button>)}
            </div>
            <button className="btn" onClick={() => api.replay("start", c?.speed ?? 10)}>{Icon.restart} Restart</button>
            <span className="pill pill-ai">{Icon.ai}{snap ? `AI: ${providerLabel(snap.agent.mode, snap.agent.model)}` : "AI: offline"}</span>
            <button className="btn" onClick={toggleTheme} aria-label="Toggle theme">{theme === "dark" ? Icon.sun : Icon.moon}</button>
          </div>
        </div>
        <div className="progress"><div style={{ width: `${progress}%` }} /></div>
        <nav className="tabs">
          {([["overview", "Overview"], ["incidents", "Incidents"], ["devices", "Devices"], ["air", "Air & sensors"], ["learning", "Learning"]] as [Tab, string][]).map(([k, label]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}
              {k === "incidents" && openCount > 0 && <span className="count">{openCount}</span>}
              {k === "learning" && (snap?.unknown.count ?? 0) > 0 && <span className="count">{snap?.unknown.count}</span>}
            </button>
          ))}
        </nav>
      </header>
      {snap && criticalAlerts.length > 0 && (
        <div className="toast-stack" role="alert" aria-live="assertive">
          {criticalAlerts.map((alert) => (
            <CriticalToast key={alert.incident_id} alert={alert} isMin={minimized.has(alert.incident_id)} onOpen={openIncident} onDismiss={dismiss} />
          ))}
        </div>
      )}
      <main>
        {!snap ? <div className="empty">Connecting to the Airframe engine… (start it with <code>python -m airframe serve</code>)</div> : (
          <>
            {tab === "overview" && <Overview snap={snap} pal={pal} openIncident={openIncident} />}
            {tab === "incidents" && <Incidents snap={snap} selected={incident} select={setIncident} />}
            {tab === "devices" && <Devices snap={snap} />}
            {tab === "air" && <Air snap={snap} pal={pal} />}
            {tab === "learning" && <Learning snap={snap} />}
          </>
        )}
      </main>
    </>
  );
}
