"""Part 3 orchestration: pick a provider (OpenRouter/DeepSeek, Claude, or the offline heuristic), validate, backtest.

draft() and auto_approve() are the two calls shared by the manual Learning-tab flow (server.py's
POST /api/discovery/.../draft and .../decision) and the automatic trigger (server.py's background
loop) - so "no human click needed" for auto-adoption reuses exactly the same validated, back-tested
path a human reviewer would use, just without waiting for the click.
"""

from __future__ import annotations

import time

from ...engine import Engine
from ..fix_agent.service import mode
from . import claude_backend, heuristic, openrouter_backend
from .adopt import adopt
from .backtest import backtest
from .cluster import cluster
from .validate import validate

_BACKENDS = {"claude": claude_backend, "openrouter": openrouter_backend}


def draft(e: Engine, cluster_id: str, lock, trigger: str = "manual") -> dict:
    with lock:
        cs = {c["cluster_id"]: c for c in cluster(e)}
    if cluster_id not in cs:
        raise KeyError(cluster_id)
    c = cs[cluster_id]
    m = mode()
    note = None
    t0 = time.time()
    backend = _BACKENDS.get(m)
    if backend is not None:
        try:
            d = backend.draft(e, c, lock)
        except Exception as exc:
            note = f"{m} unavailable ({type(exc).__name__}: {str(exc)[:160]}); offline heuristic used."
            m = "offline"
    if m == "offline":
        with lock:
            d = heuristic.build(e, c)
    with lock:
        errs = validate(e, d)
        bt = backtest(e, d, c)
    return {"draft_id": f"DR-{cluster_id}-{int(time.time()) % 100000}", "cluster": {k: v for k, v in c.items() if k != "example"},
            "entry": d, "validation_errors": errs, "backtest": bt, "trigger": trigger,
            "meta": {"mode": m, "note": note, "seconds": round(time.time() - t0, 1)},
            "status": "ready_for_review" if not errs and bt.get("ok") else "needs_changes"}


def auto_approve(e: Engine, dr: dict, lock, reviewer_note: str = "auto-adopted: validation and backtest passed") -> dict:
    """Adopt a ready draft with no human click, then re-run the incident workflow for what it covers."""
    result = adopt(e, dr, reviewer_note, lock)
    with lock:
        n = e.ingest_reclassified(result["reclassified_ids"], result["entry_id"])
    result["incidents_created_or_updated"] = n
    return result
