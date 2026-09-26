"""Group unmatched OTHER events into clusters worth drafting a catalog entry for."""

from __future__ import annotations

from collections import defaultdict

from ...engine import Engine


def cluster(e: Engine) -> list[dict]:
    groups = defaultdict(list)
    for u in e.unknown:
        if u.get("reclassified"):
            continue
        det = u["detail"]
        sig = (u["kind"], det.get("field") or det.get("transition") or det.get("metric"), det.get("code"), u.get("sender"),
               u.get("frame_kind"))
        groups[sig].append(u)
    out = []
    for i, (sig, items) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        kind, what, code, sender, fkind = sig
        out.append({"cluster_id": f"CL-{i:03d}", "kind": kind, "what": what, "code": code, "sender": sender,
                    "frame_kind": fkind, "count": len(items), "first_t": items[0]["t"], "last_t": items[-1]["t"],
                    "sensors": sorted({x["sensor"] for x in items}), "devices": len({x.get("device") for x in items}),
                    "synthetic": all(x.get("synthetic") for x in items),
                    "ieee_text": items[0]["detail"].get("ieee_text"), "event_ids": [x["id"] for x in items][:50],
                    "example": items[0]})
    return out
