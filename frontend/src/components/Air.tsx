import type { Snapshot } from "../api";
import { ChannelBars } from "./Charts";
import { Card, type Palette } from "./ui";

export function Air({ snap, pal }: { snap: Snapshot; pal: Palette }) {
  const nets = snap.aps.networks;
  return (
    <div className="grid" style={{ gap: 14 }}>
      <Card title="Sensor coverage" sub="Each sensor listens to one channel. What a sensor cannot hear is never treated as 'did not happen'.">
        <div className="sensor-grid">
          {snap.sensors.map((s) => (
            <div className="sensor" key={s.sensor}>
              <div className="row"><b>{s.sensor}</b><span className="spacer" />
                <span className="state" style={{ color: s.alive ? "var(--good)" : "var(--critical)" }}><span aria-hidden>{s.alive ? "●" : "✕"}</span><span style={{ color: "var(--ink)" }}>{s.alive ? "listening" : "silent"}</span></span></div>
              <div className="ch">ch {s.channel}</div>
              <div className="small ink2 tabnum">{s.aps} APs · {s.bssids} networks · {s.frames.toLocaleString()} frames</div>
              <div className="small ink2 tabnum">beacon loss {s.beacon_loss_pct ?? "–"}%</div>
              <div className="chips" style={{ marginTop: 6 }}>{Object.entries(s.networks).map(([n, c]) => <span className="chip" key={n}>{n} × {c}</span>)}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid g-2e">
        <Card title="Beacon airtime by channel" sub="Share of air used by access-point adverts before any real traffic, at the rate the capture reports.">
          <ChannelBars data={snap.series.beacon_air_pct} unit="%" pal={pal} name="Beacon airtime" />
        </Card>
        <Card title="Unacknowledged probe replies by channel" sub="Replies re-sent because the device never acknowledged (it had already moved on).">
          <ChannelBars data={snap.series.retry_pct} unit="%" pal={pal} name="Re-sent" />
        </Card>
      </div>

      <Card title="Access points × networks" sub="Every access point should offer every site network. Missing cells are what devices homed there cannot join.">
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="t matrix tabnum">
            <thead><tr><th>Access point</th><th>Sensor</th><th>Ch</th>{nets.map((n) => <th key={n.label} style={{ textAlign: "center" }}>{n.label}<div className="muted small">{n.kind}</div></th>)}<th>Joins</th><th>Failures</th></tr></thead>
            <tbody>{snap.aps.rows.map((r) => (
              <tr key={r.ap}><td className="mono">{r.ap}</td><td>{r.sensor}</td><td>{r.channel}</td>
                {nets.map((n) => <td key={n.label} className="cell">{r.networks[n.label]
                  ? <span className="state" style={{ color: "var(--good)" }}><span aria-hidden>✓</span><span style={{ color: "var(--ink)" }}>offered</span></span>
                  : <span className="state" style={{ color: "var(--critical)" }}><span aria-hidden>✕</span><span style={{ color: "var(--ink)" }}>missing</span></span>}</td>)}
                <td>{r.joins}</td><td style={{ color: r.failures ? "var(--critical)" : undefined }}>{r.failures}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Card>

      {snap.data_quality.length > 0 && (
        <Card title="Data quality flags" sub="Things in the capture that real radios cannot produce. They lower confidence; they are never incidents on their own.">
          <ul className="clean small">{snap.data_quality.map((f) => <li key={f.key}>{f.text} <span className="muted">({f.sensors.length === snap.sensors.length ? "all sensors" : f.sensors.join(" ")})</span></li>)}</ul>
        </Card>
      )}
    </div>
  );
}
