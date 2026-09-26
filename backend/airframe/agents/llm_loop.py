"""Shared Claude tool-call loop used by both the fix agent and the discovery agent."""

from __future__ import annotations

import json

from .. import config
from ..engine import Engine
from .tools import run_tool, tool_specs


def run_json_agent(e: Engine, lock, *, system: str, schema: dict, first_content: str,
                    tool_names: list[str] | None = None) -> tuple[dict, dict]:
    """Drive a Claude tool-use loop until it returns JSON matching `schema`.

    Returns (parsed_json, meta) where meta has turns/tool_calls/model.
    Raises RuntimeError on refusal, max_tokens, or turn-limit exhaustion.
    """
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": first_content}]
    trace = []
    for turn in range(config.AGENT_MAX_TURNS):
        resp = client.beta.messages.create(
            model=config.AGENT_MODEL, max_tokens=16000, system=system, messages=messages,
            tools=tool_specs(tool_names), thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "tool_use" and uses:
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for u in uses:
                with lock:
                    out = run_tool(e, u.name, u.input)
                trace.append({"tool": u.name, "input": u.input})
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": out})
            messages.append({"role": "user", "content": results})
            continue
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("response hit max_tokens")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text), {"turns": turn + 1, "tool_calls": trace, "model": resp.model}
    raise RuntimeError("agent did not finish within the turn limit")
