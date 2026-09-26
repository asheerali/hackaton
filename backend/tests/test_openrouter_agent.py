"""Unit tests for the OpenRouter (DeepSeek) tool-call loop. Fully offline: httpx.MockTransport
stands in for the real OpenRouter API, so these run without OPENROUTER_API_KEY or network access.
"""

from __future__ import annotations

import json
import threading

import httpx
import pytest

from airframe import config
from airframe.agents import llm_loop_openrouter as loop
from airframe.agents.discovery import openrouter_backend as disc_backend
from airframe.agents.fix_agent import openrouter_backend as fix_backend

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
LOCK = threading.Lock()


def _msg(content=None, tool_calls=None, finish="stop", model="deepseek/deepseek-v4.1-flash"):
    m = {"content": content, "role": "assistant"}
    if tool_calls:
        m["tool_calls"] = tool_calls
    return {"choices": [{"message": m, "finish_reason": finish}], "model": model}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_headers_include_auth_and_optional_site_info(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(config, "OPENROUTER_SITE_URL", "https://example.com")
    monkeypatch.setattr(config, "OPENROUTER_SITE_NAME", "Airframe Test")
    h = loop._headers()
    assert h["Authorization"] == "Bearer sk-or-v1-test"
    assert h["HTTP-Referer"] == "https://example.com"
    assert h["X-Title"] == "Airframe Test"


def test_headers_raise_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        loop._headers()


def test_openai_tool_conversion_shape():
    tools = loop._openai_tools(["catalog_lookup"])
    assert len(tools) == 1
    t = tools[0]
    assert t["type"] == "function"
    assert t["function"]["name"] == "catalog_lookup"
    assert "description" in t["function"] and "parameters" in t["function"]
    assert t["function"]["parameters"]["required"] == ["ref"]


def test_extract_json_handles_markdown_fences():
    assert loop._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert loop._extract_json("```\n{\"a\": 2}\n```") == {"a": 2}
    assert loop._extract_json('{"a": 3}') == {"a": 3}


def test_run_json_agent_returns_parsed_json_no_tools(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer sk-or-v1-test"
        return httpx.Response(200, json=_msg(content='{"answer": "42"}'))

    parsed, meta = loop.run_json_agent(
        None, LOCK, system="be terse", schema=SCHEMA, first_content="what is the answer?",
        client=_client(handler),
    )
    assert parsed == {"answer": "42"}
    assert meta == {"turns": 1, "tool_calls": [], "model": "deepseek/deepseek-v4.1-flash", "provider": "openrouter"}
    assert len(calls) == 1
    body = calls[0]
    assert body["model"] == config.OPENROUTER_MODEL
    assert body["messages"][0]["role"] == "system" and "be terse" in body["messages"][0]["content"]
    assert json.dumps(SCHEMA) in body["messages"][0]["content"]
    assert body["messages"][1] == {"role": "user", "content": "what is the answer?"}
    # tool_names=None means "all tools available", same convention as tools.tool_specs(None) - not "no tools".
    assert body["tool_choice"] == "auto"
    assert len(body["tools"]) == len(loop._openai_tools(None)) > 0


def test_run_json_agent_runs_a_tool_then_returns_json(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(loop, "run_tool", lambda e, name, args: json.dumps({"ok": True, "name": name, "args": args}))
    turns = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        turns.append(body)
        if len(turns) == 1:
            assert body["tools"][0]["function"]["name"] == "catalog_lookup"
            return httpx.Response(200, json=_msg(tool_calls=[
                {"id": "call_1", "type": "function", "function": {"name": "catalog_lookup", "arguments": '{"ref": "EAP-01"}'}}
            ], finish="tool_calls"))
        # second turn: the tool result must have been appended as a "tool" message
        assert turns[1]["messages"][-1] == {"role": "tool", "tool_call_id": "call_1",
                                            "content": json.dumps({"ok": True, "name": "catalog_lookup", "args": {"ref": "EAP-01"}})}
        return httpx.Response(200, json=_msg(content='{"answer": "done"}'))

    parsed, meta = loop.run_json_agent(
        "fake-engine", LOCK, system="sys", schema=SCHEMA, first_content="go", tool_names=["catalog_lookup"],
        client=_client(handler),
    )
    assert parsed == {"answer": "done"}
    assert meta["turns"] == 2
    assert meta["tool_calls"] == [{"tool": "catalog_lookup", "input": {"ref": "EAP-01"}}]
    assert len(turns) == 2


def test_run_json_agent_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    with pytest.raises(RuntimeError, match="OpenRouter HTTP 401"):
        loop.run_json_agent(None, LOCK, system="s", schema=SCHEMA, first_content="x", client=_client(handler))


def test_run_json_agent_raises_on_length_finish(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_msg(content="truncat", finish="length"))

    with pytest.raises(RuntimeError, match="token limit"):
        loop.run_json_agent(None, LOCK, system="s", schema=SCHEMA, first_content="x", client=_client(handler))


def test_run_json_agent_raises_on_invalid_json(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_msg(content="not json at all"))

    with pytest.raises(RuntimeError, match="did not return valid JSON"):
        loop.run_json_agent(None, LOCK, system="s", schema=SCHEMA, first_content="x", client=_client(handler))


def test_run_json_agent_gives_up_after_max_turns(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setattr(config, "AGENT_MAX_TURNS", 2)
    monkeypatch.setattr(loop, "run_tool", lambda e, name, args: "{}")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_msg(tool_calls=[
            {"id": "call_1", "type": "function", "function": {"name": "catalog_lookup", "arguments": "{}"}}
        ], finish="tool_calls"))

    with pytest.raises(RuntimeError, match="turn limit"):
        loop.run_json_agent(None, LOCK, system="s", schema=SCHEMA, first_content="x", tool_names=["catalog_lookup"],
                            client=_client(handler))


# ---------------------------------------------------------------- backend wiring (mocked at the loop level)

def test_fix_agent_openrouter_backend_builds_incident_content(monkeypatch):
    from airframe.agents.fix_agent.schema import PROPOSAL_SCHEMA
    from airframe.agents.fix_agent.prompts import SYSTEM
    captured = {}

    def fake_run_json_agent(e, lock, *, system, schema, first_content, tool_names=None, client=None):
        captured.update(system=system, schema=schema, first_content=first_content)
        return {"stub": True}, {"turns": 1, "tool_calls": [], "model": config.OPENROUTER_MODEL, "provider": "openrouter"}

    monkeypatch.setattr(fix_backend, "run_json_agent", fake_run_json_agent)

    class FakeIncidents:
        items = {"INC-0001": object()}

    class FakeEngine:
        inc = FakeIncidents()

    monkeypatch.setattr("airframe.agents.fix_agent.openrouter_backend.incident_dict",
                        lambda e, inc, full=True: {"id": "INC-0001", "title": "test"})

    proposal, meta = fix_backend.propose(FakeEngine(), "INC-0001", LOCK)
    assert proposal == {"stub": True}
    assert meta["provider"] == "openrouter"
    assert captured["schema"] is PROPOSAL_SCHEMA
    assert captured["system"] is SYSTEM
    assert "INC-0001" in captured["first_content"]
    assert "Investigate with the tools" in captured["first_content"]


def test_discovery_openrouter_backend_builds_cluster_content(monkeypatch):
    from airframe.agents.discovery.schema import ENTRY_SCHEMA
    from airframe.agents.discovery.prompts import SYSTEM
    captured = {}

    def fake_run_json_agent(e, lock, *, system, schema, first_content, tool_names=None, client=None):
        captured.update(system=system, schema=schema, first_content=first_content, tool_names=tool_names)
        return {"entry": "stub"}, {}

    monkeypatch.setattr(disc_backend, "run_json_agent", fake_run_json_agent)
    cluster = {"cluster_id": "CL-001", "code": 250, "sender": "ap"}
    entry = disc_backend.draft("fake-engine", cluster, LOCK)
    assert entry == {"entry": "stub"}
    assert captured["schema"] is ENTRY_SCHEMA
    assert captured["system"] is SYSTEM
    assert captured["tool_names"] == disc_backend.TOOL_NAMES
    assert "CL-001" in captured["first_content"]
