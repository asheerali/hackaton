import { useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtT, type SeriesPoint } from "../api";
import type { Palette } from "./ui";

type TipProps = { active?: boolean; label?: number | string; payload?: { name: string; value: number; color: string }[]; unit?: string; labelFmt?: (l: number | string) => string };

function Tip({ active, label, payload, unit = "", labelFmt }: TipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tip">
      <b>{labelFmt ? labelFmt(label as number) : label}</b>
      {payload.map((p) => (
        <div key={p.name}><span><i style={{ display: "inline-block", width: 10, height: 3, background: p.color, marginRight: 6, verticalAlign: "middle" }} />{p.name}</span><span className="tabnum">{p.value}{unit}</span></div>
      ))}
    </div>
  );
}

const LOGIN_SERIES = [
  { key: "joins", name: "Join attempts", slot: "s1" },
  { key: "kicks", name: "Kicked (802.1X failed)", slot: "s2" },
  { key: "fast_rejects", name: "Fast-rejected", slot: "s4" },
  { key: "connected", name: "Connected", slot: "s3" },
] as const;

export function LoginChart({ series, pal, duration }: { series: SeriesPoint[]; pal: Palette; duration: number | null }) {
  const [table, setTable] = useState(false);
  const byMin = new Map<number, { t: number; joins: number; kicks: number; fast_rejects: number; connected: number }>();
  for (const p of series) {
    const m = Math.floor(p.t / 60) * 60;
    const r = byMin.get(m) ?? { t: m, joins: 0, kicks: 0, fast_rejects: 0, connected: 0 };
    r.joins += p.joins; r.kicks += p.kicks; r.fast_rejects += p.fast_rejects; r.connected += p.connected;
    byMin.set(m, r);
  }
  const data = [...byMin.values()];
  const totals = LOGIN_SERIES.map((s) => ({ ...s, total: data.reduce((a, d) => a + (d[s.key] as number), 0) }));
  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="legend">
          {totals.map((s) => <span key={s.key}><i style={{ background: pal[s.slot] }} />{s.name} <b className="tabnum" style={{ color: "var(--ink)" }}>{s.total}</b></span>)}
        </div>
        <button className="btn small" onClick={() => setTable(!table)}>{table ? "Chart" : "Table"}</button>
      </div>
      {table ? (
        <div className="scroll" style={{ maxHeight: 240 }}>
          <table className="t tabnum"><thead><tr><th>Time</th>{LOGIN_SERIES.map((s) => <th key={s.key}>{s.name}</th>)}</tr></thead>
            <tbody>{data.filter((d) => d.joins || d.kicks || d.fast_rejects || d.connected).map((d) => (
              <tr key={d.t}><td>{fmtT(d.t)}</td>{LOGIN_SERIES.map((s) => <td key={s.key}>{d[s.key]}</td>)}</tr>))}</tbody></table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={230}>
          <LineChart data={data} margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
            <CartesianGrid stroke={pal.line} vertical={false} />
            <XAxis dataKey="t" type="number" domain={[0, duration ?? "dataMax"]} tickFormatter={fmtT} stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} />
            <YAxis allowDecimals={false} stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip content={<Tip labelFmt={(l) => `minute starting ${fmtT(l as number)}`} />} cursor={{ stroke: pal.axis }} />
            {LOGIN_SERIES.map((s) => (
              <Line key={s.key} dataKey={s.key} name={s.name} stroke={pal[s.slot]} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: pal.surface, strokeWidth: 2 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export function ProbeChart({ series, pal, duration }: { series: SeriesPoint[]; pal: Palette; duration: number | null }) {
  const data = series.map((p) => ({ t: p.t, v: p.probe_per_s }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={pal.line} vertical={false} />
        <XAxis dataKey="t" type="number" domain={[0, duration ?? "dataMax"]} tickFormatter={fmtT} stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} />
        <YAxis stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip content={<Tip labelFmt={(l) => fmtT(l as number)} unit="/s" />} cursor={{ stroke: pal.axis }} />
        <Area dataKey="v" name="Probe replies" stroke={pal.s1} strokeWidth={2} fill={pal.s1} fillOpacity={0.15} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const SENSOR_METRICS = [
  { key: "frames_per_s", name: "Frames", unit: "/s" },
  { key: "probe_per_s", name: "Probe replies", unit: "/s" },
  { key: "retry_pct", name: "Retry rate", unit: "%" },
  { key: "beacon_air_pct", name: "Beacon airtime", unit: "%" },
  { key: "kicks", name: "802.1X kicks", unit: "" },
  { key: "connected", name: "Connections", unit: "" },
] as const;
const SENSOR_SLOTS = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"] as const;

export function SensorCompareChart({ perSensor, sensors, pal, duration }:
  { perSensor: Record<string, Array<Record<string, number>>>; sensors: string[]; pal: Palette; duration: number | null }) {
  const [metric, setMetric] = useState<(typeof SENSOR_METRICS)[number]["key"]>("frames_per_s");
  const [selected, setSelected] = useState<string[]>(sensors);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const active = selected.filter((s) => sensors.includes(s));
  const m = SENSOR_METRICS.find((x) => x.key === metric)!;
  const data = perSensor[metric] ?? [];

  const toggle = (s: string) => setSelected((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  const toggleLegend = (s: string) => setHidden((cur) => {
    const next = new Set(cur);
    if (next.has(s)) next.delete(s); else next.add(s);
    return next;
  });

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
          <button className="btn small" onClick={() => setSelected(sensors)}>Select all</button>
          <button className="btn small" onClick={() => setSelected([])}>Deselect all</button>
          {sensors.map((s) => (
            <button key={s} className={`chip ${selected.includes(s) ? "selected" : ""}`} onClick={() => toggle(s)}>{s}</button>
          ))}
        </div>
        <select className="btn small" value={metric} onChange={(e) => setMetric(e.target.value as typeof metric)}>
          {SENSOR_METRICS.map((x) => <option key={x.key} value={x.key}>{x.name}</option>)}
        </select>
      </div>
      <div className="legend" style={{ marginTop: 6 }}>
        {active.map((s, i) => (
          <span key={s} style={{ cursor: "pointer", opacity: hidden.has(s) ? 0.4 : 1 }} onClick={() => toggleLegend(s)}>
            <i style={{ background: pal[SENSOR_SLOTS[i % SENSOR_SLOTS.length]] }} />{s}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
          <CartesianGrid stroke={pal.line} vertical={false} />
          <XAxis dataKey="t" type="number" domain={[0, duration ?? "dataMax"]} tickFormatter={fmtT} stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} />
          <YAxis stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} axisLine={false} unit={m.unit} />
          <Tooltip content={<Tip labelFmt={(l) => fmtT(l as number)} unit={m.unit} />} cursor={{ stroke: pal.axis }} />
          {active.map((s, i) => !hidden.has(s) && (
            <Line key={s} dataKey={s} name={s} stroke={pal[SENSOR_SLOTS[i % SENSOR_SLOTS.length]]} strokeWidth={2} dot={false}
              activeDot={{ r: 4, stroke: pal.surface, strokeWidth: 2 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ChannelBars({ data, unit, pal, name }: { data: Record<string, number>; unit: string; pal: Palette; name: string }) {
  const rows = Object.entries(data).map(([ch, v]) => ({ ch: `ch ${ch}`, v })).sort((a, b) => Number(a.ch.slice(3)) - Number(b.ch.slice(3)));
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 26 + 20)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 36, left: 4, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke={pal.line} horizontal={false} />
        <XAxis type="number" stroke={pal.axis} tick={{ fill: pal.muted, fontSize: 11 }} tickLine={false} unit={unit} />
        <YAxis type="category" dataKey="ch" width={52} stroke={pal.axis} tick={{ fill: pal.ink2, fontSize: 12 }} tickLine={false} axisLine={false} />
        <Tooltip content={<Tip unit={unit} />} cursor={{ fill: pal.line, opacity: 0.4 }} />
        <Bar dataKey="v" name={name} fill={pal.s1} radius={[0, 4, 4, 0]} isAnimationActive={false}
          label={{ position: "right", fill: pal.ink2, fontSize: 11, formatter: (v: unknown) => `${v}${unit}` }} />
      </BarChart>
    </ResponsiveContainer>
  );
}
