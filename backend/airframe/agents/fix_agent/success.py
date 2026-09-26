"""Live measurement of a proposal's success criteria (Part 1 watches the fix).

`sensors`, when given, scopes measurement to just those sensor numbers - this is what the
approval flow's "which sensors' data to include" picker controls (see server.py's Decision
model): a metric like reason23_kicks or probe_replies_per_s is only counted from the selected
sensors' captures. Metrics with no natural per-sensor meaning (failing_devices, missing_networks)
ignore `sensors` - a device or a missing-network incident isn't "of" one sensor.
"""

from __future__ import annotations

from ...engine import Engine

OPS = {"==": lambda a, b: a == b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b,
       ">": lambda a, b: a > b}


def measure(e: Engine, metric: str, window_s: float, net: str | None, sensors: list[int] | None = None) -> float | None:
    from ...config import BUCKET_S

    cur = int(e.t // BUCKET_S)
    nb = max(1, int(window_s // BUCKET_S))
    bucket_sets = e.buckets.items() if sensors is None else ((s, bk) for s, bk in e.buckets.items() if s in sensors)
    win = [bk[i] for _, bk in bucket_sets for i in range(cur - nb, cur) if i in bk]
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
        att = [a for a in e.attempts_all if a.t0 >= t_lo and (net is None or (a.net or e._net_of_bssid(a.bssid)) == net)
               and (sensors is None or a.s in sensors)]
        return round(sum(a.outcome == "connected" for a in att) / len(att), 3) if att else None
    if metric == "failing_devices":
        return sum(1 for d in e.devices.values() if d.state in ("failing", "excluded"))
    if metric == "missing_networks":
        return sum(1 for i in e.inc.items.values() if i.cid == "DISC-01" and i.status == "open")
    if metric == "unknown_events":
        return sum(1 for u in e.unknown if u["t"] >= t_lo and (sensors is None or u["sensor"] in sensors))
    return None


def check_success(e: Engine, rec: dict) -> list[dict]:
    net = e.inc.items[rec["incident_id"]].net if rec["incident_id"] in e.inc.items else None
    sensors = rec.get("sensors")  # e.g. [1, 3, 5] from the approval picker; None = all sensors
    out = []
    for c in rec["proposal"]["success_criteria"]:
        v = measure(e, c["metric"], c["window_s"], net, sensors)
        out.append({**c, "current": v, "met": v is not None and OPS[c["op"]](v, c["value"])})
    return out
