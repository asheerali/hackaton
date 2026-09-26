"""Claude-backed fix proposal: run the tool loop and parse the JSON proposal."""

from __future__ import annotations

import json

from ... import config
from ...engine import Engine
from ...views import incident_dict
from ..llm_loop import run_json_agent
from .prompts import SYSTEM
from .schema import PROPOSAL_SCHEMA


def propose(e: Engine, incident_id: str, lock, fast: bool = False) -> tuple[dict, dict]:
    with lock:
        first = json.dumps(incident_dict(e, e.inc.items[incident_id], full=True), default=str)[:30000]
    content = f"Incident to fix:\n{first}\n\nInvestigate with the tools, then return the proposal JSON."
    model = config.AGENT_FAST_CLAUDE_MODEL if fast else None
    return run_json_agent(e, lock, system=SYSTEM, schema=PROPOSAL_SCHEMA, first_content=content, model=model)
