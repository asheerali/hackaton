"""Part 2 orchestration: pick Claude or the offline playbook, validate, fall back on failure."""

from __future__ import annotations

import os
import time

from ... import config
from ...engine import Engine
from . import claude_backend, playbook
from .validate import validate


def _has_credentials() -> bool:
    return any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"))


def mode() -> str:
    if config.AGENT_MODE in ("claude", "offline"):
        return config.AGENT_MODE
    return "claude" if _has_credentials() else "offline"


def propose(e: Engine, incident_id: str, lock) -> dict:
    with lock:
        if incident_id not in e.inc.items:
            raise KeyError(incident_id)
        cid = e.inc.items[incident_id].cid
    t0 = time.time()
    m = mode()
    meta: dict = {"mode": m}
    note = None
    if m == "claude":
        try:
            proposal, extra = claude_backend.propose(e, incident_id, lock)
            meta.update(extra)
        except Exception as exc:  # fall back, but say so
            note = f"Claude unavailable ({type(exc).__name__}: {str(exc)[:160]}); offline playbook used."
            meta["mode"] = "offline"
            with lock:
                proposal = playbook.build(e, incident_id)
    else:
        with lock:
            proposal = playbook.build(e, incident_id)
    with lock:
        errs = validate(e, proposal)
    if errs and meta["mode"] == "claude":
        with lock:
            proposal = playbook.build(e, incident_id)
            errs2 = validate(e, proposal)
        note = f"Claude proposal failed validation ({'; '.join(errs)}); offline playbook used."
        meta["mode"], errs = "offline", errs2
    meta.update({"seconds": round(time.time() - t0, 1), "validation_errors": errs, "note": note,
                 "model": meta.get("model", config.AGENT_MODEL if meta["mode"] == "claude" else None)})
    return {"incident_id": incident_id, "catalog_id": cid, "proposal": proposal, "meta": meta,
            "status": "proposed", "created_t": round(e.t, 1)}
