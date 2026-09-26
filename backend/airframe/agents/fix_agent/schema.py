"""JSON schema + metric names for Part 2 fix proposals."""

from __future__ import annotations

METRICS = ["reason23_kicks", "reason2_rejects", "login_success_rate", "failing_devices", "probe_replies_per_s",
           "retry_pct", "missing_networks", "unknown_events"]

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "plain_summary": {"type": "string"},
        "root_cause": {"type": "string"},
        "confidence": {"type": "number"},
        "hypotheses": {"type": "array", "items": {"type": "object", "properties": {
            "cause": {"type": "string"}, "likelihood": {"type": "number"},
            "supporting_evidence": {"type": "array", "items": {"type": "string"}},
            "refuting_evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["cause", "likelihood", "supporting_evidence", "refuting_evidence"], "additionalProperties": False}},
        "deciding_check": {"type": "string"},
        "fix_steps": {"type": "array", "items": {"type": "string"}},
        "owner": {"type": "string", "enum": ["identity/AAA", "network", "device", "platform", "security"]},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "rollback": {"type": "string"},
        "success_criteria": {"type": "array", "items": {"type": "object", "properties": {
            "metric": {"type": "string", "enum": METRICS}, "op": {"type": "string", "enum": ["==", "<=", "<", ">=", ">"]},
            "value": {"type": "number"}, "window_s": {"type": "number"}},
            "required": ["metric", "op", "value", "window_s"], "additionalProperties": False}},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "needs_human": {"type": ["string", "null"]},
    },
    "required": ["plain_summary", "root_cause", "confidence", "hypotheses", "deciding_check", "fix_steps", "owner", "risk",
                 "rollback", "success_criteria", "evidence_ids", "needs_human"],
    "additionalProperties": False,
}
