import { useEffect, useState, type ReactNode } from "react";
import type { Severity } from "../api";

const SEV_ICON: Record<string, string> = { critical: "▲", high: "▲", medium: "◆", low: "●", info: "●", unknown: "?", good: "✓" };
const SEV_LABEL: Record<string, string> = { critical: "Critical", high: "High", medium: "Medium", low: "Low", info: "Info", unknown: "Unknown", good: "Healthy" };

export function Sev({ s }: { s: Severity | "good" | string }) {
  return <span className={`sev ${s}`}><span aria-hidden>{SEV_ICON[s] ?? "●"}</span>{SEV_LABEL[s] ?? s}</span>;
}

// AI provider names, keyed by the backend's `mode` value (config.AGENT_MODE / mode()).
const PROVIDER_NAME: Record<string, string> = { claude: "Claude", openrouter: "DeepSeek (OpenRouter)" };

/** "Claude (claude-opus-5)" / "DeepSeek (OpenRouter) (deepseek/deepseek-v4.1-flash)" / "Offline catalog playbook". */
export function providerLabel(mode: string, model?: string | null): string {
  const name = PROVIDER_NAME[mode];
  return name ? `${name}${model ? ` (${model})` : ""}` : "Offline catalog playbook";
}

/** Short pill text for a proposal/draft's meta.mode: "Claude · 4 turns · 2 tool calls" or "offline playbook". */
export function providerPill(mode: string, detail?: string, offlineLabel = "offline playbook"): string {
  const name = PROVIDER_NAME[mode];
  return name ? `${name}${detail ? ` · ${detail}` : ""}` : offlineLabel;
}

const STATE: Record<string, { label: string; color: string; icon: string }> = {
  excluded: { label: "Fast-rejected", color: "var(--critical)", icon: "⛔" },
  failing: { label: "Failing to log in", color: "var(--critical)", icon: "✕" },
  joining: { label: "Joining", color: "var(--serious)", icon: "…" },
  searching: { label: "Searching (no network)", color: "var(--warning)", icon: "⌕" },
  left: { label: "Left", color: "var(--muted)", icon: "↩" },
  connected: { label: "Connected", color: "var(--good)", icon: "✓" },
  seen: { label: "Seen", color: "var(--muted)", icon: "·" },
};

export function State({ s }: { s: string }) {
  const x = STATE[s] ?? STATE.seen;
  return <span className="state" style={{ color: x.color }}><span aria-hidden>{x.icon}</span><span style={{ color: "var(--ink)" }}>{x.label}</span></span>;
}

export function Kpi({ label, value, foot, tone }: { label: string; value: ReactNode; foot?: ReactNode; tone?: "bad" | "good" | "warn" }) {
  const color = tone === "bad" ? "var(--critical)" : tone === "good" ? "var(--good-ink)" : tone === "warn" ? "var(--serious)" : "var(--ink)";
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value tabnum" style={{ color }}>{value}</div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export function Card({ title, sub, right, children, className = "" }: { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="card-head">
          <div>{title && <h3>{title}</h3>}{sub && <p className="sub">{sub}</p>}</div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export type Palette = { s1: string; s2: string; s3: string; s4: string; ink2: string; muted: string; line: string; axis: string; surface: string };

function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string) => cs.getPropertyValue(n).trim();
  return { s1: v("--s1"), s2: v("--s2"), s3: v("--s3"), s4: v("--s4"), ink2: v("--ink-2"), muted: v("--muted"), line: v("--line"), axis: v("--axis"), surface: v("--surface") };
}

export function usePalette(themeKey: string): Palette {
  const [p, setP] = useState<Palette>(readPalette);
  useEffect(() => {
    setP(readPalette());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setP(readPalette());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [themeKey]);
  return p;
}

export const Icon = {
  play: <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><path d="M4 3l9 5-9 5z" fill="currentColor" /></svg>,
  pause: <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><path d="M4 3h3v10H4zM9 3h3v10H9z" fill="currentColor" /></svg>,
  restart: <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><path d="M3 8a5 5 0 1 0 1.5-3.5M3 2v3h3" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" /></svg>,
  sun: <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><circle cx="8" cy="8" r="3" fill="currentColor" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M3 13l1.4-1.4M11.6 4.4L13 3" stroke="currentColor" strokeWidth="1.5" /></svg>,
  moon: <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><path d="M13 10A6 6 0 0 1 6 3a6 6 0 1 0 7 7z" fill="currentColor" /></svg>,
  wifi: <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden><path d="M5 12a10 10 0 0 1 14 0M8.5 15.5a5 5 0 0 1 7 0" stroke="white" strokeWidth="2.2" fill="none" strokeLinecap="round" /><circle cx="12" cy="19" r="1.6" fill="white" /></svg>,
};
