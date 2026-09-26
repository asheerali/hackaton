"""Replay a drafted rule over the frame log to check it fires on the cluster and nowhere else."""

from __future__ import annotations

from ... import rules
from ...engine import Engine
from .rule_convert import to_rule


def backtest(e: Engine, d: dict, c: dict) -> dict:
    rule = to_rule(d["rule"])
    if rules.validate(rule):
        return {"ok": False, "reason": "invalid rule"}
    hits = rules.evaluate(rule, e.frame_log)
    matched = [f for f in e.frame_log if rules._matches(f, rule["match"])]
    in_cluster = sum(1 for f in matched if f.kind == c["frame_kind"] and (f.reason == c["code"] or f.status == c["code"]))
    outside = len(matched) - in_cluster
    return {"ok": in_cluster > 0 and outside <= max(1, 0.01 * len(e.frame_log)), "rule": rule, "groups_firing": len(hits),
            "frames_matched_in_cluster": in_cluster, "frames_matched_outside_cluster": outside,
            "frames_scanned": len(e.frame_log), "cluster_events": c["count"]}
