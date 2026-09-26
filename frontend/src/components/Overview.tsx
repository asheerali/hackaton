import { fmtT, type Snapshot } from "../api";
import { LoginChart, ProbeChart } from "./Charts";
import { Card, Kpi, Sev, type Palette } from "./ui";

export function Overview({ snap, pal, openIncident }: { snap: Snapshot; pal: Palette; openIncident: (id: string) => void }) {
  const k = snap.kpi;
  const open = snap.incidents.filter((i) => i.status === "open");
  const root = open.find((i) => i.is_root) ?? open[0];
  const dur = snap.clock.duration;
  const success = k.attempts ? k.connected / k.attempts : null;
  return (
    <div className="grid" style={{ gap: 14 }}>
      {root ? (
        <section className={`card ${root.severity === "critical" ? "hero" : ""}`}>
          <div className="row"><Sev s={root.severity} /><span className="pill">{root.catalog_id}</span>
            <span className="muted small">detected at {fmtT(root.first_seen_t)} · updated {fmtT(root.updated_t)}</span>
            {k.time_to_root_s != null && root.is_root && <span className="pill">found {k.time_to_root_s.toFixed(0)} s after the first failing join</span>}
          </div>
          <h2>{root.title}</h2>
          <p>
            {root.is_root
              ? <>Every login on <b>{root.network}</b> stops at the identity check (“who are you?”) and the device is thrown out. The same failure appears on {root.where.aps.length} access points and {root.where.sensors.length} sensors, so it is counted as <b>one problem</b>, not {root.devices_affected} separate ones.</>
              : <>Most important open finding right now.</>}
          </p>
          <div className="facts tabnum">
            <div><b>{root.devices_affected}</b><span>devices affected</span></div>
            <div><b>{root.where.aps.length}</b><span>access points</span></div>
            <div><b>{root.where.channels.length}</b><span>channels</span></div>
            <div><b>{root.where.sensors.join(" ") || "–"}</b><span>seen by, counted once</span></div>
            <div><b>{Math.round(root.confidence * 100)}%</b><span>confidence</span></div>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={() => openIncident(root.id)}>Open incident & propose fix →</button>
          </div>
        </section>
      ) : (
        <Card><div className="empty">{snap.clock.t < 30 ? "Listening… the first findings appear within about a minute of capture time." : "No open incidents."}</div></Card>
      )}

      <div className="grid g-kpi">
        <Kpi label="Devices seen" value={k.devices} foot={`${snap.clock.frames.toLocaleString()} frames`} />
        <Kpi label="Failing now" value={k.failing} tone={k.failing ? "bad" : "good"} foot={`${k.fast_rejects} fast-rejects`} />
        <Kpi label="Logins that worked" value={success == null ? "–" : `${Math.round(success * 100)}%`} tone={success != null && success < 0.9 ? "bad" : "good"}
          foot={snap.networks.length ? snap.networks.map((n) => `${n.label}: ${n.connected}/${n.attempts}`).join(" · ") : `${k.connected} of ${k.attempts} attempts`} />
        <Kpi label="Kicked out (802.1X)" value={k.kicks} tone={k.kicks ? "bad" : undefined} foot="reason 23" />
        <Kpi label="Probe replies" value={`${k.probe_per_s}/s`} tone={k.probe_per_s > 50 ? "warn" : undefined} foot={`${k.retry_pct}% re-sent, last 60 s`} />
        <Kpi label="Open incidents" value={k.open_incidents} foot={`${k.unknown} unmatched events`} />
      </div>

      <div className="grid g-2">
        <Card title="Login attempts and outcomes" sub="Per minute of capture time, all sensors. A healthy network shows attempts followed by connections.">
          <LoginChart series={snap.series.site} pal={pal} duration={dur} />
        </Card>
        <Card title="Probe replies per second" sub="Access points answering devices that keep searching. Storms follow failed logins.">
          <ProbeChart series={snap.series.site} pal={pal} duration={dur} />
        </Card>
      </div>

      <div className="grid g-2">
        <Card title="Open incidents" sub="One line per real problem. Children (per-device findings) are inside each incident.">
          <div className="inc-list">
            {open.slice(0, 8).map((i) => (
              <button key={i.id} className="inc" onClick={() => openIncident(i.id)}>
                <div className="row"><Sev s={i.severity} /><span className="t">{i.title}</span></div>
                <div className="m"><span className="mono">{i.id}</span><span>{i.catalog_id}</span>
                  {i.devices_affected > 0 && <span>{i.devices_affected} devices</span>}
                  {i.where.channels.length > 0 && <span>ch {i.where.channels.join(", ")}</span>}
                  <span>since {fmtT(i.first_seen_t)}</span></div>
              </button>
            ))}
            {!open.length && <div className="empty">Nothing open.</div>}
          </div>
        </Card>
        <Card title="Live events">
          <ul className="feed">
            {snap.feed.map((f, n) => (
              <li key={n}><span className="muted tabnum">{fmtT(f.t)}</span>
                <span>{f.severity !== "info" && <Sev s={f.severity} />} {f.ref && f.ref.startsWith("INC") ? <a href="#" onClick={(e) => { e.preventDefault(); openIncident(f.ref!); }}>{f.text}</a> : f.text}</span></li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
