"""OpenRouter (DeepSeek)-backed fix proposal: run the tool loop and parse the JSON proposal."""

from __future__ import annotations

import json

from ...engine import Engine
from ...views import incident_dict
from ..llm_loop_openrouter import run_json_agent
from .prompts import SYSTEM
from .schema import PROPOSAL_SCHEMA


def propose(e: Engine, incident_id: str, lock) -> tuple[dict, dict]:
    with lock:
        first = json.dumps(incident_dict(e, e.inc.items[incident_id], full=True), default=str)[:30000]
    content = f"Incident to fix:\n{first}\n\nInvestigate with the tools, then return the proposal JSON."
    return run_json_agent(e, lock, system=SYSTEM, schema=PROPOSAL_SCHEMA, first_content=content)
