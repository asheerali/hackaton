"""tshark field extraction: the same schema as convert_full.py, without importing scapy."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from . import config

DOT11_TYPE = {0: "Management", 1: "Control", 2: "Data"}
SUBTYPES = {
    0: {0: "Association Request", 1: "Association Response", 2: "Reassociation Request", 3: "Reassociation Response",
        4: "Probe Request", 5: "Probe Response", 6: "Timing Advertisement", 8: "Beacon", 9: "ATIM",
        10: "Disassociation", 11: "Authentication", 12: "Deauthentication", 13: "Action", 14: "Action No Ack"},
    1: {2: "Trigger", 3: "TACK", 4: "Beamforming Report Poll", 5: "VHT/HE NDP Announcement", 6: "Control Frame Extension",
        7: "Control Wrapper", 8: "Block Ack Request", 9: "Block Ack", 10: "PS-Poll", 11: "RTS", 12: "CTS", 13: "Ack",
        14: "CF-End", 15: "CF-End+CF-Ack"},
    2: {0: "Data", 1: "Data+CF-Ack", 2: "Data+CF-Poll", 3: "Data+CF-Ack+CF-Poll", 4: "Null (no data)",
        5: "CF-Ack (no data)", 6: "CF-Poll (no data)", 7: "CF-Ack+CF-Poll (no data)", 8: "QoS Data",
        9: "QoS Data+CF-Ack", 10: "QoS Data+CF-Poll", 11: "QoS Data+CF-Ack+CF-Poll", 12: "QoS Null (no data)",
        14: "QoS CF-Poll (no data)", 15: "QoS CF-Ack+CF-Poll (no data)"},
}

FIELDS = [
    "frame.number", "frame.time_epoch", "frame.len",
    "radiotap.datarate", "radiotap.channel.freq", "radiotap.dbm_antsignal", "radiotap.dbm_antnoise",
    "wlan.fc.type", "wlan.fc.type_subtype", "wlan.fc.retry", "wlan.fc.protected", "wlan.fc.fromds",
    "wlan.fc.tods", "wlan.fc.pwrmgt", "wlan.duration", "wlan.ra", "wlan.ta", "wlan.bssid", "wlan.seq", "wlan.frag",
    "wlan.ssid", "wlan.fixed.auth.alg", "wlan.fixed.auth_seq", "wlan.fixed.status_code",
    "wlan.fixed.reason_code", "wlan.fixed.aid", "wlan.fixed.current_ap", "wlan.fixed.beacon",
    "wlan.fixed.category_code", "wlan.rsn.akms.type", "wlan.csa.new_channel_number",
    "eapol.type", "wlan_rsna_eapol.keydes.msgnr", "wlan_rsna_eapol.keydes.key_info.key_ack",
    "wlan_rsna_eapol.keydes.key_info.key_mic", "wlan_rsna_eapol.keydes.key_info.install",
    "wlan_rsna_eapol.keydes.key_info.secure", "eapol.keydes.replay_counter",
    "eap.code", "eap.id", "eap.type",
]


def find_tshark() -> str | None:
    for c in config.TSHARK_CANDIDATES:
        if c and Path(c).exists():
            return c
    return shutil.which("tshark")


def _int(v: str):
    if v == "":
        return None
    return int(v, 16) if v.startswith("0x") else int(float(v))


def _float(v: str):
    return float(v) if v != "" else None


def _bool(v: str) -> bool:
    return v in ("True", "1")


def _ssid(v: str) -> str:
    if v in ("", "<MISSING>"):
        return ""
    try:
        return bytes.fromhex(v).decode("utf-8", errors="replace")
    except ValueError:
        return v


def row_to_dict(f: dict, n: int, t0: float) -> dict:
    """One tshark field row -> the converter's JSON schema (see convert_full.py)."""
    epoch = float(f["frame.time_epoch"])
    rec = {
        "n": n, "t": round(epoch - t0, 6), "epoch": epoch, "len": _int(f["frame.len"]),
        "rate_mbps": _float(f["radiotap.datarate"]), "freq_mhz": _int(f["radiotap.channel.freq"]),
        "signal_dbm": _int(f["radiotap.dbm_antsignal"]), "noise_dbm": _int(f["radiotap.dbm_antnoise"]),
    }
    ftype = _int(f["wlan.fc.type"])
    if ftype is None:
        return rec
    sub = _int(f["wlan.fc.type_subtype"]) & 0xF
    s = SUBTYPES.get(ftype, {}).get(sub, str(sub))
    rec.update({
        "type": DOT11_TYPE.get(ftype, str(ftype)), "subtype": s,
        "retry": _bool(f["wlan.fc.retry"]), "protected": _bool(f["wlan.fc.protected"]),
        "from_ds": _bool(f["wlan.fc.fromds"]), "to_ds": _bool(f["wlan.fc.tods"]), "pwr_mgt": _bool(f["wlan.fc.pwrmgt"]),
        "duration": _int(f["wlan.duration"]),
        "addr1": f["wlan.ra"] or None, "addr2": f["wlan.ta"] or None, "bssid": f["wlan.bssid"] or None,
    })
    if f["wlan.seq"] != "":
        rec["seq"] = _int(f["wlan.seq"])
    if f["wlan.ssid"] != "" or s in ("Beacon", "Probe Request", "Probe Response"):
        rec["ssid"] = _ssid(f["wlan.ssid"])
    if f["wlan.rsn.akms.type"]:
        rec["akm"] = _int(f["wlan.rsn.akms.type"])
    if f["wlan.csa.new_channel_number"]:
        rec["csa_new_channel"] = _int(f["wlan.csa.new_channel_number"])
    status, reason = _int(f["wlan.fixed.status_code"]), _int(f["wlan.fixed.reason_code"])
    if s == "Authentication":
        rec["auth"] = {"algo": _int(f["wlan.fixed.auth.alg"]), "seqnum": _int(f["wlan.fixed.auth_seq"]), "status": status}
    elif s == "Association Request":
        rec["assoc_req"] = {}
    elif s == "Association Response":
        rec["assoc_resp"] = {"status": status, "AID": _int(f["wlan.fixed.aid"])}
    elif s == "Reassociation Request":
        rec["reassoc_req"] = {}
    elif s == "Reassociation Response":
        rec["reassoc_resp"] = {"status": status, "AID": _int(f["wlan.fixed.aid"])}
    elif s == "Deauthentication":
        rec["deauth"] = {"reason": reason}
    elif s == "Disassociation":
        rec["disassoc"] = {"reason": reason}
    elif s in ("Action", "Action No Ack"):
        rec["action_category"] = _int(f["wlan.fixed.category_code"])
    if f["eapol.type"] != "":
        e = {"type": _int(f["eapol.type"])}
        if e["type"] == 3:
            e["msgnr"] = _int(f["wlan_rsna_eapol.keydes.msgnr"])
        rec["eapol"] = e
        if f["eap.code"] != "":
            rec["eap"] = {"code": _int(f["eap.code"]), "id": _int(f["eap.id"]), "type": _int(f["eap.type"])}
    return rec


def stream_pcap(pcap: Path, tshark: str) -> Iterator[dict]:
    """Decode a pcap with tshark, yielding converter-schema dicts as they are produced (line-flushed)."""
    cmd = [tshark, "-r", str(pcap), "-l", "-T", "fields", "-E", "separator=\t", "-E", "occurrence=f", "-E", "quote=n"]
    for fld in FIELDS:
        cmd += ["-e", fld]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            bufsize=1 << 16)
    t0 = None
    n = 0
    try:
        for line in proc.stdout:
            vals = line.rstrip("\n").split("\t")
            f = dict(zip(FIELDS, vals + [""] * (len(FIELDS) - len(vals))))
            n += 1
            if t0 is None:
                t0 = float(f["frame.time_epoch"])
            yield row_to_dict(f, n, t0)
    finally:
        proc.kill()
        proc.wait()
