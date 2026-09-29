import { useEffect, useRef, useState } from "react";

export type Severity = "critical" | "high" | "medium" | "low" | "info" | "unknown";

export interface Where { aps: string[]; channels: number[]; sensors: string[] }

export interface IncidentSummary {
  id: string; catalog_id: string; title: string; status: string; severity: Severity; confidence: number;
  scope: string; is_root: boolean; network: string | null; blast_radius: string; where: Where;
  devices_affected: number; count: number; first_seen_t: number; updated_t: number;
  children: number; parent: string | null; children_by_type: Record<string, number>; metrics: Record<string, unknown>;
}

export interface CatalogEntry {
  id: string; name: string; plain: string; signature: string; normal_lookalike: string;
  likely_causes: string[]; confirm_outside_headers: string[]; standard_fix: string[]; owner: string; default_severity: string;
}

export interface Control { network: string; kind: string; attempts: number; connected: number; on_same_aps: number; healthy: boolean }

export interface IncidentDetail extends IncidentSummary {
  devices: string[];
  evidence: { sensor: string; frame: number | null; what: string }[];
  catalog: CatalogEntry;
  children_list: IncidentSummary[];
  signature?: { last_step: string; reask_s: number | null; kick_s: number | null; deauth_reason: number | null; devices_heard_answering: number };
  control?: Control[];
  data_quality: string[];
}

export interface SeriesPoint {
  t: number; probe_resp: number; probe_retry: number; joins: number; connected: number; kicks: number;
  fast_rejects: number; leaves: number; frames: number; probe_per_s: number; retry_pct: number;
}

export interface Sensor {
  sensor: string; channel: number; frames: number; aps: number; bssids: number; networks: Record<string, number>;
  beacon_loss_pct: number | null; alive: boolean; last_t: number; flags: string[];
}

export interface DeviceRow {
  id: string; alias: string; class: string; network: string | null; ap: string | null; channel: number | null;
  sensors: number; state: string; attempts: number; connected: number; kicks: number; fast_rejects: number;
  answered: boolean; last_t: number;
}

export interface StoryStep { t: number; s: number; n: number; step: string; by: string | null; ap: string | null; detail: string }

export interface Criterion { metric: string; op: string; value: number; window_s: number; current?: number | null; met?: boolean }

export interface Proposal {
  plain_summary: string; root_cause: string; confidence: number;
  hypotheses: { cause: string; likelihood: number; supporting_evidence: string[]; refuting_evidence: string[] }[];
  deciding_check: string; fix_steps: string[]; owner: string; risk: string; rollback: string;
  success_criteria: Criterion[]; evidence_ids: string[]; needs_human: string | null;
}

export interface ProposalRecord {
  incident_id: string; catalog_id: string; proposal: Proposal; status: string; created_t: number; decided_t?: number;
  meta: { mode: string; model: string | null; seconds: number; validation_errors: string[]; note: string | null; turns?: number; tool_calls?: { tool: string }[] };
  success: Criterion[] | null;
}

export interface Cluster {
  cluster_id: string; kind: string; what: string; code: number | null; sender: string | null; frame_kind: string;
  count: number; first_t: number; last_t: number; sensors: number[]; devices: number; synthetic: boolean; ieee_text: string | null;
}

export interface Draft {
  draft_id: string; cluster: Cluster; status: string; validation_errors: string[];
  entry: { extends: string | null; category: string; name: string; plain: string; signature: string; default_severity: string;
    likely_causes: string[]; confirm_outside_headers: string[]; standard_fix: string[]; owner: string;
    reason_codes: number[]; status_codes: number[]; vendor_specific_codes: boolean; rule: Record<string, unknown>; reasoning: string };
  backtest: { ok: boolean; frames_matched_in_cluster?: number; frames_matched_outside_cluster?: number; frames_scanned?: number; groups_firing?: number };
  meta: { mode: string; note: string | null };
  trigger: "manual" | "auto";
  adopted?: { entry_id: string; catalog_version: string; reclassified_events: number };
}

export interface FeedItem { t: number; kind: string; text: string; severity: string; ref: string | null }

export interface AlertItem {
  incident_id: string; catalog_id: string; title: string; severity: "critical" | "high" | "medium" | "low" | "info" | "unknown";
  created_t: number; sensors: string[]; priority: string; source: string;
}

export interface IncidentApproval {
  approved: boolean; priority: string; selected_sensors: string[]; note?: string | null; updated_t?: number;
}

export interface Snapshot {
  clock: { state: string; speed: number; source: string | null; duration: number | null; fps: number; t: number; frames: number };
  kpi: { devices: number; failing: number; attempts: number; connected: number; kicks: number; fast_rejects: number;
    open_incidents: number; probe_per_s: number; retry_pct: number; unknown: number; time_to_root_s: number | null };
  incidents: IncidentSummary[];
  series: { site: SeriesPoint[]; channels: number[]; beacon_air_pct: Record<string, number>; retry_pct: Record<string, number>;
    sensors: string[]; per_sensor: Record<string, Array<Record<string, number>>> };
  sensors: Sensor[];
  aps: { networks: { label: string; kind: string | null }[]; rows: { ap: string; sensor: string; channel: number; networks: Record<string, boolean>; joins: number; failures: number }[] };
  networks: { label: string; kind: string | null; attempts: number; connected: number }[];
  devices: DeviceRow[];
  unknown: { count: number; total: number; recent: { id: string; kind: string; t: number; sensor: number; device: string | null; detail: Record<string, unknown>; synthetic: boolean; reclassified?: string }[] };
  observations: { cid: string; t: number; device?: string; ap?: string; text?: string }[];
  feed: FeedItem[];
  catalog: { version: string; entries: number; categories: number; extensions: number };
  data_quality: { key: string; t: number; text: string; sensors: string[] }[];
  proposals: Record<string, ProposalRecord>;
  alerts: AlertItem[];
  approvals: Record<string, IncidentApproval>;
  agent: { mode: string; model: string };
  clusters: Cluster[];
  drafts: Draft[];
}

export type Conn = "connecting" | "live" | "offline";

export function useSnapshot(): { snap: Snapshot | null; conn: Conn } {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [conn, setConn] = useState<Conn>("connecting");
  const es = useRef<EventSource | null>(null);
  useEffect(() => {
    let closed = false;
    fetch("/api/snapshot").then((r) => r.json()).then((s) => { if (!closed && s && s.clock) setSnap(s); }).catch(() => {});
    const src = new EventSource("/api/stream");
    es.current = src;
    src.addEventListener("snapshot", (ev) => {
      setConn("live");
      setSnap(JSON.parse((ev as MessageEvent).data));
    });
    src.onerror = () => setConn("offline");
    src.onopen = () => setConn("live");
    return () => { closed = true; src.close(); };
  }, []);
  return { snap, conn };
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
}

export const api = {
  replay: (action: string, speed?: number, source?: string) => post("/api/replay", { action, speed, source }),
  incident: (id: string): Promise<IncidentDetail> => fetch(`/api/incidents/${id}`).then((r) => r.json()),
  device: (id: string): Promise<DeviceRow & { story: StoryStep[] }> => fetch(`/api/devices/${id}`).then((r) => r.json()),
  fix: (id: string) => post<{ state: string }>(`/api/incidents/${id}/fix`),
  fixDecision: (id: string, decision: string, note?: string) => post(`/api/incidents/${id}/fix/decision`, { decision, note }),
  approveIncident: (id: string, payload: { approve?: boolean; priority?: string; selected_sensors?: string[]; note?: string }) =>
    post<IncidentApproval>(`/api/incidents/${id}/approval`, payload),
  draft: (clusterId: string) => post<{ state: string }>(`/api/discovery/${clusterId}/draft`),
  draftDecision: (id: string, decision: string, note?: string) => post<Draft>(`/api/discovery/drafts/${id}/decision`, { decision, note }),
  inject: (count = 25, code = 250) => post("/api/debug/inject-unknown", { count, code }),
  job: (key: string): Promise<{ state: string; error?: string; result?: unknown }> => fetch(`/api/jobs/${key}`).then((r) => r.json()),
};

export function nextSyntheticCode(): number {
  try {
    const raw = Number(sessionStorage.getItem("af-synth-code-seq") ?? "250");
    sessionStorage.setItem("af-synth-code-seq", String(raw + 1));
    return raw;
  } catch {
    return 250 + Math.floor(Math.random() * 40);
  }
}

export async function waitJob(key: string, onTick?: () => void): Promise<{ state: string; error?: string; result?: unknown }> {
  for (let i = 0; i < 600; i++) {
    const j = await api.job(key);
    if (j.state === "done" || j.state === "error") return j;
    onTick?.();
    await new Promise((r) => setTimeout(r, 400));
  }
  return { state: "error", error: "timed out" };
}

export const fmtT = (t: number | null | undefined): string => {
  if (t == null) return "–";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
};

export const pct = (v: number | null | undefined, d = 0) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);
