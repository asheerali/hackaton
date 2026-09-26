"""Part 3 orchestration: pick Claude or the offline heuristic, validate, backtest."""

from __future__ import annotations

import time

from ...engine import Engine
from ..fix_agent.service import mode
from . import claude_backend, heuristic
from .backtest import backtest
from .cluster import cluster
from .validate import validate


def draft(e: Engine, cluster_id: str, lock) -> dict:
    with lock:
        cs = {c["cluster_id"]: c for c in cluster(e)}
    if cluster_id not in cs:
        raise KeyError(cluster_id)
    c = cs[cluster_id]
    m = mode()
    note = None
    t0 = time.time()
    if m == "claude":
        try:
            d = claude_backend.draft(e, c, lock)
        except Exception as exc:
            note = f"Claude unavailable ({type(exc).__name__}: {str(exc)[:160]}); offline heuristic used."
            m = "offline"
    if m == "offline":
        with lock:
            d = heuristic.build(e, c)
    with lock:
        errs = validate(e, d)
        bt = backtest(e, d, c)
    return {"draft_id": f"DR-{cluster_id}-{int(time.time()) % 100000}", "cluster": {k: v for k, v in c.items() if k != "example"},
            "entry": d, "validation_errors": errs, "backtest": bt,
            "meta": {"mode": m, "note": note, "seconds": round(time.time() - t0, 1)},
            "status": "ready_for_review" if not errs and bt.get("ok") else "needs_changes"}
