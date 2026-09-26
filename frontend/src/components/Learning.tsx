import { useState } from "react";
import { api, fmtT, waitJob, type Draft, type Snapshot } from "../api";
import { Card, Kpi, Sev, providerLabel, providerPill } from "./ui";

export function Learning({ snap }: { snap: Snapshot }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const drafts = [...snap.drafts].reverse();
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setErr(null);
    try { await fn(); } catch (e) { setErr(String(e)); }
    setBusy(null);
  };
  const draft = (cid: string) => run(cid, async () => {
    await api.draft(cid);
    const j = await waitJob(`draft:${cid}`);
    if (j.state === "error") throw new Error(j.error);
  });
  const open = snap.clusters.filter((c) => c.count > 0);
  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="grid g-kpi">
        <Kpi label="Catalog version" value={snap.catalog.version} foot={`${snap.catalog.entries} entries · ${snap.catalog.categories} categories`} />
        <Kpi label="Learned entries" value={snap.catalog.extensions} foot="approved by a reviewer" />
        <Kpi label="Unmatched events" value={snap.unknown.count} tone={snap.unknown.count ? "warn" : "good"} foot="saved as OTHER, never dropped" />
        <Kpi label="Clusters to review" value={open.length} />
        <Kpi label="Drafts" value={snap.drafts.length} foot={`${snap.drafts.filter((d) => d.status === "adopted").length} adopted`} />
        <Kpi label="Discovery mode" value={snap.agent.mode === "offline" ? "Offline" : providerLabel(snap.agent.mode)} foot={snap.agent.mode === "offline" ? "heuristic drafts" : snap.agent.model} />
      </div>

      <Card title="How Part 3 works" sub="Every frame, sequence and metric is matched against the error catalog. Known → incident (Part 1) → fix (Part 2). Unknown → OTHER → clustered → drafted → validated and back-tested → a person approves → the catalog grows and detection updates immediately.">
        <div className="callout info small">
          In these 30 minutes of captures every code is already in the catalog, so there are no unmatched events of their own. To demonstrate the loop, inject clearly-marked <b>synthetic</b> test frames: access-point disconnects with reason code 250, which the IEEE 802.11 standard does not define (a vendor-specific code).
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn" disabled={busy === "inject"} onClick={() => run("inject", () => api.inject(25, 250))}>Inject 25 synthetic events (reason 250)</button>
          </div>
        </div>
        {err && <div className="callout bad" style={{ marginTop: 8 }}>{err}</div>}
      </Card>

      <Card title="Unmatched clusters (OTHER)" sub="Grouped by signature: kind, code or transition, who sent it, frame type.">
        <table className="t tabnum">
          <thead><tr><th>Cluster</th><th>Kind</th><th>Signature</th><th>Events</th><th>Sensors</th><th>Seen</th><th /></tr></thead>
          <tbody>{open.map((c) => (
            <tr key={c.cluster_id}><td className="mono">{c.cluster_id}</td><td>{c.kind}{c.synthetic && <span className="pill" style={{ marginLeft: 6 }}>synthetic</span>}</td>
              <td>{c.frame_kind} by {c.sender ?? "?"}, {c.what} {c.code ?? ""}<div className="muted small">{c.ieee_text}</div></td>
              <td>{c.count}</td><td>{c.sensors.map((s) => `S${s}`).join(" ")}</td><td>{fmtT(c.first_t)}–{fmtT(c.last_t)}</td>
              <td><button className="btn primary" disabled={busy === c.cluster_id} onClick={() => draft(c.cluster_id)}>{busy === c.cluster_id ? "Drafting…" : "Draft catalog entry"}</button></td></tr>
          ))}</tbody>
        </table>
        {!open.length && <div className="empty">No unmatched events. Everything seen so far is in the catalog.</div>}
      </Card>

      {drafts.map((d) => <DraftCard key={d.draft_id} d={d} />)}
    </div>
  );
}

function DraftCard({ d }: { d: Draft }) {
  const [err, setErr] = useState<string | null>(null);
  const e = d.entry;
  const decide = async (decision: string) => { try { await api.draftDecision(d.draft_id, decision); } catch (x) { setErr(String(x)); } };
  const tone = d.status === "adopted" ? "good" : d.status === "ready_for_review" ? "info" : d.status === "rejected" ? "warn" : "bad";
  return (
    <Card title={<>Draft {d.draft_id} <span className="pill" style={{ marginLeft: 6 }}>{providerPill(d.meta.mode, undefined, "offline heuristic")}</span></>}
      sub={`From ${d.cluster.cluster_id}: ${d.cluster.count} events`}
      right={d.status === "ready_for_review" ? <div className="row"><button className="btn good" onClick={() => decide("approve")}>✓ Approve & add to catalog</button><button className="btn danger" onClick={() => decide("reject")}>✕ Reject (mark benign)</button></div> : <span className={`sev ${tone === "good" ? "good" : "info"}`}>{d.status.replaceAll("_", " ")}</span>}>
      {d.meta.note && <div className="callout warn small">{d.meta.note}</div>}
      {err && <div className="callout bad small">{err}</div>}
      <div className="row" style={{ margin: "6px 0" }}><Sev s={e.default_severity} /><b>{e.name}</b><span className="pill">{e.category}</span><span className="pill">owner: {e.owner}</span>
        {e.vendor_specific_codes && <span className="pill">vendor-specific code</span>}{e.extends && <span className="pill">extends {e.extends}</span>}</div>
      <p className="ink2" style={{ margin: "4px 0 10px" }}>{e.plain}</p>
      <div className="grid g-2e">
        <dl className="kv small">
          <dt>Looks like</dt><dd>{e.signature}</dd>
          <dt>Likely causes</dt><dd>{e.likely_causes.join("; ")}</dd>
          <dt>Confirm with</dt><dd>{e.confirm_outside_headers.join("; ")}</dd>
          <dt>Standard fix</dt><dd>{e.standard_fix.join("; ")}</dd>
        </dl>
        <div>
          <b className="small">Detection rule (safe JSON, interpreted)</b>
          <pre className="mono" style={{ background: "var(--surface-2)", padding: 10, borderRadius: 8, overflowX: "auto", margin: "4px 0 8px" }}>{JSON.stringify(e.rule, null, 1)}</pre>
          <div className={`callout ${d.backtest.ok ? "good" : "bad"} small`}>
            Back-test: {d.backtest.ok ? "passes" : "fails"} · matched {d.backtest.frames_matched_in_cluster ?? 0} cluster frames, {d.backtest.frames_matched_outside_cluster ?? 0} outside, of {d.backtest.frames_scanned?.toLocaleString() ?? 0} stored frames.
          </div>
          <div className={`callout ${d.validation_errors.length ? "bad" : "good"} small`} style={{ marginTop: 6 }}>
            Validation: {d.validation_errors.length ? d.validation_errors.join("; ") : "schema, codes and privacy checks pass"}
          </div>
          {d.adopted && <div className="callout good small" style={{ marginTop: 6 }}>Adopted as <b>{d.adopted.entry_id}</b> · catalog {d.adopted.catalog_version} · {d.adopted.reclassified_events} stored events re-classified. New frames with this code now become incidents.</div>}
        </div>
      </div>
    </Card>
  );
}
