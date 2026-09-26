"""Shared OpenRouter (DeepSeek) tool-call loop used by both the fix agent and the discovery agent.

Mirrors llm_loop.py's run_json_agent(), but talks to OpenRouter's OpenAI-compatible
Chat Completions API (https://openrouter.ai/docs) over plain httpx instead of the
Anthropic SDK, since the two providers use unrelated request/response shapes
(tool_use content blocks vs. message.tool_calls, output_config vs. response_format, ...).
"""

from __future__ import annotations

import json
import os

import httpx

from .. import config
from ..engine import Engine
from .tools import run_tool, tool_specs


def _openai_tools(names: list[str] | None) -> list[dict]:
    """Convert our Anthropic-shape tool specs (tools.py) into OpenAI/OpenRouter function-tool shape."""
    out = []
    for s in tool_specs(names):
        out.append({"type": "function", "function": {
            "name": s["name"], "description": s["description"], "parameters": s["input_schema"],
        }})
    return out


def _headers() -> dict:
    key = os.environ.get(config.OPENROUTER_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{config.OPENROUTER_API_KEY_ENV} is not set")
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if config.OPENROUTER_SITE_URL:
        h["HTTP-Referer"] = config.OPENROUTER_SITE_URL
    if config.OPENROUTER_SITE_NAME:
        h["X-Title"] = config.OPENROUTER_SITE_NAME
    return h


def _schema_instruction(schema: dict) -> str:
    return ("\n\nRespond with a single JSON object and nothing else (no markdown fences, no prose "
            f"before or after it) matching exactly this JSON Schema:\n{json.dumps(schema)}")


def _extract_json(text: str) -> dict:
    """DeepSeek sometimes wraps JSON in ```json fences despite instructions; strip them before parsing."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        t = t.strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    return json.loads(t)


def run_json_agent(e: Engine, lock, *, system: str, schema: dict, first_content: str,
                    tool_names: list[str] | None = None, model: str | None = None,
                    client: httpx.Client | None = None) -> tuple[dict, dict]:
    """Drive an OpenRouter (DeepSeek) tool-call loop until it returns JSON matching `schema`.

    Returns (parsed_json, meta) where meta has turns/tool_calls/model.
    Raises RuntimeError on an API error, a finish_reason of "length", or turn-limit exhaustion.
    `model` overrides config.OPENROUTER_MODEL (already the "flash"/fast DeepSeek variant by
    default, but kept overridable for consistency with the Claude loop). `client` is injectable
    for tests (an httpx.Client with a mock transport); a real OpenRouter POST is made against
    config.OPENROUTER_BASE_URL otherwise.
    """
    own_client = client is None
    http = client or httpx.Client(timeout=config.OPENROUTER_TIMEOUT_S)
    messages = [
        {"role": "system", "content": system + _schema_instruction(schema)},
        {"role": "user", "content": first_content},
    ]
    tools = _openai_tools(tool_names)
    trace: list[dict] = []
    try:
        for turn in range(config.AGENT_MAX_TURNS):
            body = {"model": model or config.OPENROUTER_MODEL, "messages": messages, "max_tokens": 8000,
                    "reasoning": {"enabled": True}}
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"
            resp = http.post(f"{config.OPENROUTER_BASE_URL}/chat/completions", headers=_headers(), json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"OpenRouter error: {str(data['error'])[:300]}")
            choice = data["choices"][0]
            msg = choice["message"]
            finish = choice.get("finish_reason")
            calls = msg.get("tool_calls") or []
            if finish == "tool_calls" or calls:
                messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
                for tc in calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                    except json.JSONDecodeError as exc:
                        args, parse_err = {}, str(exc)
                    else:
                        parse_err = None
                    if parse_err is None:
                        with lock:
                            out = run_tool(e, name, args)
                    else:
                        out = json.dumps({"error": f"could not parse tool arguments: {parse_err}"})
                    trace.append({"tool": name, "input": args})
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": out})
                continue
            if finish == "length":
                raise RuntimeError("response hit the token limit before finishing")
            content = msg.get("content") or ""
            try:
                parsed = _extract_json(content)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"model did not return valid JSON: {exc}") from exc
            return parsed, {"turns": turn + 1, "tool_calls": trace, "model": data.get("model", config.OPENROUTER_MODEL),
                            "provider": "openrouter"}
        raise RuntimeError("agent did not finish within the turn limit")
    finally:
        if own_client:
            http.close()
