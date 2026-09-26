import { useEffect, useMemo, useState } from "react";
import { api, fmtT, waitJob, type IncidentDetail, type ProposalRecord, type Snapshot } from "../api";
import { Card, Sev } from "./ui";

export function Incidents({ snap, selected, select }: { snap: Snapshot; selected: string | null; select: (id: string) => void }) {
  const [filter, setFilter] = useState<"open" | "all">("open");
  const list = snap.incidents.filter((i) => filter === "all" || i.status === "open");
  const current = selected ?? list[0]?.id ?? null;
  return (
    <div className="grid g-split">
      <Card title="Incidents" sub="De-duplicated across sensors: one line per real problem." right={
        <div className="seg"><button className={filter === "open" ? "on" : ""} onClick={() => setFilter("open")}>Open</button><button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>All</button></div>}>
        <div className="inc-list">
          {list.map((i) => (
            <button key={i.id} className={`inc ${i.id === current ? "on" : ""} ${i.status !== "open" ? "resolved" : ""}`} onClick={() => select(i.id)}>
              <div className="row"><Sev s={i.severity} />{i.status !== "open" && <span className="pill">resolved</span>}<span className="t">{i.title}</span></div>
              <div className="m"><span className="mono">{i.id}</span><span>{i.catalog_id}</span>
                {i.children > 0 && <span>{i.children} child findings</span>}<span>since {fmtT(i.first_seen_t)}</span></div>
            </button>
          ))}
          {!list.length && <div className="empty">No incidents.</div>}
        </div>
      </Card>
      {current ? <Detail id={current} snap={snap} select={select} /> : <Card><div className="empty">Select an incident.</div></Card>}
    </div>
  );
}

function Detail({ id, snap, select }: { id: string; snap: Snapshot; select: (id: string) => void }) {
  const [d, setD] = useState<IncidentDetail | null>(null);
  const tick = Math.floor(snap.clock.t / 5);
  useEffect(() => { api.incident(id).then(setD).catch(() => setD(null)); }, [id, tick, snap.catalog.version]);
  if (!d || d.id !== id) return <Card><div className="empty">Loading…</div></Card>;
  const cat = d.catalog ?? ({} as IncidentDetail["catalog"]);
  const parent = d.parent ? snap.incidents.find((i) => i.id === d.parent) : null;
  return (
    <div className="grid" style={{ gap: 14 }}>
      <Card>
        <div className="row"><Sev s={d.severity} /><span className="pill">{d.catalog_id}</span><span className="pill">{d.status}</span>
          <span className="pill">confidence {Math.round(d.confidence * 100)}%</span><span className="pill">blast radius: {d.blast_radius}</span></div>
        <h2 style={{ margin: "8px 0 4px", fontSize: 18 }}>{d.title}</h2>
        {cat.plain && <p className="ink2" style={{ margin: 0 }}>{cat.plain}</p>}
        {parent && <p className="small">Part of <a href="#" onClick={(e) => { e.preventDefault(); select(parent.id); }}>{parent.id}: {parent.title}</a></p>}
        <dl className="kv" style={{ marginTop: 12 }}>
          <dt>When</dt><dd className="tabnum">first {fmtT(d.first_seen_t)} · last {fmtT(d.updated_t)} · {d.count} observations</dd>
          {d.network && <><dt>Network</dt><dd>{d.network}</dd></>}
          <dt>Where</dt><dd><div className="chips">
            {d.where.sensors.map((s) => <span className="chip" key={s}>{s}</span>)}
            {d.where.channels.map((c) => <span className="chip" key={c}>ch {c}</span>)}
            {d.where.aps.slice(0, 30).map((a) => <span className="chip mono" key={a}>{a}</span>)}
            {d.where.aps.length > 30 && <span className="chip">+{d.where.aps.length - 30}</span>}
          </div></dd>
          {d.devices_affected > 0 && <><dt>Devices</dt><dd>{d.devices_affected} affected <span className="muted small">({d.devices.slice(0, 6).join(", ")}{d.devices.length > 6 ? ", …" : ""})</span></dd></>}
          {Object.keys(d.children_by_type).length > 0 && <><dt>Child findings</dt><dd><div className="chips">{Object.entries(d.children_by_type).map(([k, v]) => <span className="chip" key={k}>{k} × {v}</span>)}</div></dd></>}
          {typeof d.metrics.per_channel === "object" && d.metrics.per_channel && <><dt>Per channel</dt><dd><div className="chips">{Object.entries(d.metrics.per_channel as Record<string, number>).map(([c, v]) => <span className="chip" key={c}>ch {c}: {v}</span>)}</div></dd></>}
        </dl>
      </Card>

      {d.signature && (
        <Card title="What the air shows" sub="Header-only evidence, cross-compared across sensors.">
          <dl className="kv tabnum">
            <dt>Where it stops</dt><dd>{d.signature.last_step}</dd>
            <dt>Re-ask interval</dt><dd>{d.signature.reask_s ?? "–"} s (median)</dd>
            <dt>Kicked after</dt><dd>{d.signature.kick_s ?? "–"} s, reason {d.signature.deauth_reason ?? "–"} (802.1X authentication failed)</dd>
            <dt>Devices heard answering</dt><dd>{d.signature.devices_heard_answering} of {d.devices_affected} (the rest are out of sensor range for uplink)</dd>
          </dl>
          {d.control?.map((c) => (
            <div key={c.network} className={`callout ${c.healthy ? "good" : "warn"}`} style={{ marginTop: 10 }}>
              <b>Control group:</b> {c.network} ({c.kind}) on {c.on_same_aps} of the same access points: {c.connected}/{c.attempts} joins connected.{" "}
              {c.healthy ? "Same radios work → not a radio problem." : "Also struggling → check shared infrastructure."}
            </div>
          ))}
        </Card>
      )}

      <FixPanel id={id} rec={snap.proposals[id]} agent={snap.agent} />

      <div className="grid g-2e">
        <Card title="Evidence" sub="Frame references (sensor : frame number).">
          <ul className="clean evidence">{d.evidence.map((e, n) => <li key={n}><span className="mono">{e.sensor}{e.frame ? `:${e.frame}` : ""}</span> {e.what}</li>)}</ul>
          {!d.evidence.length && <div className="muted small">Aggregated metric; no single frame.</div>}
        </Card>
        <Card title="From the error catalog" sub={cat.name}>
          {cat.likely_causes?.length > 0 && <><b className="small">Likely causes</b><ul className="clean small">{cat.likely_causes.map((c) => <li key={c}>{c}</li>)}</ul></>}
          {cat.confirm_outside_headers?.length > 0 && <><b className="small">Confirm outside the captures</b><ul className="clean small">{cat.confirm_outside_headers.map((c) => <li key={c}>{c}</li>)}</ul></>}
          {cat.normal_lookalike && <p className="small muted">Not to confuse with: {cat.normal_lookalike}</p>}
        </Card>
      </div>

      {d.children_list.length > 0 && (
        <Card title={`Child findings (${d.children_list.length})`} sub="Per-device and symptom findings grouped under this root.">
          <div className="scroll" style={{ maxHeight: 320 }}>
            <table className="t"><thead><tr><th>Id</th><th>Type</th><th>Finding</th><th>First</th><th>Count</th></tr></thead>
              <tbody>{d.children_list.map((c) => (
                <tr key={c.id} className="click" onClick={() => select(c.id)}><td className="mono">{c.id}</td><td>{c.catalog_id}</td><td>{c.title}</td><td className="tabnum">{fmtT(c.first_seen_t)}</td><td className="tabnum">{c.count}</td></tr>
              ))}</tbody></table>
          </div>
        </Card>
      )}
    </div>
  );
}

const METRIC_LABEL: Record<string, string> = {
  reason23_kicks: "802.1X kicks (reason 23)", reason2_rejects: "Fast-rejects (reason 2)", login_success_rate: "Login success rate",
  failing_devices: "Failing devices", probe_replies_per_s: "Probe replies per second", retry_pct: "Retry %",
  missing_networks: "Missing networks", unknown_events: "Unmatched events",
};

function FixPanel({ id, rec, agent }: { id: string; rec?: ProposalRecord; agent: Snapshot["agent"] }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      await api.fix(id);
      const j = await waitJob(`fix:${id}`);
      if (j.state === "error") setErr(j.error ?? "failed");
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  };
  const decide = async (decision: string) => { try { await api.fixDecision(id, decision); } catch (e) { setErr(String(e)); } };
  const p = rec?.proposal;
  const modeLabel = useMemo(() => (agent.mode === "claude" ? `Claude (${agent.model})` : "Offline catalog playbook"), [agent]);
  return (
    <section className="card">
      <div className="card-head">
        <div><h3>How to fix it <span className="pill" style={{ marginLeft: 6 }}>Part 2 · AI agent</span></h3>
          <p className="sub">Read-only investigation → cause, deciding check, fix, owner, risk and a success test Part 1 measures live. Mode: {modeLabel}.</p></div>
        {!p && <button className="btn primary" disabled={busy} onClick={run}>{busy ? "Investigating…" : "Explain & propose fix"}</button>}
      </div>
      {err && <div className="callout bad">{err}</div>}
      {p && rec && (
        <div className="fix">
          <div className="row"><span className="pill">{rec.meta.mode === "claude" ? `Claude · ${rec.meta.turns ?? "?"} turns · ${rec.meta.tool_calls?.length ?? 0} tool calls` : "offline playbook"}</span>
            <span className="pill">confidence {Math.round(p.confidence * 100)}%</span><span className="pill">owner: {p.owner}</span><span className="pill">risk: {p.risk}</span>
            <span className="pill">status: {rec.status}</span><span className="spacer" />
            {rec.status === "proposed" && <><button className="btn good" onClick={() => decide("approve")}>✓ Approve</button><button className="btn danger" onClick={() => decide("reject")}>✕ Reject</button><button className="btn" onClick={run} disabled={busy}>↻ Re-run</button></>}
          </div>
          {rec.meta.note && <div className="callout warn small" style={{ marginTop: 8 }}>{rec.meta.note}</div>}
          <p style={{ marginTop: 10, fontSize: 14.5 }}>{p.plain_summary}</p>
          {p.needs_human && <div className="callout warn small">Needs a person: {p.needs_human}</div>}
          <h4>Most likely cause</h4><div>{p.root_cause}</div>
          <h4>The one check that confirms it</h4><div>{p.deciding_check}</div>
          <h4>Fix steps</h4><ol className="clean">{p.fix_steps.map((s) => <li key={s}>{s}</li>)}</ol>
          <h4>Other hypotheses</h4>
          {p.hypotheses.map((h) => (
            <div key={h.cause} className="crit" style={{ gridTemplateColumns: "1fr 140px" }}>
              <span>{h.cause}{h.refuting_evidence.length > 0 && <span className="muted small"> · against: {h.refuting_evidence.join("; ")}</span>}</span>
              <div className="bar-bg" title={`${Math.round(h.likelihood * 100)}%`}><div className="bar-fg" style={{ width: `${Math.round(h.likelihood * 100)}%` }} /></div>
            </div>
          ))}
          <h4>Rollback</h4><div className="small">{p.rollback}</div>
          <h4>Success test {rec.status === "approved" ? "(measured live)" : "(measured after approval)"}</h4>
          {p.success_criteria.map((c, n) => {
            const live = rec.success?.[n];
            return (
              <div className="crit" key={n}>
                <span aria-hidden>{live ? (live.met ? "✓" : "✕") : "○"}</span>
                <span>{METRIC_LABEL[c.metric] ?? c.metric} {c.op} {c.value} over {Math.round(c.window_s / 60)} min</span>
                <span className="tabnum small" style={{ color: live ? (live.met ? "var(--good-ink)" : "var(--critical)") : "var(--muted)" }}>
                  {live ? `now ${live.current ?? "–"} · ${live.met ? "met" : "not met"}` : "pending"}</span>
              </div>
            );
          })}
          <p className="small muted" style={{ marginTop: 8 }}>Evidence: {p.evidence_ids.join(", ")}{rec.meta.validation_errors.length ? ` · validation: ${rec.meta.validation_errors.join("; ")}` : " · passed validation"}</p>
        </div>
      )}
    </section>
  );
}
