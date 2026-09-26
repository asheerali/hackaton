"""Turn an approved draft into a permanent catalog entry, and reclassify the events it covers."""

from __future__ import annotations

import json

from ...engine import Engine
from .rule_convert import to_rule


def adopt(e: Engine, dr: dict, reviewer_note: str, lock) -> dict:
    d = dr["entry"]
    with lock:
        existing = [x for x in e.cat.entries if x.startswith(d["category"] + "-X")]
        new_id = d["extends"] or f"{d['category']}-X{len(existing) + 1:02d}"
        base = e.cat.entry(d["extends"]) if d["extends"] else {}
        entry = {**(base or {}), "id": new_id, "category": d["category"], "name": d["name"] if not d["extends"] else base["name"],
                 "plain": d["plain"], "signature": d["signature"], "detect": json.dumps(to_rule(d["rule"])),
                 "rule": to_rule(d["rule"]), "normal_lookalike": d["normal_lookalike"],
                 "default_severity": d["default_severity"], "likely_causes": d["likely_causes"],
                 "confirm_outside_headers": d["confirm_outside_headers"], "standard_fix": d["standard_fix"],
                 "owner": d["owner"], "codes": {"reason": sorted(set((base or {}).get("codes", {}).get("reason", []) + d["reason_codes"])),
                                                 "status": sorted(set((base or {}).get("codes", {}).get("status", []) + d["status_codes"]))},
                 "header_visibility": "full", "vendor_specific_codes": d["vendor_specific_codes"],
                 "dataset": {"seen": True, "evidence": f"adopted from {dr['cluster']['cluster_id']} ({dr['cluster']['count']} events)"},
                 "source": "discovery-agent", "draft_id": dr["draft_id"]}
        version = e.cat.add_extension(entry, f"{dr['draft_id']} approved: {reviewer_note or 'no note'}")
        reclassified_ids = []
        for u in e.unknown:
            det = u["detail"]
            if not u.get("reclassified") and det.get("code") is not None and e.cat.for_code(det.get("field", ""), det["code"]) == new_id:
                u["reclassified"] = new_id
                reclassified_ids.append(u["id"])
    return {"entry_id": new_id, "catalog_version": version, "reclassified_events": len(reclassified_ids),
            "reclassified_ids": reclassified_ids}
