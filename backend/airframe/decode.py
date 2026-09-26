"""Normalise converter-schema dicts into masked Frame records."""

from __future__ import annotations

from dataclasses import dataclass

from .privacy import Masker

KIND_BY_SUBTYPE = {
    "Beacon": "beacon", "Probe Request": "probe_req", "Probe Response": "probe_resp",
    "Authentication": "auth", "Association Request": "assoc_req", "Association Response": "assoc_resp",
    "Reassociation Request": "reassoc_req", "Reassociation Response": "reassoc_resp",
    "Deauthentication": "deauth", "Disassociation": "disassoc", "Action": "action", "Action No Ack": "action",
    "Ack": "ack",
}


@dataclass(slots=True)
class Frame:
    s: int                    # sensor index 1..N
    t: float                  # event time: seconds since this sensor's capture start
    n: int                    # frame number in the sensor's capture
    kind: str
    retry: bool = False
    rate: float | None = None
    freq: int | None = None
    sig: int | None = None
    length: int | None = None
    sender: str | None = None     # "ap" | "client" | None
    ap: str | None = None         # masked AP radio id
    bssid: str | None = None      # masked BSSID
    net: str | None = None        # network label, e.g. ENT-1
    client: str | None = None     # masked client MAC
    cclass: str | None = None     # laptop / phone / iot / device
    status: int | None = None
    reason: int | None = None
    auth_seq: int | None = None
    eap_code: int | None = None
    eap_type: int | None = None
    msgnr: int | None = None
    action_cat: int | None = None
    akm: int | None = None
    csa: int | None = None
    to_ds: bool = False
    synthetic: bool = False


def _is_group(mac: str | None) -> bool:
    return bool(mac) and (int(mac[:2], 16) & 1) == 1


def normalise(raw: dict, sensor: int, mk: Masker) -> Frame:
    sub = raw.get("subtype")
    kind = KIND_BY_SUBTYPE.get(sub)
    if kind is None:
        if "eapol" in raw:
            kind = "eap" if "eap" in raw else ("eapol_key" if raw["eapol"].get("type") == 3 else "eapol_other")
        elif raw.get("type") == "Data":
            kind = "null" if "Null" in (sub or "") else "data"
        elif raw.get("type") == "Control":
            kind = "ctrl"
        else:
            kind = "other"
    elif "eapol" in raw:
        kind = "eap" if "eap" in raw else "eapol_key"

    a1, a2, bssid = raw.get("addr1"), raw.get("addr2"), raw.get("bssid")
    sender = None
    client_raw = None
    if kind in ("ack", "ctrl"):
        client_raw = None
    elif raw.get("type") == "Data" or kind in ("eap", "eapol_key", "eapol_other", "null", "data"):
        if raw.get("from_ds"):
            sender, client_raw = "ap", a1
        elif raw.get("to_ds"):
            sender, client_raw = "client", a2
    elif bssid and a2:
        if a2 == bssid:
            sender, client_raw = "ap", a1
        else:
            sender, client_raw = "client", a2
    if client_raw and _is_group(client_raw):
        client_raw = None
    if bssid and _is_group(bssid):
        bssid = None

    f = Frame(
        s=sensor, t=raw["t"], n=raw["n"], kind=kind, retry=bool(raw.get("retry")), rate=raw.get("rate_mbps"),
        freq=raw.get("freq_mhz"), sig=raw.get("signal_dbm"), length=raw.get("len"), sender=sender,
        ap=mk.radio(bssid), bssid=mk.mac(bssid), client=mk.mac(client_raw),
        cclass=mk.device_class(client_raw) if client_raw else None, akm=raw.get("akm"),
        csa=raw.get("csa_new_channel"), to_ds=bool(raw.get("to_ds")), synthetic=bool(raw.get("synthetic")),
    )
    if kind == "beacon" and "ssid" in raw:
        f.net = mk.register_ssid(raw["ssid"], raw.get("akm"))
    elif "ssid" in raw:
        f.net = mk.ssid(raw["ssid"])
    if "auth" in raw:
        f.status, f.auth_seq = raw["auth"].get("status"), raw["auth"].get("seqnum")
    for key in ("assoc_resp", "reassoc_resp"):
        if key in raw:
            f.status = raw[key].get("status")
    for key in ("deauth", "disassoc"):
        if key in raw:
            f.reason = raw[key].get("reason")
    if "eap" in raw:
        f.eap_code, f.eap_type = raw["eap"].get("code"), raw["eap"].get("type")
    if "eapol" in raw:
        f.msgnr = raw["eapol"].get("msgnr")
    if "action_category" in raw:
        f.action_cat = raw["action_category"]
    return f
