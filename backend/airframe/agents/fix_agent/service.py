"""Part 2 orchestration: pick a provider (OpenRouter/DeepSeek, Claude, or the offline playbook), validate, fall back on failure."""

from __future__ import annotations

import os
import time

from ... import config
from ...engine import Engine
from . import claude_backend, openrouter_backend, playbook
from .validate import validate


def _has_claude() -> bool:
    return any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"))


def _has_openrouter() -> bool:
    return bool(os.environ.get(config.OPENROUTER_API_KEY_ENV))


def mode() -> str:
    """auto picks the best available provider: openrouter (DeepSeek) > claude > offline."""
    if config.AGENT_MODE in ("claude", "openrouter", "offline"):
        return config.AGENT_MODE
    if _has_openrouter():
        return "openrouter"
    if _has_claude():
        return "claude"
    return "offline"


def current_model() -> str | None:
    m = mode()
    return {"claude": config.AGENT_MODEL, "openrouter": config.OPENROUTER_MODEL}.get(m)


_BACKENDS = {"claude": claude_backend, "openrouter": openrouter_backend}


def propose(e: Engine, incident_id: str, lock) -> dict:
    with lock:
        if incident_id not in e.inc.items:
            raise KeyError(incident_id)
        cid = e.inc.items[incident_id].cid
    t0 = time.time()
    m = mode()
    meta: dict = {"mode": m}
    note = None
    backend = _BACKENDS.get(m)
    if backend is not None:
        try:
            proposal, extra = backend.propose(e, incident_id, lock)
            meta.update(extra)
        except Exception as exc:  # fall back, but say so
            note = f"{m} unavailable ({type(exc).__name__}: {str(exc)[:160]}); offline playbook used."
            meta["mode"] = "offline"
            with lock:
                proposal = playbook.build(e, incident_id)
    else:
        with lock:
            proposal = playbook.build(e, incident_id)
    with lock:
        errs = validate(e, proposal)
    if errs and meta["mode"] in _BACKENDS:
        with lock:
            proposal = playbook.build(e, incident_id)
            errs2 = validate(e, proposal)
        note = f"{meta['mode']} proposal failed validation ({'; '.join(errs)}); offline playbook used."
        meta["mode"], errs = "offline", errs2
    meta.update({"seconds": round(time.time() - t0, 1), "validation_errors": errs, "note": note,
                 "model": meta.get("model") or ({"claude": config.AGENT_MODEL, "openrouter": config.OPENROUTER_MODEL}.get(meta["mode"]))})
    return {"incident_id": incident_id, "catalog_id": cid, "proposal": proposal, "meta": meta,
            "status": "proposed", "created_t": round(e.t, 1)}
