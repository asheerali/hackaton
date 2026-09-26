"""End-to-end API test: replay at full speed, Part 2 proposal (offline mode), Part 3 inject -> draft -> adopt,
plus the auto-trigger behaviour (critical incidents get an automatic fast proposal; unmatched-event clusters
are drafted, validated, back-tested and adopted into the catalog with no human click, then re-run through
detection so they become real incidents)."""

import os
import shutil
import time

import pytest

os.environ["AIRFRAME_AUTOSTART"] = "0"
os.environ["AIRFRAME_AGENT_MODE"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402

from airframe import config  # noqa: E402

config.AGENT_MODE = "offline"
# test_full_flow drives Part 2/3 by hand (the pre-existing manual buttons); keep the background
# auto-triggers off for it so it isn't racing its own explicit clicks, then two dedicated tests
# below turn each flag on in isolation to verify the automatic behaviour specifically.
config.AGENT_AUTO_ANALYZE = False
config.DISCOVERY_AUTO = False
pytestmark = pytest.mark.skipif(not list(config.JSONL_DIR.glob("sensor*.jsonl")), reason="run convert_full.py first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    ext = config.CATALOG_DIR / "extensions.json"
    backup = tmp_path_factory.mktemp("cat") / "extensions.json"
    had = ext.exists()
    if had:
        shutil.copy(ext, backup)
    from airframe.server import app
    with TestClient(app) as c:
        yield c
    if had:
        shutil.copy(backup, ext)
    else:
        ext.unlink(missing_ok=True)


def wait_job(c, key, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{key}").json()
        if j["state"] in ("done", "error"):
            return j
        time.sleep(0.2)
    raise TimeoutError(key)


def wait_until(fn, timeout=30, interval=0.3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(interval)
    raise TimeoutError("condition never became true")


def test_full_flow(client):
    assert client.get("/api/health").json()["agent_mode"] == "offline"
    client.post("/api/replay", json={"action": "start", "speed": 0, "source": "jsonl"})
    t0 = time.time()
    while client.get("/api/health").json()["replay"] != "finished":
        assert time.time() - t0 < 180
        time.sleep(0.5)
    snap = client.get("/api/snapshot").json()
    assert snap["clock"]["state"] == "finished" and snap["kpi"]["devices"] > 60
    root = next(i for i in snap["incidents"] if i["catalog_id"] == "INFRA-01")
    assert root["devices_affected"] == 63

    detail = client.get(f"/api/incidents/{root['id']}").json()
    assert detail["control"][0]["healthy"] is True

    client.post(f"/api/incidents/{root['id']}/fix")
    job = wait_job(client, f"fix:{root['id']}")
    assert job["state"] == "done", job
    p = job["result"]["proposal"]
    assert job["result"]["meta"]["mode"] == "offline" and job["result"]["meta"]["validation_errors"] == []
    assert job["result"]["meta"]["trigger"] == "manual"
    assert p["owner"] == "identity/AAA"
    assert any("exclusion" in s for s in p["fix_steps"])
    assert {c["metric"] for c in p["success_criteria"]} >= {"reason23_kicks", "login_success_rate"}
    dec = client.post(f"/api/incidents/{root['id']}/fix/decision", json={"decision": "approve", "note": "test"}).json()
    assert dec["status"] == "approved"
    success = client.get("/api/snapshot").json()["proposals"][root["id"]]["success"]
    assert success and not all(s["met"] for s in success)   # nothing was actually fixed in the recording

    dev = snap["devices"][0]["id"]
    story = client.get(f"/api/devices/{dev}").json()
    assert story["story"]

    assert client.post("/api/debug/inject-unknown", json={"count": 25, "code": 250}).json()["injected"] == 25
    snap = client.get("/api/snapshot").json()
    assert snap["unknown"]["count"] == 25
    cl = snap["clusters"][0]
    assert cl["count"] == 25 and cl["code"] == 250 and cl["synthetic"]
    client.post(f"/api/discovery/{cl['cluster_id']}/draft")
    job = wait_job(client, f"draft:{cl['cluster_id']}")
    assert job["state"] == "done", job
    dr = job["result"]
    assert dr["status"] == "ready_for_review", dr
    assert dr["trigger"] == "manual"
    assert dr["entry"]["vendor_specific_codes"] is True
    adopted = client.post(f"/api/discovery/drafts/{dr['draft_id']}/decision", json={"decision": "approve"}).json()
    assert adopted["status"] == "adopted" and adopted["adopted"]["reclassified_events"] == 25
    assert client.get("/api/catalog").json()["summary"]["extensions"] == 1

    client.post("/api/debug/inject-unknown", json={"count": 3, "code": 250})
    snap = client.get("/api/snapshot").json()
    assert snap["unknown"]["count"] == 0 and snap["unknown"]["total"] == 25   # all re-classified; new frames recognised
    assert any(i["catalog_id"] == adopted["adopted"]["entry_id"] for i in snap["incidents"])

    root_alerts = [a for a in client.get("/api/snapshot").json().get("alerts", []) if a["incident_id"] == root["id"]]
    assert root_alerts and root_alerts[0]["severity"] == "critical"
    approval = client.post(f"/api/incidents/{root['id']}/approval", json={
        "selected_sensors": ["S1", "S2"],
        "priority": "P1",
        "approve": True,
    }).json()
    assert approval["approved"] is True and approval["priority"] == "P1"
    assert approval["selected_sensors"] == ["S1", "S2"]

    # the approval's sensor selection should scope the live success check (agents/fix_agent/success.py)
    snap = client.get("/api/snapshot").json()
    assert snap["proposals"][root["id"]]["sensors"] == [1, 2]

    blob = str(client.get("/api/snapshot").json())
    assert "TESLA" not in blob.upper()


def test_auto_discovery_adopts_without_human_click(client):
    """Part 3, no human intervention: an unmatched cluster past the size threshold drafts, validates,
    back-tests and adopts itself, and every event it covered is re-run through detection (Engine.
    ingest_reclassified) so it becomes a real incident - "then again the incident workflow is run"."""
    config.DISCOVERY_AUTO = True
    try:
        before_ext = client.get("/api/catalog").json()["summary"]["extensions"]
        # a fresh, distinct code so this cluster can't overlap with the one test_full_flow adopted manually
        client.post("/api/debug/inject-unknown", json={"count": 5, "code": 251})

        def adopted_auto_draft():
            snap = client.get("/api/snapshot").json()
            return next((d for d in snap["drafts"]
                        if d.get("trigger") == "auto" and d["status"] == "adopted"
                        and d["entry"]["reason_codes"] == [251]), None)

        dr = wait_until(adopted_auto_draft, timeout=30)
        assert dr["adopted"]["reclassified_events"] == 5
        new_id = dr["adopted"]["entry_id"]

        snap = client.get("/api/snapshot").json()
        assert snap["catalog"]["extensions"] == before_ext + 1
        assert any(i["catalog_id"] == new_id for i in snap["incidents"]), "reclassified events should create real incidents"
        assert not any(u["detail"].get("code") == 251 for u in snap["unknown"]["recent"] if not u.get("reclassified"))
    finally:
        config.DISCOVERY_AUTO = False


def test_auto_fix_proposal_for_critical_incident(client):
    """Part 2, "auto analyzed... fastly": a critical incident gets a fix proposal with no click,
    using the fast/small model path (fast=True) rather than the manual full-model one."""
    import airframe.server as server_mod

    snap = client.get("/api/snapshot").json()
    root = next(i for i in snap["incidents"] if i["catalog_id"] == "INFRA-01")
    server_mod.PROPOSALS.pop(root["id"], None)
    server_mod._auto_state["fix_seen"].discard(root["id"])
    config.AGENT_AUTO_ANALYZE = True
    try:
        def auto_proposed():
            snap = client.get("/api/snapshot").json()
            rec = snap["proposals"].get(root["id"])
            return rec if rec and rec["meta"].get("trigger") == "auto" else None

        rec = wait_until(auto_proposed, timeout=15)
        assert rec["meta"]["fast"] is True
        assert rec["proposal"]["owner"] == "identity/AAA"
    finally:
        config.AGENT_AUTO_ANALYZE = False
