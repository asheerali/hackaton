"""Compare tshark JSONL (json_full/) against the scapy JSON (json/) for every frame in the 50 s window."""

from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).parent


def eapol_msg_from_flags(e: dict):
    ack, mic, sec = e.get("key_ack"), e.get("has_key_mic"), e.get("secure")
    if ack and not mic:
        return 1
    if ack and mic:
        return 3
    if not ack and mic and not sec:
        return 2
    if not ack and mic and sec:
        return 4
    return None


def norm_scapy(p: dict) -> dict:
    out = {k: p.get(k) for k in ("n", "len", "rate_mbps", "freq_mhz", "signal_dbm", "noise_dbm", "type", "subtype",
                                  "retry", "protected", "from_ds", "to_ds", "addr1", "addr2", "seq", "ssid")}
    out["epoch"] = round(p["epoch"], 6)
    for key, sub in (("auth", "status"), ("assoc_resp", "status"), ("reassoc_resp", "status"),
                     ("deauth", "reason"), ("disassoc", "reason")):
        if key in p:
            out[f"{key}.{sub}"] = int(p[key][sub])
    if "auth" in p:
        out["auth.seqnum"] = p["auth"]["seqnum"]
    if "eapol" in p:
        out["eapol.type"] = int(p["eapol"]["type"])
        if out["eapol.type"] == 3:
            out["eapol.msg"] = eapol_msg_from_flags(p["eapol"])
    if "eap" in p:
        out["eap"] = (int(p["eap"]["code"]), p["eap"]["id"], int(p["eap"]["type"]) if p["eap"]["type"] not in (None, "None") else None)
    return out


def norm_tshark(p: dict) -> dict:
    out = {k: p.get(k) for k in ("n", "len", "rate_mbps", "freq_mhz", "signal_dbm", "noise_dbm", "type", "subtype",
                                  "retry", "protected", "from_ds", "to_ds", "addr1", "addr2", "seq", "ssid")}
    out["epoch"] = round(p["epoch"], 6)
    for key, sub in (("auth", "status"), ("assoc_resp", "status"), ("reassoc_resp", "status"),
                     ("deauth", "reason"), ("disassoc", "reason")):
        if key in p:
            out[f"{key}.{sub}"] = p[key][sub]
    if "auth" in p:
        out["auth.seqnum"] = p["auth"]["seqnum"]
    if "eapol" in p:
        out["eapol.type"] = p["eapol"]["type"]
        if out["eapol.type"] == 3:
            out["eapol.msg"] = p["eapol"]["msgnr"]
    if "eap" in p:
        out["eap"] = (p["eap"]["code"], p["eap"]["id"], p["eap"]["type"])
    return out


def main() -> None:
    total = 0
    diffs = collections.Counter()
    examples = {}
    for i in range(1, 9):
        scapy_doc = json.loads((ROOT / "json" / f"sensor{i:02d}.json").read_text(encoding="utf-8"))
        want = {p["n"]: norm_scapy(p) for p in scapy_doc["packets"]}
        with (ROOT / "json_full" / f"sensor{i:02d}.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                p = json.loads(line)
                if p["n"] > max(want):
                    break
                got = norm_tshark(p)
                exp = want[p["n"]]
                total += 1
                for k in set(exp) | set(got):
                    a, b = exp.get(k), got.get(k)
                    if k == "rate_mbps" and a is not None and b is not None:
                        a, b = float(a), float(b)
                    if a != b:
                        diffs[k] += 1
                        examples.setdefault(k, (i, p["n"], a, b))
    print(f"frames compared: {total}")
    if not diffs:
        print("ALL FIELDS MATCH")
    for k, c in diffs.most_common():
        print(f"  {k}: {c} mismatches, e.g. sensor{examples[k][0]:02d} n={examples[k][1]} scapy={examples[k][2]!r} tshark={examples[k][3]!r}")


if __name__ == "__main__":
    main()
