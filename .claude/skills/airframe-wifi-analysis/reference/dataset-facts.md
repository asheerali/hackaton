# Dataset facts: the test oracle (full captures)

Verified on `json_full/` (all 1,802 s of every sensor) on 2026-09-25. `python verify_findings.py` recomputes the starred (★) items: 36/36 pass. Facts measured with scratch analysis and not yet in the script are marked (m). The earlier 50 s facts are superseded.

Pseudonyms: `L-nn` laptop, `H-nn` phone, `I-nn` IoT, where nn = last MAC byte in decimal; `APnn` = decimal of the 4th BSSID byte. Homing rule (verified for every device, 0 exceptions): laptop N → AP N, phone N → AP N+5, IoT N → AP N+12 (all mod 30, 1-based).

## Inventory
- ★ 1,118,853 frames; ★ 1,802 s per sensor; start epochs differ by up to 2.3 s.
- ★ One fixed channel per sensor: S1 36, S2 40, S3 44, S4 48, S5 149, S6 153, S7 157, S8 161. 0 channel-switch announcements.
- ★ 53 BSSIDs, ★ none heard by more than one sensor. ★ NET-C = AKM 1 (802.1X), NET-T = AKM 2 (PSK).
- ★ Missing all 30 min: NET-C on AP03, AP13, AP16, AP17; NET-T on AP06, AP13, AP28.
- ★ All 914,057 beacons at 1 Mbit/s; ★ RSSI constant on 53/53 BSSIDs; ★ beacon loss 1.7–2.3%; longest gap 0.41 s; no sensor deaf interval (m).
- Clients: ★ 63 NET-C devices (30 laptops, 33 phones); ★ 24 IoT on NET-T. (m) No device ever changes AP (0 roams).

## F1 NET-C 802.1X stall (EAP-01 + EAP-04 + INFRA-01)
- ★ 654 accepted associations, ★ 0 EAP Success/Failure, ★ 0 EAPOL M1 to NET-C devices, on 26 APs (m).
- ★ EAP Identity re-ask median 30.0 s; ★ reason-23 kick median 60.0 s after join (488/489 within 60 ± 0.1 s (m)); ★ 506 reason-23 deauths.
- ★ 12 NET-C devices heard answering Identity (each within 1 ms); the other 51 have 0 own join frames heard (m).
- (m) First attempts: laptops at t_rel 11.4 … 79.4 s, phones 81.4 … 153.6 s, every 2.0 s.
- (m) Streaming detection: first re-ask 41.4 s; 3rd distinct AP 47.5 s → root incident; 3rd AP kick 77.5 s.
- Expected output: 1 root incident, `blast_radius=site`, 26 APs, 8 channels, 8 sensors, 63 child devices, control "NET-T 31/31 M3".

## F2 retry loop (SESS-01, child of F1)
- (m) 8–14 attempts per device (median 10).
- (m) Kick → next attempt median: 28 s (kicks in min 0–5), 94 s (5–10), 151 s (10–15), 180 s (15–20), 222 s (20–25), 206 s (25–30).

## F3 fast reject / exclusion (SESS-02, child of F1)
- ★ 18 laptops (L-01, 02, 04–12, 14, 15, 18–22), ★ 1,477 reason-2 frames, ★ first at 402 s.
- ★ each had 3–5 reason-23 kicks before its switch and ★ 0 after.
- (m) Onset one laptop per ~15 s from 402 s to 641 s (t_rel). Deauth variant (L-01…L-12) repeats every 11–15 s; disassoc variant (L-14…L-22) every ~26 s. Rejoin → first reason-2 median 8 s.
- (m) Reason-2 frames carry the sending AP's own increasing management sequence numbers.

## F4 probe storm + missing ACKs (DISC-03 + RF-01, child of F1)
- ★ 173,964 probe responses (mean 96.5/s), ★ peak 13,015 in one minute (minute 3), ★ 31.3% retried (30–32% every minute (m)).
- ★ 6,024 probe requests heard. ★ Retries not on probe responses: 60 of 54,544.
- (m) Probe responses by destination: laptops 90,721, phones 80,194, IoT 3,049; 99 destinations.

## F5 missing networks (DISC-01, DISC-02)
- The 8 devices homed on APs without NET-C (L-03, L-13, L-16, L-17, H-08, H-11, H-12, H-28) never associate; each appears in 2,038–3,127 probe frames (m).

## F6–F9
- F6 beacon overhead (RF-03/RF-04): 10.3–18.6% airtime per channel at 1 Mbit/s, 1.7–3.0% at 6 Mbit/s (computed on 50 s; beacon mix unchanged over 30 min).
- F7 visibility (SENS-05): probe responses : requests ≈ 29 : 1.
- F8 leave burst (SESS-08): ★ 16 client reason-3 deauths, ★ 15 within the first 9 s; the 16th is I-03 at 742 s (m).
- F9 NET-T healthy: ★ 24 IoT devices join; ★ 31 handshakes reach M3 (M1→M3 0.3–2.5 ms (m)); ★ 1 join with M1 but no M3 (I-18 on AP30, S2, t=189.5 s) followed by AP Block-Ack setup → KEY-06 only; ★ 4 IoT devices heard sending data; ★ 0 reason 14/15/16; ★ 0 non-zero status codes.

## Negative expectations (false-positive guards)
- No AUTH-*/ASSOC-* rejects, no KEY-01..05, no ROAM-*, no SEC-01 flood, no DISC-06 channel change, no SENS-01 deaf sensor.
- The NET-C failure must not surface as 63 or 654 top-level incidents.
