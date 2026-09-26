import { useEffect, useMemo, useState } from "react";
import { api, fmtT, type DeviceRow, type Snapshot, type StoryStep } from "../api";
import { Card, State } from "./ui";

const STATES = ["all", "excluded", "failing", "searching", "connected", "left"] as const;

export function Devices({ snap }: { snap: Snapshot }) {
  const [state, setState] = useState<(typeof STATES)[number]>("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => snap.devices.filter((d) => (state === "all" || d.state === state)
    && (!q || `${d.alias} ${d.network} ${d.ap} ${d.class}`.toLowerCase().includes(q.toLowerCase()))), [snap.devices, state, q]);
  const counts = useMemo(() => Object.fromEntries(STATES.map((s) => [s, s === "all" ? snap.devices.length : snap.devices.filter((d) => d.state === s).length])), [snap.devices]);
  return (
    <>
      <Card title="Devices" sub="Every client seen by any sensor (identifiers are keyed hashes). Click a device to see its login sequence.">
        <div className="row" style={{ marginBottom: 10 }}>
          <div className="seg">{STATES.map((s) => <button key={s} className={state === s ? "on" : ""} onClick={() => setState(s)}>{s} <span className="muted">{counts[s]}</span></button>)}</div>
          <input placeholder="Filter by name, network, AP…" value={q} onChange={(e) => setQ(e.target.value)}
            style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "6px 10px", background: "var(--surface)", color: "var(--ink)", minWidth: 220 }} />
        </div>
        <div className="scroll">
          <table className="t tabnum">
            <thead><tr><th>Device</th><th>Type</th><th>State</th><th>Network</th><th>Access point</th><th>Ch</th><th>Attempts</th><th>Connected</th><th>Kicked</th><th>Fast-rejected</th><th>Last seen</th></tr></thead>
            <tbody>{rows.map((d) => (
              <tr key={d.id} className="click" onClick={() => setOpen(d.id)}>
                <td className="mono">{d.alias}</td><td>{d.class}</td><td><State s={d.state} /></td><td>{d.network ?? "–"}</td>
                <td className="mono">{d.ap ?? "–"}</td><td>{d.channel ?? "–"}</td><td>{d.attempts}</td><td>{d.connected}</td><td>{d.kicks}</td><td>{d.fast_rejects}</td><td>{fmtT(d.last_t)}</td>
              </tr>))}</tbody>
          </table>
          {!rows.length && <div className="empty">No devices match.</div>}
        </div>
      </Card>
      {open && <Story id={open} close={() => setOpen(null)} />}
    </>
  );
}

const STEP_COLOR = (s: string) => /Deauth|Disassoc|refused|failure/i.test(s) ? "var(--critical)"
  : /who are you|EAP/.test(s) ? "var(--serious)" : /Key message M3|Data flowing|EAP success/.test(s) ? "var(--good)" : "var(--s1)";

function Story({ id, close }: { id: string; close: () => void }) {
  const [d, setD] = useState<(DeviceRow & { story: StoryStep[] }) | null>(null);
  useEffect(() => { api.device(id).then(setD); }, [id]);
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && close(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [close]);
  return (
    <>
      <div className="drawer-bg" onClick={close} />
      <aside className="drawer" role="dialog" aria-label="Device login sequence">
        <div className="row"><h3 style={{ margin: 0 }} className="mono">{d?.alias ?? "…"}</h3><span className="spacer" /><button className="btn" onClick={close}>Close</button></div>
        {d && <>
          <div className="row small" style={{ margin: "8px 0 12px" }}><State s={d.state} /><span className="pill">{d.class}</span><span className="pill">{d.network ?? "no network"}</span>
            <span className="pill">{d.attempts} attempts · {d.connected} connected</span></div>
          <p className="small muted">Each row is one frame the sensors heard (sensor, time). "by AP" rows are the access point's side, which sensors hear most reliably.</p>
          <ol className="story">
            {d.story.map((s, n) => (
              <li key={n}><span className="ts tabnum">{fmtT(s.t)}</span><span className="node" style={{ background: STEP_COLOR(s.step) }} />
                <span><b>{s.step}</b> <span className="muted small">by {s.by ?? "?"} · S{s.s}:{s.n}{s.ap ? ` · ${s.ap}` : ""}</span>{s.detail && <div className="small ink2">{s.detail}</div>}</span></li>
            ))}
          </ol>
          {!d.story.length && <div className="empty">Only probe traffic seen for this device: it searches but never joins.</div>}
        </>}
      </aside>
    </>
  );
}
