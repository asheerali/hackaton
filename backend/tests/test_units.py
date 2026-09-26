"""Unit tests for masking, decoding, catalog mapping and episode logic on hand-made frames."""

from airframe.catalog import Catalog
from airframe.decode import normalise
from airframe.engine import Engine
from airframe.privacy import Masker

AP = "00:0b:86:01:00:00"
AP_T = "00:0b:86:01:00:01"
CL = "b8:27:eb:00:00:99"


def mk():
    return Masker(salt=b"test-salt")


def beacon(t, bssid=AP, ssid="CORP", akm=1, n=1):
    return {"n": n, "t": t, "len": 245, "rate_mbps": 6.0, "freq_mhz": 5180, "signal_dbm": -60, "type": "Management",
            "subtype": "Beacon", "addr1": "ff:ff:ff:ff:ff:ff", "addr2": bssid, "bssid": bssid, "ssid": ssid, "akm": akm}


def mgmt(t, sub, src, dst, n, **extra):
    return {"n": n, "t": t, "len": 50, "rate_mbps": 6.0, "freq_mhz": 5180, "signal_dbm": -70, "type": "Management",
            "subtype": sub, "addr1": dst, "addr2": src, "bssid": AP_T if AP_T in (src, dst) else AP, **extra}


def eapol(t, msgnr, n, from_ap=True):
    return {"n": n, "t": t, "len": 150, "rate_mbps": 54.0, "freq_mhz": 5180, "type": "Data", "subtype": "QoS Data",
            "from_ds": from_ap, "to_ds": not from_ap, "addr1": CL if from_ap else AP_T, "addr2": AP_T if from_ap else CL,
            "bssid": AP_T, "eapol": {"type": 3, "msgnr": msgnr}}


def test_masking_is_stable_and_hides_macs():
    m = mk()
    assert m.mac(CL) == m.mac(CL) and len(m.mac(CL)) == 8 and ":" not in m.mac(CL)
    assert m.mac("ff:ff:ff:ff:ff:ff") == "broadcast"
    assert Masker(salt=b"other").mac(CL) != m.mac(CL)
    assert m.radio(AP) == m.radio(AP_T)
    assert m.register_ssid("CORP", 1) == "ENT-1" and m.register_ssid("TOOLS", 2) == "PSK-1"
    assert m.ssid("CORP") == "ENT-1" and m.ssid("") == "*"


def test_sender_and_client_roles():
    m = mk()
    f = normalise(mgmt(1.0, "Deauthentication", AP, CL, 5, deauth={"reason": 23}), 1, m)
    assert f.kind == "deauth" and f.sender == "ap" and f.client == m.mac(CL) and f.reason == 23
    g = normalise(mgmt(1.0, "Deauthentication", CL, AP, 6, deauth={"reason": 3}), 1, m)
    assert g.sender == "client" and g.client == m.mac(CL)
    p = normalise({"n": 7, "t": 1, "type": "Management", "subtype": "Probe Request", "addr1": "ff:ff:ff:ff:ff:ff",
                   "addr2": CL, "bssid": "ff:ff:ff:ff:ff:ff", "ssid": ""}, 1, m)
    assert p.ap is None and p.bssid is None and p.sender == "client"


def test_catalog_maps_every_reason_and_marks_unknown():
    c = Catalog()
    assert c.for_code("reason", 23) == "EAP-04"
    assert c.for_code("reason", 2) == "SESS-02"
    assert c.for_code("status", 17) == "ASSOC-01"
    assert c.for_code("status", 0) == "OK"
    assert c.for_code("status", 4) == "OTHER-CODE"      # reserved
    assert c.for_code("reason", 250) == "OTHER-CODE"    # not in the IEEE table


def _run(frames):
    m = mk()
    e = Engine(Catalog(), m)
    for fr in frames:
        e.process(normalise(fr, 1, m))
    e.finish()
    return e


def test_unknown_reason_goes_to_other():
    e = _run([beacon(0.0), beacon(0.1, AP_T, "TOOLS", 2),
              mgmt(1.0, "Authentication", AP_T, CL, 3, auth={"algo": 0, "seqnum": 2, "status": 0}),
              mgmt(1.1, "Association Response", AP_T, CL, 4, assoc_resp={"status": 0}),
              mgmt(2.0, "Deauthentication", AP_T, CL, 5, deauth={"reason": 250})])
    assert len(e.unknown) == 1 and e.unknown[0]["kind"] == "OTHER-CODE" and e.unknown[0]["detail"]["code"] == 250


def test_m1_repeated_without_m3_is_key01():
    fr = [beacon(0.0, AP_T, "TOOLS", 2), mgmt(1.0, "Association Response", AP_T, CL, 2, assoc_resp={"status": 0}),
          eapol(1.1, 1, 3), eapol(2.1, 1, 4), eapol(3.1, 1, 5)]
    fr += [beacon(t, AP_T, "TOOLS", 2, n=10 + int(t * 10)) for t in [x * 0.5 for x in range(4, 30)]]
    e = _run(fr)
    assert any(i.cid == "KEY-01" for i in e.inc.items.values())


def test_single_m1_then_blockack_is_not_a_failure():
    fr = [beacon(0.0, AP_T, "TOOLS", 2), mgmt(1.0, "Association Response", AP_T, CL, 2, assoc_resp={"status": 0}),
          eapol(1.1, 1, 3), mgmt(1.2, "Action", AP_T, CL, 4, action_category=3)]
    fr += [beacon(t, AP_T, "TOOLS", 2, n=10 + int(t * 10)) for t in [x * 0.5 for x in range(4, 30)]]
    e = _run(fr)
    assert not any(i.cid.startswith("KEY-0") and i.cid != "KEY-06" for i in e.inc.items.values())
    assert [o["cid"] for o in e.observations] == ["KEY-06"]


def test_m1_m3_connects():
    e = _run([beacon(0.0, AP_T, "TOOLS", 2), mgmt(1.0, "Association Response", AP_T, CL, 2, assoc_resp={"status": 0}),
              eapol(1.1, 1, 3), eapol(1.2, 3, 4)])
    assert e.net_stats()["PSK-1"] == {"attempts": 1, "connected": 1}
