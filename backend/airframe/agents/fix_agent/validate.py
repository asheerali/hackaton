"""Guardrail checks applied to every fix proposal, Claude-written or offline."""

from __future__ import annotations

import re

from ... import config
from ...engine import Engine
from ..tools import MAC_RE
from .schema import METRICS


def validate(e: Engine, p: dict) -> list[str]:
    import json

    errs = []
    blob = json.dumps(p)
    if MAC_RE.search(blob):
        errs.append("contains a raw MAC address")
    for kind, code in re.findall(r"\b(reason|status)(?: code)?\s+(\d+)", blob, re.I):
        if e.cat.code_text(kind.lower(), int(code)) == "not defined in IEEE 802.11 tables":
            errs.append(f"{kind} {code} is not a defined IEEE 802.11 code")
    if not 0 <= p.get("confidence", -1) <= 1:
        errs.append("confidence must be between 0 and 1")
    if not p.get("evidence_ids"):
        errs.append("no evidence cited")
    for c in p.get("success_criteria", []):
        if c.get("metric") not in METRICS:
            errs.append(f"unknown metric {c.get('metric')}")
    if p.get("confidence", 0) < config.AGENT_MIN_CONFIDENCE and not p.get("needs_human"):
        errs.append("confidence below threshold but needs_human is empty")
    return errs
