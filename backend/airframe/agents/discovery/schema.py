"""JSON schema for a Part 3 draft catalog entry."""

from __future__ import annotations

ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "extends": {"type": ["string", "null"]},
        "category": {"type": "string", "enum": ["DISC", "AUTH", "ASSOC", "EAP", "KEY", "SESS", "ROAM", "RF", "CLIENT", "SEC",
                                                  "INFRA", "SENS"]},
        "name": {"type": "string"}, "plain": {"type": "string"}, "signature": {"type": "string"},
        "normal_lookalike": {"type": "string"},
        "default_severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
        "likely_causes": {"type": "array", "items": {"type": "string"}},
        "confirm_outside_headers": {"type": "array", "items": {"type": "string"}},
        "standard_fix": {"type": "array", "items": {"type": "string"}},
        "owner": {"type": "string", "enum": ["identity/AAA", "network", "device", "platform", "security"]},
        "reason_codes": {"type": "array", "items": {"type": "integer"}},
        "status_codes": {"type": "array", "items": {"type": "integer"}},
        "vendor_specific_codes": {"type": "boolean"},
        "rule": {"type": "object", "properties": {
            "match": {"type": "object", "properties": {
                "kind": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "array", "items": {"type": "integer"}},
                "status": {"type": "array", "items": {"type": "integer"}},
                "sender": {"type": "array", "items": {"type": "string", "enum": ["ap", "client"]}}},
                "required": ["kind", "reason", "status", "sender"], "additionalProperties": False},
            "group_by": {"type": "array", "items": {"type": "string", "enum": ["device", "ap", "sensor", "network"]}},
            "window_s": {"type": "number"},
            "min_count": {"type": "integer"}},
            "required": ["match", "group_by", "window_s", "min_count"], "additionalProperties": False},
        "reasoning": {"type": "string"},
    },
    "required": ["extends", "category", "name", "plain", "signature", "normal_lookalike", "default_severity", "likely_causes",
                 "confirm_outside_headers", "standard_fix", "owner", "reason_codes", "status_codes", "vendor_specific_codes",
                 "rule", "reasoning"],
    "additionalProperties": False,
}
