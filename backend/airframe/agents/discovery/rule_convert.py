"""Convert a drafted entry's `rule` block into the detector-rule shape `rules.py` expects."""

from __future__ import annotations


def to_rule(r: dict) -> dict:
    m = {k: v for k, v in r["match"].items() if v}
    return {"match": m, "group_by": r.get("group_by", []), "window_s": r["window_s"],
            "threshold": {"count": {">=": max(1, int(r["min_count"]))}}}
