"""Offline (no Claude credentials) fix proposal, built straight from the catalog entry."""

from __future__ import annotations

from ... import config
from ...engine import Engine
from ...views import incident_dict


def build(e: Engine, incident_id: str) -> dict:
    inc = e.inc.items[incident_id]
    d = incident_dict(e, inc, full=True)
    cat = d["catalog"] or {}
    kids = d.get("children_by_type", {})
    ev = [incident_id] + [f"{x['sensor']}:{x['frame']}" for x in d.get("evidence", []) if x.get("frame")][:4]
    if inc.cid == "INFRA-01":
        stall = e.cat.entry("EAP-01") or {}
        cat = {**cat, "likely_causes": stall.get("likely_causes", []) + cat.get("likely_causes", []),
               "confirm_outside_headers": stall.get("confirm_outside_headers", []) + cat.get("confirm_outside_headers", []),
               "standard_fix": stall.get("standard_fix", []), "owner": stall.get("owner", cat.get("owner"))}
        child_ids = [c for c in inc.children if e.inc.items[c].cid in ("EAP-04", "EAP-01")][:2]
        ev = [incident_id] + child_ids + [f"{x['sensor']}:{x['frame']}" for x in d.get("evidence", []) if x.get("frame")][:4]
    causes = cat.get("likely_causes") or ["see catalog entry"]
    hyps = [{"cause": c, "likelihood": round(max(0.1, 0.55 - 0.15 * i), 2), "supporting_evidence": ev[:2],
             "refuting_evidence": []} for i, c in enumerate(causes[:4])]
    fix = list(cat.get("standard_fix") or [])
    crit = []
    summary = cat.get("plain") or d["title"]
    conf = d["confidence"]
    owner = {"identity/AAA": "identity/AAA", "device": "device", "security": "security", "platform": "platform"}.get(
        cat.get("owner"), "network")
    if inc.cid == "INFRA-01":
        sig = d.get("signature", {})
        ctrl = d.get("control", [])
        healthy = [c for c in ctrl if c["healthy"]]
        for h in hyps:
            h["supporting_evidence"] = ev[:3]
        if healthy:
            hyps.append({"cause": "Radio/coverage problem", "likelihood": 0.05, "supporting_evidence": [],
                         "refuting_evidence": [f"{healthy[0]['network']} on the same {healthy[0]['on_same_aps']} APs: "
                                               f"{healthy[0]['connected']}/{healthy[0]['attempts']} joins OK"]})
        summary = (f"No device can log in to {inc.net}: {d['devices_affected']} devices on {len(d['where']['aps'])} access points "
                   f"get stuck at the identity check and are removed after about {sig.get('kick_s') or 60:.0f} seconds. "
                   f"The other network on the same access points works, so the Wi-Fi radio is fine; the login service behind it is not answering.")
        if kids.get("SESS-02"):
            fix.append(f"After the login service is restored, clear the controller's client-exclusion list for the "
                       f"{kids['SESS-02']} devices that are being fast-rejected (reason 2); otherwise they stay blocked.")
        crit = [{"metric": "reason23_kicks", "op": "==", "value": 0, "window_s": 600},
                {"metric": "login_success_rate", "op": ">=", "value": 0.95, "window_s": 600},
                {"metric": "reason2_rejects", "op": "==", "value": 0, "window_s": 600}]
        if kids.get("DISC-03"):
            crit.append({"metric": "probe_replies_per_s", "op": "<=", "value": 20, "window_s": 300})
        conf = max(conf, 0.8)
    else:
        crit = {
            "RF-01": [{"metric": "retry_pct", "op": "<=", "value": 10, "window_s": 300}],
            "DISC-01": [{"metric": "missing_networks", "op": "==", "value": 0, "window_s": 120}],
            "DISC-03": [{"metric": "probe_replies_per_s", "op": "<=", "value": 20, "window_s": 300}],
            "EAP-04": [{"metric": "reason23_kicks", "op": "==", "value": 0, "window_s": 600}],
            "SESS-02": [{"metric": "reason2_rejects", "op": "==", "value": 0, "window_s": 600}],
        }.get(inc.cid, [{"metric": "failing_devices", "op": "==", "value": 0, "window_s": 600}])
    confirm = (cat.get("confirm_outside_headers") or ["check the controller logs for this incident"])[0]
    return {
        "plain_summary": summary, "root_cause": causes[0], "confidence": round(conf, 2), "hypotheses": hyps,
        "deciding_check": confirm, "fix_steps": fix or ["investigate using the catalog entry"], "owner": owner,
        "risk": "low" if owner == "identity/AAA" else "medium",
        "rollback": "No Wi-Fi configuration change is proposed; revert the service change if logins do not recover."
        if inc.cid == "INFRA-01" else "Revert the configuration change.",
        "success_criteria": crit, "evidence_ids": ev,
        "needs_human": None if conf >= config.AGENT_MIN_CONFIDENCE else "Confirm with controller logs before acting.",
    }
