"""Guardrail checks applied to every drafted catalog entry, Claude-written or offline."""

from __future__ import annotations

import json

from ... import rules
from ...engine import Engine
from ..tools import MAC_RE
from .rule_convert import to_rule


def validate(e: Engine, d: dict) -> list[str]:
    errs = []
    if MAC_RE.search(json.dumps(d)):
        errs.append("contains a raw MAC address")
    for kind, codes in (("reason", d.get("reason_codes", [])), ("status", d.get("status_codes", []))):
        for code in codes:
            undefined = e.cat.code_text(kind, code) == "not defined in IEEE 802.11 tables"
            if undefined and not d.get("vendor_specific_codes"):
                errs.append(f"{kind} {code} is not an IEEE code; mark vendor_specific_codes")
            mapped = e.cat.for_code(kind, code)
            if mapped not in ("OTHER-CODE", "OK") and not d.get("extends"):
                errs.append(f"{kind} {code} is already mapped to {mapped}")
    if d.get("extends") and not e.cat.entry(d["extends"]):
        errs.append(f"extends unknown entry {d['extends']}")
    errs += rules.validate(to_rule(d["rule"]))
    return errs
