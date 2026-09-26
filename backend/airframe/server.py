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
    return {"ok": True, "replay": REPLAY.state, "agent_mode": fix_agent.mode(), "model": config.AGENT_MODEL,
            "catalog": CATALOG.summary()}


@app.get("/api/snapshot")
def get_snapshot():
    return _decorate(REPLAY.snap or {})


def _decorate(snap: dict) -> dict:
    if not snap:
        return snap
    eng = REPLAY.engine
    snap = dict(snap)
    with REPLAY.lock:
        snap["proposals"] = {k: {**v, "success": fix_agent.check_success(eng, v) if v["status"] == "approved" and eng else None}
                             for k, v in PROPOSALS.items()}
        snap["agent"] = {"mode": fix_agent.mode(), "model": config.AGENT_MODEL}
        snap["clusters"] = [{k: v for k, v in c.items() if k != "example"} for c in discovery.cluster(eng)] if eng else []
        snap["drafts"] = list(DRAFTS.values())
        snap["catalog"] = CATALOG.summary()
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
        dr = discovery.draft(eng, cluster_id, REPLAY.lock)
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
        dr["adopted"] = discovery.adopt(_engine(), dr, d.note or "", REPLAY.lock)
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
