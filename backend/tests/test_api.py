"""End-to-end API test: replay at full speed, Part 2 proposal (offline mode), Part 3 inject -> draft -> adopt."""

import os
import shutil
import time

import pytest

os.environ["AIRFRAME_AUTOSTART"] = "0"
os.environ["AIRFRAME_AGENT_MODE"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402

from airframe import config  # noqa: E402

config.AGENT_MODE = "offline"
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
    assert dr["entry"]["vendor_specific_codes"] is True
    adopted = client.post(f"/api/discovery/drafts/{dr['draft_id']}/decision", json={"decision": "approve"}).json()
    assert adopted["status"] == "adopted" and adopted["adopted"]["reclassified_events"] == 25
    assert client.get("/api/catalog").json()["summary"]["extensions"] == 1

    client.post("/api/debug/inject-unknown", json={"count": 3, "code": 250})
    snap = client.get("/api/snapshot").json()
    assert snap["unknown"]["count"] == 0 and snap["unknown"]["total"] == 25   # all re-classified; new frames recognised
    assert any(i["catalog_id"] == adopted["adopted"]["entry_id"] for i in snap["incidents"])

    blob = str(client.get("/api/snapshot").json())
    assert "TESLA" not in blob.upper()
