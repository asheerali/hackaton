"""JSON views of engine state for the API, dashboard and agents. Only masked identifiers leave here."""

from __future__ import annotations

import statistics as st
from collections import Counter

from . import config
from .engine import Engine, channel_of
from .incidents import Incident

STATE_ORDER = {"excluded": 0, "failing": 1, "joining": 2, "searching": 3, "left": 4, "connected": 5, "seen": 6}


def _median(xs):
    return round(st.median(xs), 2) if xs else None


def incident_dict(e: Engine, i: Incident, full: bool = False) -> dict:
    kids = [e.inc.items[c] for c in i.children]
    d = {
        "id": i.id, "catalog_id": i.cid, "title": i.title or i.cid, "status": i.status, "severity": i.severity,
        "confidence": round(i.confidence, 2), "scope": i.scope, "is_root": i.is_root, "network": i.net,
        "blast_radius": "site" if i.is_root or i.scope == "site" else ("ap" if i.scope == "ap" else ("channel" if i.scope == "sensor" else "device")),
        "where": {"aps": sorted(e.alias_ap(a) for a in i.aps), "channels": sorted(c for c in i.channels if c is not None),
                  "sensors": [f"S{s}" for s in sorted(i.sensors)]},
        "devices_affected": len(i.devices), "count": i.count,
        "first_seen_t": round(i.first_t, 1), "updated_t": round(i.last_t, 1),
        "children": len(kids), "parent": i.parent,
        "children_by_type": dict(Counter(k.cid for k in kids)),
        "metrics": i.metrics,
    }
    if full:
        entry = e.cat.entry(i.cid) or {}
        d["devices"] = sorted(e.alias_dev(x) for x in i.devices)
        d["evidence"] = [{"sensor": f"S{s}", "frame": n, "what": w} for s, n, w in i.evidence]
        d["catalog"] = {k: entry.get(k) for k in ("id", "name", "plain", "signature", "normal_lookalike", "likely_causes",
                                                   "confirm_outside_headers", "standard_fix", "owner", "default_severity")}
        d["children_list"] = [incident_dict(e, k) for k in sorted(kids, key=lambda k: k.first_t)]
        if i.is_root:
            d["signature"] = {
                "last_step": "EAP Identity request, no method round",
                "reask_s": _median(e.reask.get(i.net, [])), "kick_s": _median(e.kick_delay.get(i.net, [])),
                "deauth_reason": 23 if e.kick_delay.get(i.net) else None,
                "devices_heard_answering": sum(1 for x in i.devices if e.devices[x].answered),
            }
            d["control"] = control(e, i)
        d["data_quality"] = sorted({k.split(":")[0] for k in e.flags})
    return d


def control(e: Engine, root: Incident) -> list[dict]:
    """Other networks on the same AP radios: are their joins succeeding?"""
    out = []
    for net, c in e.net_stats().items():
        if net == root.net or net == "?":
            continue
        same = sum(1 for a in root.aps if net in e.aps.get(a, {}).get("nets", {}))
        out.append({"network": net, "kind": e.mk.network_kind(net), "attempts": c["attempts"], "connected": c["connected"],
                    "on_same_aps": same, "healthy": c["attempts"] > 0 and c["connected"] >= 0.9 * c["attempts"]})
    return out


def _dev_channel(e: Engine, d):
    ap = e.aps.get(d.ap or "")
    if ap:
        return e.sensors[min(ap["sensors"])].channel
    return e.sensors[min(d.sensors)].channel if d.sensors else None


def device_row(e: Engine, d) -> dict:
    state = d.state
    if d.attempts == 0 and state == "seen":
        state = "searching" if d.probe_ts or d.sensors else "seen"
    return {"id": d.id, "alias": e.alias_dev(d.id), "class": d.cclass, "network": d.net, "ap": e.alias_ap(d.ap),
            "channel": _dev_channel(e, d), "sensors": len(d.sensors),
            "state": state, "attempts": d.attempts, "connected": d.connected_n, "kicks": d.kicks,
            "fast_rejects": d.fast_rejects, "answered": d.answered, "last_t": round(d.last_t, 1)}


def series(e: Engine) -> dict:
    n = int(e.t // config.BUCKET_S) + 1
    site = []
    per_ch = {}
    per_sensor = {}
    for i in range(n):
        agg = Counter()
        for s, bk in e.buckets.items():
            b = bk.get(i)
            if not b:
                continue
            ch = e.sensors[s].channel
            agg["probe_resp"] += b.probe_resp
            agg["probe_retry"] += b.probe_resp_retry
            agg["joins"] += b.joins
            agg["connected"] += b.connected
            agg["kicks"] += b.kicks
            agg["fast_rejects"] += b.fast_rejects
            agg["leaves"] += b.leaves
            agg["frames"] += b.frames
            per_ch.setdefault(ch, {})[i] = {
                "probe_per_s": round(b.probe_resp / config.BUCKET_S, 1),
                "retry_pct": round(100 * b.probe_resp_retry / b.probe_resp, 1) if b.probe_resp else 0,
                "beacon_air_pct": round(100 * b.beacon_air_us / (config.BUCKET_S * 1e6), 1),
            }
            per_sensor.setdefault(s, {})[i] = {
                "frames_per_s": round(b.frames / config.BUCKET_S, 1),
                "probe_per_s": round(b.probe_resp / config.BUCKET_S, 1),
                "retry_pct": round(100 * b.probe_resp_retry / b.probe_resp, 1) if b.probe_resp else 0,
                "beacon_air_pct": round(100 * b.beacon_air_us / (config.BUCKET_S * 1e6), 1),
                "kicks": b.kicks, "connected": b.connected,
            }
        site.append({"t": i * config.BUCKET_S, **agg,
                     "probe_per_s": round(agg["probe_resp"] / config.BUCKET_S, 1),
                     "retry_pct": round(100 * agg["probe_retry"] / agg["probe_resp"], 1) if agg["probe_resp"] else 0})
    channels = sorted(c for c in per_ch if c is not None)
    chan_series = [{"t": i * config.BUCKET_S, **{f"ch{c}": per_ch[c].get(i, {}).get("probe_per_s", 0) for c in channels}}
                   for i in range(n)]
    air = {c: round(st.mean(v["beacon_air_pct"] for v in per_ch[c].values()), 1) for c in channels}
    retry = {c: round(st.mean(v["retry_pct"] for v in per_ch[c].values() if v["retry_pct"]), 1)
             if any(v["retry_pct"] for v in per_ch[c].values()) else 0 for c in channels}
    sensors = sorted(per_sensor)
    per_sensor_series = {
        metric: [{"t": i * config.BUCKET_S, **{f"S{s}": per_sensor[s].get(i, {}).get(metric, 0) for s in sensors}}
                 for i in range(n)]
        for metric in ("frames_per_s", "probe_per_s", "retry_pct", "beacon_air_pct", "kicks", "connected")
    }
    return {"site": site, "channels": channels, "probe_by_channel": chan_series, "beacon_air_pct": air, "retry_pct": retry,
            "sensors": [f"S{s}" for s in sensors], "per_sensor": per_sensor_series}


def sensors_view(e: Engine) -> list[dict]:
    out = []
    for s, ss in sorted(e.sensors.items()):
        bs = [e.bssids[b] for b in ss.bssids]
        losses = [b.loss() for b in bs if b.count > 50]
        nets = Counter(b.net for b in bs)
        out.append({"sensor": f"S{s}", "channel": ss.channel, "frames": ss.frames,
                    "aps": len({b.ap for b in bs}), "bssids": len(bs), "networks": dict(nets),
                    "beacon_loss_pct": round(100 * st.mean(losses), 2) if losses else None,
                    "alive": ss.last_beacon_t is not None and e.t - ss.last_beacon_t < config.SENSOR_DEAF_S + config.ALLOWED_LATENESS_S,
                    "last_t": round(ss.last_t, 1),
                    "flags": [v["text"] for v in e.flags.values() if s in v["sensors"]]})
    return out


def aps_view(e: Engine) -> dict:
    nets = sorted({n for a in e.aps.values() for n in a["nets"]})
    fails = Counter()
    joins = Counter()
    for d in e.devices.values():
        if d.ap:
            joins[d.ap] += d.attempts
            fails[d.ap] += d.kicks + d.fast_rejects
    rows = []
    for ap, a in sorted(e.aps.items(), key=lambda kv: (min(kv[1]["sensors"]), kv[0])):
        s = min(a["sensors"])
        rows.append({"ap": e.alias_ap(ap), "sensor": f"S{s}", "channel": e.sensors[s].channel,
                     "networks": {n: (n in a["nets"]) for n in nets}, "joins": joins[ap], "failures": fails[ap]})
    return {"networks": [{"label": n, "kind": e.mk.network_kind(n)} for n in nets], "rows": rows}


def snapshot(e: Engine, clock: dict) -> dict:
    devs = [device_row(e, d) for d in e.devices.values() if d.cclass != "unknown"]
    devs.sort(key=lambda r: (STATE_ORDER.get(r["state"], 9), -r["attempts"], r["alias"]))
    tops = e.inc.top_level()
    cur = int(e.t // config.BUCKET_S)
    last = [bk[i] for bk in e.buckets.values() for i in range(cur - 6, cur) if i in bk]
    pr = sum(b.probe_resp for b in last)
    prr = sum(b.probe_resp_retry for b in last)
    failing = sum(1 for r in devs if r["state"] in ("failing", "excluded"))
    kpi = {
        "devices": len(devs), "failing": failing,
        "attempts": sum(r["attempts"] for r in devs), "connected": sum(r["connected"] for r in devs),
        "kicks": sum(r["kicks"] for r in devs), "fast_rejects": sum(r["fast_rejects"] for r in devs),
        "open_incidents": sum(1 for i in tops if i.status == "open"),
        "probe_per_s": round(pr / (6 * config.BUCKET_S), 1) if last else 0,
        "retry_pct": round(100 * prr / pr, 1) if pr else 0,
        "unknown": sum(1 for u in e.unknown if not u.get("reclassified")),
        "time_to_root_s": round(e.inc.first_root_t - e.first_fail_join_t, 1)
        if e.inc.first_root_t is not None and e.first_fail_join_t is not None else None,
    }
    return {
        "clock": {**clock, "t": round(e.t, 1), "frames": e.frames},
        "kpi": kpi,
        "incidents": [incident_dict(e, i) for i in tops],
        "series": series(e),
        "sensors": sensors_view(e),
        "aps": aps_view(e),
        "networks": [{"label": n, "kind": e.mk.network_kind(n), "attempts": c["attempts"], "connected": c["connected"]}
                     for n, c in e.net_stats().items() if n != "?"],
        "devices": devs,
        "unknown": {"count": sum(1 for u in e.unknown if not u.get("reclassified")), "total": len(e.unknown),
                    "recent": e.unknown[-20:][::-1]},
        "observations": e.observations[-20:],
        "feed": list(e.feed)[-60:][::-1],
        "catalog": e.cat.summary(),
        "data_quality": [{"key": k, "t": v["t"], "text": v["text"], "sensors": [f"S{s}" for s in sorted(v["sensors"])]}
                         for k, v in e.flags.items()],
    }


def device_story(e: Engine, dev_id: str) -> dict | None:
    d = e.devices.get(dev_id)
    if not d:
        return None
    return {**device_row(e, d), "story": d.story}
