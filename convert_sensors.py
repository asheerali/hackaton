"""Convert header-only 802.11 pcaps to JSON for the first 50 seconds of each capture."""

from __future__ import annotations

import json
from pathlib import Path

from scapy.config import conf
from scapy.layers.dot11 import (
    Dot11,
    Dot11AssoReq,
    Dot11AssoResp,
    Dot11Auth,
    Dot11Beacon,
    Dot11Deauth,
    Dot11Disas,
    Dot11Elt,
    Dot11ProbeReq,
    Dot11ProbeResp,
    Dot11ReassoReq,
    Dot11ReassoResp,
    RadioTap,
)
from scapy.layers.eap import EAP, EAPOL
from scapy.packet import Packet
from scapy.utils import PcapReader

try:
    from scapy.layers.eap import EAPOL_KEY
except ImportError:  # older scapy
    EAPOL_KEY = None

conf.l2types.register(127, RadioTap)

PCAP_DIR = Path(r"C:\Users\asheer\Downloads\hackaton\hackaton_airframe\hackaton_airframe")
OUT_DIR = Path(r"C:\Users\asheer\Downloads\hackaton\json")
WINDOW_SECONDS = 50.0
DOT11_TYPE = {0: "Management", 1: "Control", 2: "Data"}


def _str(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ssid_from(pkt: Packet) -> str | None:
    elt = pkt.getlayer(Dot11Elt)
    while elt is not None:
        if getattr(elt, "ID", None) == 0:
            info = elt.info
            if isinstance(info, bytes):
                if not info:
                    return ""
                return info.decode("utf-8", errors="replace")
            return str(info) if info is not None else ""
        elt = elt.payload.getlayer(Dot11Elt)
    return None


def packet_to_dict(pkt: Packet, index: int, t0: float) -> dict:
    epoch = float(pkt.time)
    rec: dict = {
        "n": index,
        "t": round(epoch - t0, 6),
        "epoch": epoch,
        "len": len(pkt),
    }

    rt = pkt.getlayer(RadioTap)
    if rt is not None:
        rec["rate_mbps"] = _float(getattr(rt, "Rate", None))
        rec["freq_mhz"] = _int(getattr(rt, "ChannelFrequency", None))
        rec["channel_flags"] = _str(getattr(rt, "ChannelFlags", None))
        rec["signal_dbm"] = _int(getattr(rt, "dBm_AntSignal", None))
        rec["noise_dbm"] = _int(getattr(rt, "dBm_AntNoise", None))
        rec["antenna"] = _int(getattr(rt, "Antenna", None))
        flags = getattr(rt, "Flags", None)
        if flags:
            rec["radiotap_flags"] = str(flags)

    dot11 = pkt.getlayer(Dot11)
    if dot11 is None:
        rec["summary"] = pkt.summary()
        return rec

    rec["type"] = DOT11_TYPE.get(int(dot11.type), str(dot11.type))
    rec["subtype"] = str(dot11.sprintf("%Dot11.subtype%"))
    rec["fc"] = str(dot11.FCfield) if dot11.FCfield else ""
    rec["retry"] = bool(dot11.FCfield.retry) if hasattr(dot11.FCfield, "retry") else False
    rec["protected"] = bool(getattr(dot11.FCfield, "protected", False))
    rec["from_ds"] = bool(getattr(dot11.FCfield, "from-DS", getattr(dot11.FCfield, "fromDS", False)))
    rec["to_ds"] = bool(getattr(dot11.FCfield, "to-DS", getattr(dot11.FCfield, "toDS", False)))
    rec["duration"] = _int(getattr(dot11, "ID", None))
    rec["addr1"] = _str(dot11.addr1)
    rec["addr2"] = _str(dot11.addr2)
    rec["addr3"] = _str(dot11.addr3)
    rec["addr4"] = _str(getattr(dot11, "addr4", None))
    sc = getattr(dot11, "SC", None)
    if sc is not None:
        rec["seq"] = int(sc) >> 4
        rec["frag"] = int(sc) & 0xF

    ssid = ssid_from(pkt)
    if ssid is not None:
        rec["ssid"] = ssid

    auth = pkt.getlayer(Dot11Auth)
    if auth is not None:
        rec["auth"] = {
            "algo": _str(auth.algo),
            "seqnum": _int(auth.seqnum),
            "status": _str(auth.status),
        }

    asso_req = pkt.getlayer(Dot11AssoReq)
    if asso_req is not None:
        rec["assoc_req"] = {
            "cap": _str(asso_req.cap),
            "listen_interval": _int(getattr(asso_req, "listen_interval", None)),
        }

    asso_resp = pkt.getlayer(Dot11AssoResp)
    if asso_resp is not None:
        rec["assoc_resp"] = {
            "cap": _str(asso_resp.cap),
            "status": _str(asso_resp.status),
            "AID": _int(getattr(asso_resp, "AID", None)),
        }

    reasso_req = pkt.getlayer(Dot11ReassoReq)
    if reasso_req is not None:
        rec["reassoc_req"] = {
            "cap": _str(reasso_req.cap),
            "current_ap": _str(getattr(reasso_req, "current_AP", getattr(reasso_req, "addr1", None))),
        }

    reasso_resp = pkt.getlayer(Dot11ReassoResp)
    if reasso_resp is not None:
        rec["reassoc_resp"] = {
            "cap": _str(reasso_resp.cap),
            "status": _str(reasso_resp.status),
        }

    deauth = pkt.getlayer(Dot11Deauth)
    if deauth is not None:
        rec["deauth"] = {"reason": _str(deauth.reason)}

    disas = pkt.getlayer(Dot11Disas)
    if disas is not None:
        rec["disassoc"] = {"reason": _str(disas.reason)}

    beacon = pkt.getlayer(Dot11Beacon)
    if beacon is not None:
        rec["beacon"] = {
            "cap": _str(beacon.cap),
            "timestamp": _str(getattr(beacon, "timestamp", None)),
        }

    if pkt.getlayer(Dot11ProbeReq) is not None:
        rec["probe"] = "request"
    if pkt.getlayer(Dot11ProbeResp) is not None:
        rec["probe"] = "response"

    eapol = pkt.getlayer(EAPOL)
    if eapol is not None:
        rec["eapol"] = {
            "version": _str(eapol.version),
            "type": _str(eapol.type),
            "len": _int(eapol.len),
        }
        key = pkt.getlayer(EAPOL_KEY) if EAPOL_KEY is not None else None
        if key is not None:
            rec["eapol"].update(
                {
                    "key_descriptor_type": _str(getattr(key, "key_descriptor_type", None)),
                    "key_type": _str(getattr(key, "key_type", None)),
                    "key_ack": bool(getattr(key, "key_ack", False)),
                    "install": bool(getattr(key, "install", False)),
                    "secure": bool(getattr(key, "secure", False)),
                    "has_key_mic": bool(getattr(key, "has_key_mic", False)),
                    "key_replay_counter": _int(getattr(key, "key_replay_counter", None)),
                    "key_data_length": _int(getattr(key, "key_data_length", None)),
                }
            )
        eap = pkt.getlayer(EAP)
        if eap is not None:
            rec["eap"] = {
                "code": _str(getattr(eap, "code", None)),
                "id": _int(getattr(eap, "id", None)),
                "type": _str(getattr(eap, "type", None)),
            }

    return rec


def convert_pcap(pcap_path: Path, out_path: Path) -> dict:
    packets = []
    t0 = None
    scanned = 0
    with PcapReader(str(pcap_path)) as reader:
        for pkt in reader:
            scanned += 1
            epoch = float(pkt.time)
            if t0 is None:
                t0 = epoch
            if epoch - t0 > WINDOW_SECONDS:
                break
            packets.append(packet_to_dict(pkt, len(packets) + 1, t0))

    doc = {
        "sensor": pcap_path.stem,
        "source": pcap_path.name,
        "window_seconds": WINDOW_SECONDS,
        "start_epoch": t0,
        "end_epoch": packets[-1]["epoch"] if packets else t0,
        "scanned_until_cutoff": scanned,
        "packet_count": len(packets),
        "packets": packets,
    }
    out_path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return {
        "sensor": doc["sensor"],
        "packets": doc["packet_count"],
        "bytes": out_path.stat().st_size,
        "start_epoch": t0,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for i in range(1, 9):
        pcap = PCAP_DIR / f"sensor{i:02d}.pcap"
        out = OUT_DIR / f"sensor{i:02d}.json"
        print(f"converting {pcap.name} ...", flush=True)
        summaries.append(convert_pcap(pcap, out))
        print(summaries[-1], flush=True)
    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
