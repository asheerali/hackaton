"""FastAPI app: live snapshots over SSE, replay control, incident/device detail, Part 2 and Part 3 workflows."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .agents import discovery, fix_agent
from .catalog import Catalog
from .runner import Replay
from .views import device_story, incident_dict

CATALOG = Catalog()
REPLAY = Replay(CATALOG)
PROPOSALS: dict[str, dict] = {}
DRAFTS: dict[str, dict] = {}
JOBS: dict[str, dict] = {}

# Background auto-triggers (Part 2 critical auto-analysis, Part 3 auto-discovery). State is
# reset whenever a new engine appears (a fresh /api/replay start), tracked by id(engine).
_AUTO_STOP = threading.Event()
_auto_state = {"engine_id": None, "fix_seen": set(), "discovery_done_sigs": set(), "discovery_inflight": set()}
APPROVALS: dict[str, dict] = {}


def _engine():
    if not REPLAY.engine:
        raise HTTPException(409, "no replay running; start one first")
    return REPLAY.engine


def _job(key: str, fn) -> dict:
    """Run a slow agent call in a thread; the UI polls the job."""
    if JOBS.get(key, {}).get("state") == "running":
        return JOBS[key]
    JOBS[key] = {"state": "running", "started": time.time()}

    def work():
        try:
            JOBS[key] = {"state": "done", "result": fn()}
        except Exception as exc:
            JOBS[key] = {"state": "error", "error": f"{type(exc).__name__}: {exc}"}

    threading.Thread(target=work, daemon=True).start()
    return JOBS[key]


@asynccontextmanager
async def lifespan(_app):
    if config.AUTOSTART:
        REPLAY.start(speed=10)
    yield
    REPLAY.stop()


app = FastAPI(title="Airframe", version="1.0", lifespan=lifespan)


# ---------------------------------------------------------------- live data
@app.get("/api/health")
def health():
    return {"ok": True, "replay": REPLAY.state, "agent_mode": fix_agent.mode(), "model": fix_agent.current_model(),
            "catalog": CATALOG.summary()}


@app.get("/api/snapshot")
def get_snapshot():
    return _decorate(REPLAY.snap or {})


def _build_alerts(eng) -> list[dict]:
    if not eng:
        return []
    alerts = []
    for inc in eng.inc.top_level():
        if inc.status != "open":
            continue
        severity = inc.severity if inc.severity in {"critical", "high", "medium", "low", "info", "unknown"} else "unknown"
        if severity not in {"critical", "high", "medium"}:
            continue
        alerts.append({
            "incident_id": inc.id,
            "catalog_id": inc.cid,
            "title": inc.title or inc.cid,
            "severity": severity,
            "created_t": round(inc.first_t, 1),
            "sensors": [f"S{s}" for s in sorted(inc.sensors)],
            "priority": APPROVALS.get(inc.id, {}).get("priority", "P2"),
            "source": "catalog" if inc.cid != "OTHER" else "discovery",
        })
    return sorted(alerts, key=lambda x: (0 if x["severity"] == "critical" else 1, x["created_t"]))


def _auto_work(eng) -> None:
    """Background auto-triggers, called on every snapshot decoration (see _decorate below).

    Part 2: a critical/high incident gets a fast fix proposal generated with no click needed.
    Part 3: an unmatched-event cluster past the size threshold is drafted and, if it passes
    validation + backtest, adopted into the catalog automatically - no human click - and every
    event it covers is re-run through detection so it becomes a real incident (see
    Engine.ingest_reclassified). A cluster that fails validation/backtest is drafted once and
    left for a human to review in the Learning tab, not retried every poll.
    """
    if not eng:
        return
    if _auto_state["engine_id"] != id(eng):
        _auto_state.update(engine_id=id(eng), fix_seen=set(), discovery_done_sigs=set(), discovery_inflight=set())

    if config.AGENT_AUTO_ANALYZE:
        for inc in eng.inc.top_level():
            if inc.status != "open" or inc.severity not in config.AGENT_AUTO_SEVERITIES:
                continue
            if inc.id in PROPOSALS or inc.id in _auto_state["fix_seen"]:
                continue
            _auto_state["fix_seen"].add(inc.id)

            def _run_fix(incident_id: str = inc.id) -> None:
                try:
                    rec = fix_agent.propose(eng, incident_id, REPLAY.lock, fast=True, trigger="auto")
                    PROPOSALS[incident_id] = rec
                    REPLAY._publish()
                except Exception:
                    _auto_state["fix_seen"].discard(incident_id)  # let it retry on a later poll
            threading.Thread(target=_run_fix, daemon=True).start()

    if config.DISCOVERY_AUTO:
        for c in discovery.cluster(eng):
            if c.get("count", 0) < config.DISCOVERY_AUTO_MIN_COUNT:
                continue
            sig = (c["kind"], c["what"], c["code"], c["sender"], c["frame_kind"])
            if sig in _auto_state["discovery_done_sigs"] or sig in _auto_state["discovery_inflight"]:
                continue
            _auto_state["discovery_inflight"].add(sig)
            cluster_id = c["cluster_id"]

            def _run_draft(cluster_key: str = cluster_id, signature: tuple = sig) -> None:
                try:
                    dr = discovery.draft(eng, cluster_key, REPLAY.lock, trigger="auto")
                    if dr["status"] == "ready_for_review":
                        dr["adopted"] = discovery.auto_approve(eng, dr, REPLAY.lock)
                        dr["status"] = "adopted"
                    _auto_state["discovery_done_sigs"].add(signature)  # one attempt per signature either way
                    DRAFTS[dr["draft_id"]] = dr
                    REPLAY._publish()
                except Exception:
                    pass  # left out of discovery_done_sigs: retried on a later poll
                finally:
                    _auto_state["discovery_inflight"].discard(signature)
            threading.Thread(target=_run_draft, daemon=True).start()


def _sensor_ints(labels: list[str] | None) -> list[int] | None:
    """['S1', 'S3'] -> [1, 3], for scoping a live success check to the approval's selected sensors."""
    if not labels:
        return None
    out = []
    for s in labels:
        try:
            out.append(int(s[1:]) if s.upper().startswith("S") else int(s))
        except ValueError:
            continue
    return out or None


def _decorate(snap: dict) -> dict:
    if not snap:
        return snap
    eng = REPLAY.engine
    snap = dict(snap)
    with REPLAY.lock:
        proposals = {}
        for k, v in PROPOSALS.items():
            rec = {**v, "sensors": _sensor_ints(APPROVALS.get(k, {}).get("selected_sensors"))}
            proposals[k] = {**rec, "success": fix_agent.check_success(eng, rec) if v["status"] == "approved" and eng else None}
        snap["proposals"] = proposals
        snap["agent"] = {"mode": fix_agent.mode(), "model": fix_agent.current_model()}
        snap["clusters"] = [{k: v for k, v in c.items() if k != "example"} for c in discovery.cluster(eng)] if eng else []
        snap["drafts"] = list(DRAFTS.values())
        snap["catalog"] = CATALOG.summary()
        snap["alerts"] = _build_alerts(eng)
        snap["approvals"] = {k: {**v} for k, v in APPROVALS.items()}
        if eng:
            _auto_work(eng)
    return snap


@app.get("/api/stream")
async def stream():
    async def gen():
        last = -1
        while True:
            if REPLAY.version != last and REPLAY.snap:
                last = REPLAY.version
                yield f"event: snapshot\ndata: {json.dumps(_decorate(REPLAY.snap), default=str)}\n\n"
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class ReplayCmd(BaseModel):
    action: str
    speed: float | None = None
    source: str | None = None


@app.post("/api/replay")
def replay(cmd: ReplayCmd):
    if cmd.action == "start":
        PROPOSALS.clear()
        DRAFTS.clear()
        REPLAY.start(speed=cmd.speed, source=cmd.source)
    elif cmd.action == "pause":
        REPLAY.pause()
    elif cmd.action == "resume":
        REPLAY.resume()
    elif cmd.action == "speed" and cmd.speed is not None:
        REPLAY.set_speed(cmd.speed)
    else:
        raise HTTPException(400, "action must be start | pause | resume | speed")
    return {"state": REPLAY.state, "speed": REPLAY.speed}


@app.get("/api/incidents/{iid}")
def incident(iid: str):
    eng = _engine()
    with REPLAY.lock:
        if iid not in eng.inc.items:
            raise HTTPException(404, "no such incident")
        return incident_dict(eng, eng.inc.items[iid], full=True)


@app.get("/api/devices/{did}")
def device(did: str):
    eng = _engine()
    with REPLAY.lock:
        s = device_story(eng, did)
    if not s:
        raise HTTPException(404, "no such device")
    return s


@app.get("/api/catalog")
def catalog():
    return {"summary": CATALOG.summary(), "categories": CATALOG.categories, "changelog": CATALOG.changelog,
            "entries": list(CATALOG.entries.values())}


# ---------------------------------------------------------------- Part 2
@app.post("/api/incidents/{iid}/fix")
def fix(iid: str):
    eng = _engine()
    if iid not in eng.inc.items:
        raise HTTPException(404, "no such incident")

    def run():
        rec = fix_agent.propose(eng, iid, REPLAY.lock)
        PROPOSALS[iid] = rec
        REPLAY._publish()
        return rec
    return _job(f"fix:{iid}", run)


@app.get("/api/jobs/{key}")
def job(key: str):
    return JOBS.get(key, {"state": "none"})


class Decision(BaseModel):
    decision: str
    note: str | None = None


class IncidentApproval(BaseModel):
    approve: bool = True
    priority: str = "P2"
    selected_sensors: list[str] | None = None
    note: str | None = None


@app.post("/api/incidents/{iid}/approval")
def incident_approval(iid: str, body: IncidentApproval):
    eng = _engine()
    with REPLAY.lock:
        if iid not in eng.inc.items:
            raise HTTPException(404, "no such incident")
        inc = eng.inc.items[iid]
        sensors = body.selected_sensors or [f"S{s}" for s in sorted(inc.sensors)]
        APPROVALS[iid] = {
            "approved": bool(body.approve),
            "priority": body.priority,
            "selected_sensors": sensors,
            "note": body.note,
            "updated_t": round(eng.t, 1),
        }
        if body.approve:
            inc.status = "open"
        else:
            inc.status = "resolved"
        REPLAY._publish()
    return APPROVALS[iid]


@app.post("/api/incidents/{iid}/fix/decision")
def fix_decision(iid: str, d: Decision):
    rec = PROPOSALS.get(iid)
    if not rec:
        raise HTTPException(404, "no proposal for this incident")
    if d.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve | reject")
    rec["status"] = "approved" if d.decision == "approve" else "rejected"
    rec["decision_note"] = d.note
    rec["decided_t"] = round(REPLAY.engine.t, 1) if REPLAY.engine else None
    config.OUT_DIR.mkdir(exist_ok=True)
    with (config.OUT_DIR / "fix_history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"catalog_id": rec["catalog_id"], "incident_id": iid, "decision": rec["status"], "note": d.note,
                             "root_cause": rec["proposal"]["root_cause"], "fix_steps": rec["proposal"]["fix_steps"]}) + "\n")
    REPLAY._publish()
    return rec


# ---------------------------------------------------------------- Part 3
@app.post("/api/discovery/{cluster_id}/draft")
def draft(cluster_id: str):
    eng = _engine()

    def run():
        dr = discovery.draft(eng, cluster_id, REPLAY.lock, trigger="manual")
        DRAFTS[dr["draft_id"]] = dr
        REPLAY._publish()
        return dr
    return _job(f"draft:{cluster_id}", run)


@app.post("/api/discovery/drafts/{draft_id}/decision")
def draft_decision(draft_id: str, d: Decision):
    dr = DRAFTS.get(draft_id)
    if not dr:
        raise HTTPException(404, "no such draft")
    if d.decision == "approve":
        if dr["validation_errors"] or not dr["backtest"].get("ok"):
            raise HTTPException(409, "draft failed validation or backtest; it cannot be adopted")
        eng = _engine()
        dr["adopted"] = discovery.auto_approve(eng, dr, REPLAY.lock, d.note or "reviewer approved")
        dr["status"] = "adopted"
    elif d.decision == "reject":
        dr["status"] = "rejected"
        with REPLAY.lock:
            for u in _engine().unknown:
                if u["id"] in dr["cluster"]["event_ids"]:
                    u["reclassified"] = "benign (rejected by reviewer)"
    else:
        raise HTTPException(400, "decision must be approve | reject")
    REPLAY._publish()
    return dr


class Inject(BaseModel):
    count: int = 25
    code: int = 250


@app.post("/api/debug/inject-unknown")
def inject(body: Inject):
    """Demo only: synthetic deauths with an undefined reason code, clearly marked synthetic."""
    ap = "02:00:5e:aa:00:00"
    frames = []
    for k in range(max(1, min(body.count, 200))):
        dev = f"02:00:5e:bb:00:{k % 5:02x}"
        frames.append((1, {"n": 900000 + k, "t": 0.0, "len": 26, "rate_mbps": 6.0, "freq_mhz": 5180, "signal_dbm": -70,
                           "type": "Management", "subtype": "Deauthentication", "addr1": dev, "addr2": ap, "bssid": ap,
                           "deauth": {"reason": body.code}, "synthetic": True}))
    REPLAY.inject(frames)
    return {"injected": len(frames), "reason_code": body.code, "synthetic": True}


# ---------------------------------------------------------------- dashboard
if config.WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = config.WEB_DIST / path
        return FileResponse(f if path and f.is_file() else config.WEB_DIST / "index.html")
