import { useEffect, useState } from "react";
import { api, fmtT, useSnapshot } from "./api";
import { Air } from "./components/Air";
import { Devices } from "./components/Devices";
import { Incidents } from "./components/Incidents";
import { Learning } from "./components/Learning";
import { Overview } from "./components/Overview";
import { Icon, usePalette } from "./components/ui";

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

export default function App() {
  const { snap, conn } = useSnapshot();
  const [tab, setTab] = useState<Tab>("overview");
  const [incident, setIncident] = useState<string | null>(null);
  const [theme, toggleTheme] = useTheme();
  const pal = usePalette(theme);
  const openIncident = (id: string) => { setIncident(id); setTab("incidents"); };

  const c = snap?.clock;
  const progress = c?.duration ? Math.min(100, (100 * c.t) / c.duration) : 0;
  const running = c?.state === "running";
  const openCount = snap?.incidents.filter((i) => i.status === "open").length ?? 0;

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
            <span className="pill">{snap?.agent.mode === "claude" ? "AI: Claude" : "AI: offline"}</span>
            <button className="btn" onClick={toggleTheme} aria-label="Toggle theme">{theme === "dark" ? Icon.sun : Icon.moon}</button>
          </div>
        </div>
        <div className="progress"><div style={{ width: `${progress}%` }} /></div>
        <nav className="tabs">
          {([["overview", "Overview"], ["incidents", "Incidents"], ["devices", "Devices"], ["air", "Air & sensors"], ["learning", "Learning (Part 3)"]] as [Tab, string][]).map(([k, label]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}
              {k === "incidents" && openCount > 0 && <span className="count">{openCount}</span>}
              {k === "learning" && (snap?.unknown.count ?? 0) > 0 && <span className="count">{snap?.unknown.count}</span>}
            </button>
          ))}
        </nav>
      </header>
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
