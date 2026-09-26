"""Convert full header-only 802.11 pcaps to JSON-lines with tshark (fast), one process per sensor.

Output rows use the same field names as convert_sensors.py (scapy) plus a few extras
(bssid, akm, eapol.msgnr, action_category, csa_new_channel). Run validate_converter.py to
check the output against the scapy JSON for the first 50 s.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from scapy.layers.dot11 import _dot11_subtypes

TSHARK = r"C:\Program Files\Wireshark\tshark.exe"
PCAP_DIR = Path(r"C:\Users\asheer\Downloads\hackaton\hackaton_airframe\hackaton_airframe")
OUT_DIR = Path(r"C:\Users\asheer\Downloads\hackaton\json_full")
DOT11_TYPE = {0: "Management", 1: "Control", 2: "Data"}

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


def _int(v: str):
    if v == "":
        return None
    return int(v, 16) if v.startswith("0x") else int(float(v))


def _float(v: str):
    return float(v) if v != "" else None


def _bool(v: str) -> bool:
    return v in ("True", "1")


def _ssid(v: str):
    if v in ("", "<MISSING>"):
        return ""
    try:
        return bytes.fromhex(v).decode("utf-8", errors="replace")
    except ValueError:
        return v


def row_to_dict(f: dict, n: int, t0: float) -> dict:
    epoch = float(f["frame.time_epoch"])
    rec = {
        "n": n,
        "t": round(epoch - t0, 6),
        "epoch": epoch,
        "len": _int(f["frame.len"]),
        "rate_mbps": _float(f["radiotap.datarate"]),
        "freq_mhz": _int(f["radiotap.channel.freq"]),
        "signal_dbm": _int(f["radiotap.dbm_antsignal"]),
        "noise_dbm": _int(f["radiotap.dbm_antnoise"]),
    }
    ftype = _int(f["wlan.fc.type"])
    if ftype is None:
        return rec
    ts = _int(f["wlan.fc.type_subtype"])
    sub = ts & 0xF
    rec["type"] = DOT11_TYPE.get(ftype, str(ftype))
    rec["subtype"] = _dot11_subtypes.get(ftype, {}).get(sub, str(sub))
    rec["retry"] = _bool(f["wlan.fc.retry"])
    rec["protected"] = _bool(f["wlan.fc.protected"])
    rec["from_ds"] = _bool(f["wlan.fc.fromds"])
    rec["to_ds"] = _bool(f["wlan.fc.tods"])
    rec["pwr_mgt"] = _bool(f["wlan.fc.pwrmgt"])
    rec["duration"] = _int(f["wlan.duration"])
    rec["addr1"] = f["wlan.ra"] or None
    rec["addr2"] = f["wlan.ta"] or None
    rec["bssid"] = f["wlan.bssid"] or None
    if f["wlan.seq"] != "":
        rec["seq"] = _int(f["wlan.seq"])
        rec["frag"] = _int(f["wlan.frag"])
    if f["wlan.ssid"] != "" or rec["subtype"] in ("Beacon", "Probe Request", "Probe Response"):
        rec["ssid"] = _ssid(f["wlan.ssid"])
    if f["wlan.rsn.akms.type"]:
        rec["akm"] = _int(f["wlan.rsn.akms.type"])
    if f["wlan.csa.new_channel_number"]:
        rec["csa_new_channel"] = _int(f["wlan.csa.new_channel_number"])

    status = _int(f["wlan.fixed.status_code"])
    reason = _int(f["wlan.fixed.reason_code"])
    s = rec["subtype"]
    if s == "Authentication":
        rec["auth"] = {"algo": _int(f["wlan.fixed.auth.alg"]), "seqnum": _int(f["wlan.fixed.auth_seq"]), "status": status}
    elif s == "Association Request":
        rec["assoc_req"] = {}
    elif s == "Association Response":
        rec["assoc_resp"] = {"status": status, "AID": _int(f["wlan.fixed.aid"])}
    elif s == "Reassociation Request":
        rec["reassoc_req"] = {"current_ap": f["wlan.fixed.current_ap"] or None}
    elif s == "Reassociation Response":
        rec["reassoc_resp"] = {"status": status, "AID": _int(f["wlan.fixed.aid"])}
    elif s == "Deauthentication":
        rec["deauth"] = {"reason": reason}
    elif s == "Disassociation":
        rec["disassoc"] = {"reason": reason}
    elif s == "Beacon":
        rec["beacon"] = {"interval_tu": _int(f["wlan.fixed.beacon"])}
    elif s in ("Action", "Action No Ack"):
        rec["action_category"] = _int(f["wlan.fixed.category_code"])
    if s == "Probe Request":
        rec["probe"] = "request"
    elif s == "Probe Response":
        rec["probe"] = "response"

    if f["eapol.type"] != "":
        e = {"type": _int(f["eapol.type"])}
        if e["type"] == 3:
            e.update({
                "msgnr": _int(f["wlan_rsna_eapol.keydes.msgnr"]),
                "key_ack": _bool(f["wlan_rsna_eapol.keydes.key_info.key_ack"]),
                "has_key_mic": _bool(f["wlan_rsna_eapol.keydes.key_info.key_mic"]),
                "install": _bool(f["wlan_rsna_eapol.keydes.key_info.install"]),
                "secure": _bool(f["wlan_rsna_eapol.keydes.key_info.secure"]),
                "key_replay_counter": _int(f["eapol.keydes.replay_counter"]),
            })
        rec["eapol"] = e
        if f["eap.code"] != "":
            rec["eap"] = {"code": _int(f["eap.code"]), "id": _int(f["eap.id"]), "type": _int(f["eap.type"])}
    return rec


def convert(i: int) -> dict:
    pcap = PCAP_DIR / f"sensor{i:02d}.pcap"
    out = OUT_DIR / f"sensor{i:02d}.jsonl"
    cmd = [TSHARK, "-r", str(pcap), "-T", "fields", "-E", "separator=\t", "-E", "occurrence=f", "-E", "quote=n"]
    for fld in FIELDS:
        cmd += ["-e", fld]
    started = time.time()
    n = 0
    t0 = None
    last = None
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1 << 20)
    with out.open("w", encoding="utf-8") as fh:
        for line in proc.stdout:
            vals = line.rstrip("\n").split("\t")
            f = dict(zip(FIELDS, vals + [""] * (len(FIELDS) - len(vals))))
            n += 1
            if t0 is None:
                t0 = float(f["frame.time_epoch"])
            last = row_to_dict(f, n, t0)
            fh.write(json.dumps(last, separators=(",", ":")))
            fh.write("\n")
    rc = proc.wait()
    meta = {
        "sensor": f"sensor{i:02d}", "source": pcap.name, "tshark_rc": rc,
        "start_epoch": t0, "end_epoch": last["epoch"] if last else None,
        "duration_s": last["t"] if last else None, "packet_count": n,
        "seconds": round(time.time() - started, 1),
    }
    (OUT_DIR / f"sensor{i:02d}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sensors = [int(a) for a in sys.argv[1:]] or list(range(1, 9))
    with Pool(min(4, len(sensors))) as pool:
        metas = pool.map(convert, sensors)
    (OUT_DIR / "summary.json").write_text(json.dumps(metas, indent=2), encoding="utf-8")
    for m in metas:
        print(m)


if __name__ == "__main__":
    main()
