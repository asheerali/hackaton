"""Live measurement of a proposal's success criteria (Part 1 watches the fix)."""

from __future__ import annotations

from ...engine import Engine

OPS = {"==": lambda a, b: a == b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b,
       ">": lambda a, b: a > b}


def measure(e: Engine, metric: str, window_s: float, net: str | None) -> float | None:
    from ...config import BUCKET_S

    cur = int(e.t // BUCKET_S)
    nb = max(1, int(window_s // BUCKET_S))
    win = [bk[i] for bk in e.buckets.values() for i in range(cur - nb, cur) if i in bk]
    t_lo = e.t - window_s
    if metric == "reason23_kicks":
        return sum(b.kicks for b in win)
    if metric == "reason2_rejects":
        return sum(b.fast_rejects for b in win)
    if metric == "probe_replies_per_s":
        return round(sum(b.probe_resp for b in win) / (nb * BUCKET_S), 1)
    if metric == "retry_pct":
        pr = sum(b.probe_resp for b in win)
        return round(100 * sum(b.probe_resp_retry for b in win) / pr, 1) if pr else 0.0
    if metric == "login_success_rate":
        att = [a for a in e.attempts_all if a.t0 >= t_lo and (net is None or (a.net or e._net_of_bssid(a.bssid)) == net)]
        return round(sum(a.outcome == "connected" for a in att) / len(att), 3) if att else None
    if metric == "failing_devices":
        return sum(1 for d in e.devices.values() if d.state in ("failing", "excluded"))
    if metric == "missing_networks":
        return sum(1 for i in e.inc.items.values() if i.cid == "DISC-01" and i.status == "open")
    if metric == "unknown_events":
        return sum(1 for u in e.unknown if u["t"] >= t_lo)
    return None


def check_success(e: Engine, rec: dict) -> list[dict]:
    net = e.inc.items[rec["incident_id"]].net if rec["incident_id"] in e.inc.items else None
    out = []
    for c in rec["proposal"]["success_criteria"]:
        v = measure(e, c["metric"], c["window_s"], net)
        out.append({**c, "current": v, "met": v is not None and OPS[c["op"]](v, c["value"])})
    return out
