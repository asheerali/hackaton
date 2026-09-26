"""Golden test: replaying the full captures must reproduce the verified facts (skill reference/dataset-facts.md)."""

import json
import re

import pytest

from airframe import config
from airframe.runner import build_engine, run_batch
from airframe.views import incident_dict, snapshot

pytestmark = pytest.mark.skipif(not list(config.JSONL_DIR.glob("sensor*.jsonl")), reason="run convert_full.py first")


@pytest.fixture(scope="module")
def eng():
    e = build_engine()
    run_batch(e, "jsonl")
    return e


@pytest.fixture(scope="module")
def tops(eng):
    return [incident_dict(eng, i, full=True) for i in eng.inc.top_level()]


def by_cid(tops, cid):
    return [i for i in tops if i["catalog_id"] == cid]


def test_frames_and_duration(eng):
    assert eng.frames == 1_118_853
    assert 1801 < eng.t < 1803


def test_one_root_for_the_login_outage(tops):
    roots = by_cid(tops, "INFRA-01")
    assert len(roots) == 1
    r = roots[0]
    assert r["severity"] == "critical"
    assert r["devices_affected"] == 63
    assert len(r["where"]["aps"]) == 26
    assert len(r["where"]["channels"]) == 8 and len(r["where"]["sensors"]) == 8
    assert r["signature"]["reask_s"] == pytest.approx(30.0, abs=0.1)
    assert r["signature"]["kick_s"] == pytest.approx(60.0, abs=0.1)
    assert r["signature"]["devices_heard_answering"] == 12


def test_root_children_one_finding_per_device(tops):
    r = by_cid(tops, "INFRA-01")[0]
    assert r["children_by_type"] == {"EAP-01": 63, "EAP-04": 63, "SESS-01": 63, "SESS-02": 18, "DISC-03": 1}


def test_control_network_healthy(tops):
    ctrl = by_cid(tops, "INFRA-01")[0]["control"]
    assert len(ctrl) == 1
    c = ctrl[0]
    assert c["kind"] == "PSK" and c["attempts"] == 32 and c["connected"] == 31 and c["healthy"]


def test_time_to_detect(eng):
    assert eng.first_fail_join_t == pytest.approx(11.4, abs=0.1)
    assert eng.inc.first_root_t - eng.first_fail_join_t <= 40


def test_missing_networks_and_silent_ap(tops):
    miss = by_cid(tops, "DISC-01")
    assert len(miss) == 5
    kinds = sorted(i["metrics"]["missing"].split("-")[0] for i in miss)
    assert kinds == ["ENT", "ENT", "ENT", "PSK", "PSK"]
    assert len(by_cid(tops, "DISC-02")) == 1


def test_leave_burst(tops):
    b = by_cid(tops, "SESS-08")
    assert len(b) == 1 and b[0]["devices_affected"] == 15


def test_channel_findings_grouped(tops):
    for cid in ("RF-01", "RF-03", "RF-04"):
        items = by_cid(tops, cid)
        assert len(items) == 1, cid
        assert len(items[0]["metrics"]["per_channel"]) == 8, cid
    pc = by_cid(tops, "RF-01")[0]["metrics"]["per_channel"]
    assert all(28 < v < 34 for v in pc.values())


def test_false_positive_guards(eng, tops):
    bad = [i["catalog_id"] for i in tops for k in [i] if re.match(r"(AUTH|ASSOC|ROAM|SEC)-|KEY-0[1-5]|DISC-06|SENS-01", k["catalog_id"])]
    assert bad == []
    assert eng.unknown == []
    assert [o["cid"] for o in eng.observations] == ["KEY-06"]


def test_probe_storm_numbers(eng):
    s = snapshot(eng, {})["series"]["site"]
    pr = sum(b["probe_resp"] for b in s)
    rt = sum(b["probe_retry"] for b in s)
    assert pr == 173_964
    assert round(100 * rt / pr, 1) == 31.3


def test_device_states(eng):
    rows = snapshot(eng, {})["devices"]
    corp = [r for r in rows if r["network"] == "ENT-1" and r["attempts"] > 0]
    assert len(corp) == 63
    assert sum(r["state"] == "excluded" for r in corp) == 18
    assert sum(r["connected"] for r in corp) == 0


def test_no_raw_identifiers_leave_the_engine(eng, tops):
    blob = json.dumps(snapshot(eng, {})) + json.dumps(tops)
    assert not re.search(r"\b[0-9a-f]{2}(:[0-9a-f]{2}){5}\b", blob, re.I)
    assert "TESLA" not in blob.upper()
