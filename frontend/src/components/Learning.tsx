import { useState } from "react";
import { api, fmtT, nextSyntheticCode, type Draft, type Snapshot } from "../api";
import { Card, Icon, Kpi, Sev, providerLabel, providerPill } from "./ui";

export function Learning({ snap }: { snap: Snapshot }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const drafts = [...snap.drafts].reverse();
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setErr(null);
    try { await fn(); } catch (e) { setErr(String(e)); }
    setBusy(null);
  };
  const inject = (code: number) => run("inject", () => api.inject(25, code));
  const open = snap.clusters.filter((c) => c.count > 0);
  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="grid g-kpi">
        <Kpi label="Catalog version" value={snap.catalog.version} foot={`${snap.catalog.entries} entries · ${snap.catalog.categories} categories`} />
        <Kpi label="Learned entries" value={snap.catalog.extensions} foot="auto-adopted, no human click" />
        <Kpi label="Unmatched events" value={snap.unknown.count} tone={snap.unknown.count ? "warn" : "good"} foot="saved as OTHER, never dropped" />
        <Kpi label="Clusters to review" value={open.length} />
        <Kpi label="Drafts" value={snap.drafts.length} foot={`${snap.drafts.filter((d) => d.status === "adopted").length} adopted`} />
        <Kpi label="Discovery mode" value={snap.agent.mode === "offline" ? "Offline" : providerLabel(snap.agent.mode)} foot={snap.agent.mode === "offline" ? "heuristic drafts" : snap.agent.model} />
      </div>

      <Card title="How this works" sub="Every frame, sequence and metric is matched against the error catalog. Known → incident → fix. Unknown → clustered → drafted → validated and back-tested → automatically adopted, no human click → the catalog grows and detection updates immediately, and the newly-classified events re-run through incident detection.">
        <div className="callout info small">
          This runs on its own in the background as soon as a cluster of unmatched events is large enough — nothing here needs a click. A batch of <b>synthetic</b> test frames (access-point disconnects with a reason code the IEEE 802.11 standard does not define) was already injected automatically when the app started, so opening this tab shows you the live flow: a cluster forming below, then a draft, then it adopting itself into the catalog.
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn" disabled={busy === "inject"} onClick={() => inject(nextSyntheticCode())}>{busy === "inject" ? "Injecting…" : "Inject another batch of 25"}</button>
          </div>
        </div>
        {err && <div className="callout bad" style={{ marginTop: 8 }}>{err}</div>}
      </Card>

      <Card title="Unmatched clusters (OTHER)" sub="Grouped by signature: kind, code or transition, who sent it, frame type. The catalog-learning agent drafts and adopts each one on its own — nothing to click.">
        <table className="t tabnum">
          <thead><tr><th>Cluster</th><th>Kind</th><th>Signature</th><th>Events</th><th>Sensors</th><th>Seen</th><th>Status</th></tr></thead>
          <tbody>{open.map((c) => (
            <tr key={c.cluster_id}><td className="mono">{c.cluster_id}</td><td>{c.kind}{c.synthetic && <span className="pill" style={{ marginLeft: 6 }}>synthetic</span>}</td>
              <td>{c.frame_kind} by {c.sender ?? "?"}, {c.what} {c.code ?? ""}<div className="muted small">{c.ieee_text}</div></td>
              <td>{c.count}</td><td>{c.sensors.map((s) => `S${s}`).join(" ")}</td><td>{fmtT(c.first_t)}–{fmtT(c.last_t)}</td>
              <td><span className="pill pill-ai">{Icon.ai}agent working…</span></td></tr>
          ))}</tbody>
        </table>
        {!open.length && <div className="empty">No unmatched events. Everything seen so far is in the catalog.</div>}
      </Card>

      {drafts.map((d) => <DraftCard key={d.draft_id} d={d} />)}
    </div>
  );
}

function DraftCard({ d }: { d: Draft }) {
  const e = d.entry;
  const tone = d.status === "adopted" ? "good" : d.status === "ready_for_review" ? "info" : d.status === "rejected" ? "warn" : "bad";
  const statusLabel = d.status === "ready_for_review"
    ? <span className="pill pill-ai">{Icon.ai}adopting…</span>
    : <span className={`sev ${tone === "good" ? "good" : "info"}`}>{d.status.replaceAll("_", " ")}</span>;
  return (
    <Card title={<>Draft {d.draft_id} <span className="pill" style={{ marginLeft: 6 }}>{providerPill(d.meta.mode, undefined, "offline heuristic")}</span>
      <span className="pill" style={{ marginLeft: 6 }}>{d.trigger === "auto" ? "auto · no human click" : "manual"}</span></>}
      sub={`From ${d.cluster.cluster_id}: ${d.cluster.count} events`}
      right={statusLabel}>
      {d.meta.note && <div className="callout warn small">{d.meta.note}</div>}
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
