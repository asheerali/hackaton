import { fmtT, type Snapshot } from "../api";
import { LoginChart, ProbeChart, SensorCompareChart } from "./Charts";
import { Card, Kpi, Sev, type Palette } from "./ui";

export function Overview({ snap, pal, openIncident }: { snap: Snapshot; pal: Palette; openIncident: (id: string) => void }) {
  const k = snap.kpi;
  const open = snap.incidents.filter((i) => i.status === "open");
  const dur = snap.clock.duration;
  const success = k.attempts ? k.connected / k.attempts : null;
  const sensorCompare = snap.sensors.map((sensor) => ({
    sensor: sensor.sensor,
    alive: sensor.alive,
    frames: sensor.frames,
    beacon_loss_pct: sensor.beacon_loss_pct ?? 0,
  }));
  return (
    <div className="grid" style={{ gap: 14 }}>
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

      <Card title="Nearby sensor comparison" sub="Cross-compare capture health and event intensity across the sensor cluster.">
        <div className="sensor-grid">
          {sensorCompare.map((entry) => (
            <div key={entry.sensor} className="sensor">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b>{entry.sensor}</b>
                <span className={`state ${entry.alive ? "good" : "critical"}`} style={{ color: entry.alive ? "var(--good)" : "var(--critical)" }}>
                  {entry.alive ? "● listening" : "✕ silent"}
                </span>
              </div>
              <div className="m" style={{ marginTop: 8 }}>
                <span>{entry.frames.toLocaleString()} frames</span>
                <span>{entry.beacon_loss_pct.toFixed(1)}% beacon loss</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14 }}>
          <SensorCompareChart perSensor={snap.series.per_sensor} sensors={snap.series.sensors} pal={pal} duration={dur} />
        </div>
      </Card>

      <div className="grid g-2">
        <Card title="Critical alert log" sub="Every critical detection, newest first — a running notification log, not just what's currently open.">
          <ul className="feed">
            {snap.feed.filter((f) => f.severity === "critical").map((f, n) => {
              const isNew = snap.clock.t - f.t < 8;
              return (
                <li key={n} className={isNew ? "pulse" : undefined}>
                  <span className="muted tabnum">{fmtT(f.t)}</span>
                  <span><Sev s="critical" /> {f.ref && f.ref.startsWith("INC") ? <a href="#" onClick={(e) => { e.preventDefault(); openIncident(f.ref!); }}>{f.text}</a> : f.text}
                    {isNew && <span className="pill" style={{ marginLeft: 6 }}>new</span>}</span>
                </li>
              );
            })}
            {!snap.feed.some((f) => f.severity === "critical") && <li><span className="muted">No critical alerts yet</span></li>}
          </ul>
        </Card>
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
      </div>

      <div className="grid g-2">
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
