"""OpenRouter (DeepSeek)-backed catalog-entry draft: run the tool loop and parse the JSON entry."""

from __future__ import annotations

import json

from ...engine import Engine
from ..llm_loop_openrouter import run_json_agent
from .prompts import SYSTEM
from .schema import ENTRY_SCHEMA

TOOL_NAMES = ["catalog_lookup", "query_frames", "get_device_timeline"]


def draft(e: Engine, c: dict, lock) -> dict:
    content = "Unmatched cluster:\n" + json.dumps(c, default=str)[:20000]
    entry, _meta = run_json_agent(e, lock, system=SYSTEM, schema=ENTRY_SCHEMA, first_content=content, tool_names=TOOL_NAMES)
    return entry
