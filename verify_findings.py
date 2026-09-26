"""Recompute every number quoted in the v3 report from json_full/ and check it (PASS/FAIL).

usage: python verify_findings.py            (needs json_full/ from convert_full.py)
"""

from __future__ import annotations

import collections as C
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).parent / "json_full"
AP_OUI = "00:0b:86"
KIND = {"3c:58:c2": "laptop", "b8:27:eb": "iot", "f0:18:98": "phone"}
checks: list[tuple[str, object, object, bool]] = []


def check(name, got, expected, ok=None):
    checks.append((name, got, expected, (got == expected) if ok is None else ok))


def kind(mac):
    return KIND.get((mac or "")[:8], "other")


def is_ap(mac):
    return bool(mac) and mac.startswith(AP_OUI)


def main() -> None:
    frames = C.Counter()
    duration = {}
    channels = {}
    bssid_sensors = C.defaultdict(set)
    ssid_akm = set()
    beacon_rates = set()
    rssi = C.defaultdict(set)
    beacon_ts = C.defaultdict(list)
    probe_resp = probe_retry = probe_req = 0
    retries = C.Counter()
    probe_min = C.Counter()
    tl = C.defaultdict(list)
    for i in range(1, 9):
        meta = json.loads((ROOT / f"sensor{i:02d}.meta.json").read_text())
        duration[i] = meta["duration_s"]
        with (ROOT / f"sensor{i:02d}.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                p = json.loads(line)
                frames[i] += 1
                channels.setdefault(i, set()).add(p.get("freq_mhz"))
                s = p.get("subtype")
                if p.get("retry"):
                    retries[s] += 1
                if s == "Beacon":
                    bssid_sensors[p["addr2"]].add(i)
                    ssid_akm.add((p["addr2"][-2:], p.get("ssid"), p.get("akm")))
                    beacon_rates.add(p["rate_mbps"])
                    rssi[p["addr2"]].add(p["signal_dbm"])
                    beacon_ts[(i, p["addr2"])].append(p["t"])
                    continue
                if s == "Probe Response":
                    probe_resp += 1
                    probe_retry += p["retry"]
                    probe_min[int(p["t"] // 60)] += 1
                    continue
                if s == "Probe Request":
                    probe_req += 1
                    continue
                if s == "Ack" or (p.get("type") == "Data" and "eapol" not in p):
                    if p.get("type") == "Data" and p.get("to_ds") and not is_ap(p.get("addr2")):
                        tl[p["addr2"]].append((p["t"], i, "DATA_UP", p["addr1"]))
                    continue
                a1, a2 = p.get("addr1"), p.get("addr2")
                client = a2 if not is_ap(a2) else a1
                if not client or client.startswith(("ff:ff", "33:33")):
                    continue
                ap = a2 if is_ap(a2) else a1
                if "auth" in p:
                    lab = f"AUTH{p['auth']['seqnum']}_{p['auth']['status']}"
                elif "assoc_resp" in p:
                    lab = f"ASSOC_RESP_{p['assoc_resp']['status']}"
                elif "deauth" in p:
                    lab = f"DEAUTH_{p['deauth']['reason']}"
                elif "disassoc" in p:
                    lab = f"DISASSOC_{p['disassoc']['reason']}"
                elif "eap" in p:
                    lab = f"EAP_{p['eap']['code']}"
                elif "eapol" in p and p["eapol"]["type"] == 3:
                    lab = f"M{p['eapol']['msgnr']}"
                else:
                    lab = s
                tl[client].append((p["t"], i, lab, ap))

    total = sum(frames.values())
    check("total frames", total, 1_118_853)
    check("capture length per sensor ~1802 s", sorted({round(d) for d in duration.values()}), [1802])
    check("one fixed channel per sensor", [sorted(channels[i]) for i in range(1, 9)],
          [[5180], [5200], [5220], [5240], [5745], [5765], [5785], [5805]])
    check("BSSIDs heard", len(bssid_sensors), 53)
    check("BSSIDs heard by >1 sensor", sum(1 for v in bssid_sensors.values() if len(v) > 1), 0)
    check("NET-C=802.1X (AKM 1), NET-T=PSK (AKM 2)", sorted({(s, a) for _, s, a in ssid_akm}),
          [("TESLA-CORP", 1), ("TESLA-TOOLS", 2)])
    check("beacon rate field (Mbit/s)", sorted(beacon_rates), [1.0])
    check("BSSIDs with constant RSSI", sum(1 for v in rssi.values() if len(v) == 1), 53)
    present = C.defaultdict(set)
    for b in bssid_sensors:
        present[int(b.split(":")[3], 16)].add("C" if b.endswith("00") else "T")
    missing = sorted((ap, net) for ap in range(1, 31) for net in "CT" if net not in present.get(ap, set()))
    check("missing networks (AP, net)", missing,
          [(3, "C"), (6, "T"), (13, "C"), (13, "T"), (16, "C"), (17, "C"), (28, "T")])
    losses = []
    for (_, _), ts in beacon_ts.items():
        exp = (ts[-1] - ts[0]) / 0.1024 + 1
        losses.append(100 * (1 - len(ts) / exp))
    check("beacon loss % range", (round(min(losses), 1), round(max(losses), 1)), (1.8, 2.3),
          ok=1.5 < min(losses) and max(losses) < 2.5)

    corp = {m: sorted(L) for m, L in tl.items() if any(x[2].startswith("EAP") for x in L)}
    check("NET-C clients (laptop, phone)", C.Counter(kind(m) for m in corp), C.Counter({"phone": 33, "laptop": 30}))
    joins = sum(1 for L in corp.values() for x in L if x[2] == "ASSOC_RESP_0")
    check("NET-C join attempts accepted at association", joins, 654)
    check("EAP Success/Failure frames", sum(1 for L in tl.values() for x in L if x[2] in ("EAP_3", "EAP_4")), 0)
    check("EAPOL-Key M1 to NET-C clients", sum(1 for L in corp.values() for x in L if x[2] == "M1"), 0)
    check("NET-C clients whose EAP Identity answer was heard", sum(1 for L in corp.values() if any(x[2] == "EAP_2" for x in L)), 12)
    reask, kick = [], []
    for L in corp.values():
        req = [x[0] for x in L if x[2] == "EAP_1"]
        reask += [b - a for a, b in zip(req, req[1:]) if b - a < 40]
        js = [x[0] for x in L if x[2] == "ASSOC_RESP_0"]
        for j in js:
            k = next((x[0] for x in L if x[0] > j and x[2] == "DEAUTH_23"), None)
            nj = next((t for t in js if t > j), None)
            if k and (nj is None or k < nj):
                kick.append(k - j)
    check("EAP re-ask interval median (s)", round(st.median(reask), 1), 30.0)
    check("join -> reason-23 kick median (s)", round(st.median(kick), 1), 60.0)
    check("reason-23 deauths", sum(1 for L in tl.values() for x in L if x[2] == "DEAUTH_23"), 506)
    r2 = {m for m, L in corp.items() if any(x[2] in ("DEAUTH_2", "DISASSOC_2") for x in L)}
    check("clients in reason-2 fast-reject phase", len(r2), 18)
    check("reason-2 frames (deauth + disassoc)", sum(1 for L in tl.values() for x in L if x[2] in ("DEAUTH_2", "DISASSOC_2")), 1477)
    first_r2 = min(x[0] for m in r2 for x in corp[m] if x[2] in ("DEAUTH_2", "DISASSOC_2"))
    check("first reason-2 (s)", round(first_r2), 402)
    check("reason-23 kicks before reason-2 phase, per client", sorted({sum(1 for x in corp[m] if x[2] == "DEAUTH_23") for m in r2}), [3, 4, 5])
    onset = {m: min(x[0] for x in corp[m] if x[2] in ("DEAUTH_2", "DISASSOC_2")) for m in r2}
    check("reason-23 after each client's reason-2 onset", sum(1 for m in r2 for x in corp[m] if x[2] == "DEAUTH_23" and x[0] > onset[m]), 0)

    iot = {m: sorted(L) for m, L in tl.items() if kind(m) == "iot"}
    check("IoT devices seen joining NET-T", len([m for m, L in iot.items() if any(x[2] == "ASSOC_RESP_0" for x in L)]), 24)
    check("IoT joins with M3 (proves valid M2)", sum(1 for L in iot.values() for x in L if x[2] == "M3"), 31)
    check("IoT joins with M1 but no M3 seen", sum(1 for L in iot.values() if sum(x[2] == "M1" for x in L) > sum(x[2] == "M3" for x in L)), 1)
    check("IoT devices seen sending data", sum(1 for L in iot.values() if any(x[2] == "DATA_UP" for x in L)), 4)
    check("reason-15/14/16 (4-way / MIC / group key) deauths", sum(1 for L in tl.values() for x in L if x[2] in ("DEAUTH_15", "DEAUTH_14", "DEAUTH_16")), 0)
    check("non-zero auth/assoc status codes", sum(1 for L in tl.values() for x in L if x[2].startswith(("AUTH", "ASSOC_RESP")) and not x[2].endswith("_0")), 0)
    r3 = sorted(x[0] for L in tl.values() for x in L if x[2] == "DEAUTH_3")
    check("client 'leaving' deauths (reason 3)", len(r3), 16)
    check("of which in first 9 s", sum(1 for t in r3 if t < 9), 15)

    check("probe responses", probe_resp, 173_964)
    check("probe response retry %", round(100 * probe_retry / probe_resp, 1), 31.3)
    check("probe requests heard", probe_req, 6_024)
    check("peak probe responses in one minute", max(probe_min.values()), 13_015)
    non_probe_retry = sum(v for k, v in retries.items() if k != "Probe Response")
    check("retries that are not probe responses", non_probe_retry, 60)

    width = max(len(c[0]) for c in checks)
    fails = 0
    for name, got, exp, ok in checks:
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {got}" + ("" if ok else f"   (expected {exp})"))
    print(f"\n{len(checks) - fails}/{len(checks)} checks passed")


if __name__ == "__main__":
    main()
