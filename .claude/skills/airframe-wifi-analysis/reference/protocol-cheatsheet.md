# 802.11 / 802.1X cheat sheet for header-only analysis

## Normal join sequence

| # | Frame | Sender | Notes |
|---|---|---|---|
| 1 | Probe Request / Response | client / AP | optional; clients also scan while connected |
| 2 | Authentication seq 1 / seq 2 | client / AP | open system on WPA2; SAE (algo 3) on WPA3 |
| 3 | (Re)Association Request / Response | client / AP | response `status` 0 = accepted |
| 4 | EAP (802.1X networks only) | AP ⇄ client | Request/Identity → Response/Identity → method rounds (PEAP/TLS/TTLS…) → Success(3) or Failure(4) |
| 5 | EAPOL-Key M1, M2, M3, M4 | AP, client, AP, client | 4-way handshake |
| 6 | Protected data | both | payload invisible; only that it flows |

PSK networks skip step 4. On 802.1X networks, EAP Identity followed by *no method round* means the authenticator never got an answer from the authentication server (or never forwarded the identity).

## EAPOL-Key message from flags

| Msg | key_ack | has_key_mic | install | secure |
|---|---|---|---|---|
| M1 | 1 | 0 | 0 | 0 |
| M2 | 0 | 1 | 0 | 0 |
| M3 | 1 | 1 | 1 | 1 (WPA2) |
| M4 | 0 | 1 | 0 | 1 |

Group-key handshake (G1/G2) looks like M3/M4 without install; distinguish by replay counter and timing after connection.

## EAP codes
1 Request · 2 Response · 3 Success · 4 Failure. EAP type 1 = Identity, 13 = TLS, 21 = TTLS, 25 = PEAP, 254 = expanded.

## Status codes (auth / assoc response)

| Code | Meaning | Typical plant cause |
|---|---|---|
| 0 | Success | |
| 1 | Unspecified failure | AP policy, controller issue |
| 12 | Denied, other reason | ACL / MAC filter |
| 13 | Auth algorithm not supported | WPA3/WPA2 mismatch |
| 17 | AP cannot support more stations | shift-start crowding |
| 30 | Try again later (PMF comeback) | PMF SA query in progress |
| 31 | Robust management frame policy violation | legacy device on PMF-required network |
| 53 | Invalid PMKID | stale cached key during roam |

## Reason codes (deauth / disassoc)

| Code | Meaning | Usually sent by | Incident? |
|---|---|---|---|
| 1 | Unspecified | either | context |
| 2 | Previous authentication no longer valid | AP | 4-way/PSK failure, or (as in this data) repeated fast-reject of an excluded client |
| 3 | Station leaving | client | normal alone; loop if repeated |
| 4 | Inactivity | AP | idle timeout, usually fine |
| 5 | AP cannot handle all stations | AP | capacity |
| 6/7 | Class 2/3 frame from non-auth/non-assoc STA | AP | state mismatch, roam race |
| 8 | Station leaving BSS (disassoc) | client | normal roam |
| 14 | MIC failure | AP | security issue |
| 15 | 4-way handshake timeout | AP | wrong PSK, weak uplink, driver |
| 16 | Group key handshake timeout | AP | power-save clients |
| 23 | IEEE 802.1X authentication failed | AP | RADIUS/AAA, certificates, credentials |
| 34 | Poor channel conditions / excessive retries | AP | RF |

## Timing signatures worth recognising
- Beacon interval: 100 TU = 102.4 ms. Gaps of ~205 / ~307 ms = 1 / 2 missed beacons.
- EAP retransmit timers on controllers are commonly 5–30 s; an exact, repeating re-ask interval (here 30.0 s) is a supplicant/authenticator timer, not random loss.
- 802.1X hold/kick after repeated timeouts (here 60 s, reason 23).
- A roam: leave (reason 3/8 or none) and reassoc to another BSSID within ~50 ms–1 s; FT roams use Authentication algo 2.

## Airtime quick maths
Frame airtime ≈ preamble + bytes × 8 / rate. OFDM preamble ≈ 20 µs; DSSS long preamble 192 µs (2.4 GHz only). A 245-byte beacon: ~2 ms at 1 Mbit/s, ~0.35 ms at 6 Mbit/s. Beacon share per channel = Σ over BSSIDs (≈9.8 beacons/s × airtime). Each extra SSID per radio adds one more beacon stream.

## Visibility asymmetry
Sensors are usually closer to ceiling APs (higher power, better antennas) than to clients. Expect to hear AP frames reliably and client frames partially. Build every verdict from AP-side evidence first; use client frames as confirmation.
