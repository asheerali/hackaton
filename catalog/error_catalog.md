# Airframe error catalog v1.0.0

79 entries in 13 categories. Codes verified against Wireshark 4.6.9 value_strings (tshark -G values), which follow IEEE 802.11-2020/802.11be and RFC 3748.

`seen`: yes = found in the provided captures (evidence given), no = checked and not present, n/a = not assessable yet.

## DISC: Discovery and beacons

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| DISC-01 | Network not broadcast on an AP radio | An access point advertises one of the site's networks but not the other, so devices that need it cannot find it there. | medium | network |  | yes | NET-C missing on AP03, AP13, AP16, AP17; NET-T missing on AP06, AP13, AP28 for all 30 min; the 8 NET-C devices homed on those APs never join. |
| DISC-02 | Access point silent | An access point that should exist is not heard at all. | high | network |  | yes | AP13 never heard in 30 min on the 8 monitored channels (could be on an unmonitored channel). |
| DISC-03 | Probe storm | Devices search for networks far more than normal, flooding the air with questions and answers. | high | network |  | yes | 173,964 probe responses in 30 min, peak 13,015/min (217/s) in minute 3, falling as failing clients back off. |
| DISC-04 | Probe unanswered | Devices ask for a network and no access point answers. | medium | network |  | n/a |  |
| DISC-05 | Beacon loss | The access point's heartbeat goes missing more than normal. | low | network |  | no | Loss 1.7-2.3% on all 53 BSSIDs, max gap 0.41 s: below threshold, not an incident. |
| DISC-06 | Channel change / DFS event | An access point jumps to another channel, briefly disconnecting its devices. | medium | network |  | no | 0 CSA elements, every BSSID stays on one channel. |
| DISC-07 | Beacon configuration drift | An access point changes what it advertises (security, rates, capabilities) without a planned change. | low | network |  | n/a | Not assessed: converter does not keep full element hash yet. |
| DISC-08 | Too many networks per channel | Too many networks share one radio lane, so their adverts crowd the air. | low | network |  | yes | 5-9 BSSIDs per channel; 9 on channels 36 and 40. |
| DISC-09 | Passpoint / ANQP query failure | A device asking the network for service information (Hotspot 2.0) got no or a failed answer. | low | network | S59, S60, S61, S62, S63, S64 | no |  |

## AUTH: 802.11 authentication (open, SAE, FT)

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| AUTH-01 | 802.11 authentication rejected | The access point refuses the very first 'may I talk to you' step. | high | network | S1, S13, S14, S15, S16 | no | All 685 authentication responses status 0. |
| AUTH-02 | 802.11 authentication timeout | A device asks to talk and never gets an answer. | medium | network |  | no |  |
| AUTH-03 | WPA3-SAE failure | Password-based WPA3 login fails. | high | network | S76, S77, S123, S126 | no |  |
| AUTH-04 | Fast-transition (802.11r) authentication failure | A fast roam fails and the device has to do a full login. | medium | network | S28, S52, S53, S54, S55 | no |  |
| AUTH-05 | Authentication flood | Many authentication attempts at once, overloading an access point. | medium | security |  | no |  |
| AUTH-06 | FILS authentication failure | Fast initial link setup (FILS) login failed. | medium | identity/AAA | S112, S113 | no |  |

## ASSOC: Association and reassociation

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| ASSOC-01 | Association rejected: AP full / capacity | The access point says it cannot take more devices. | high | network | S17, S33, S93 | no |  |
| ASSOC-02 | Association rejected: capability or rate mismatch | The device does not support something the network requires. | medium | network | S10, S18, S19, S22, S23, S24 | no |  |
| ASSOC-03 | Association rejected: PMF / temporary | The network requires protected management frames or asks the device to come back later. | medium | network | S30, S31 | no |  |
| ASSOC-04 | Association rejected: security (RSN) mismatch | The device and network disagree on the security settings. | high | network | S40, S41, S42, S43, S44, S45 | no |  |
| ASSOC-05 | Association refused: policy or external reason | The access point refuses for a reason outside the Wi-Fi standard (policy, ACL, controller). | medium | network | S1, S12, S92, S125 | no |  |
| ASSOC-06 | Reassociation denied | A device moving between access points is refused. | medium | network | S11 | no |  |
| ASSOC-07 | Association timeout | A device asks to join and gets no answer. | medium | network |  | no |  |
| ASSOC-08 | QoS / traffic-stream request refused | A device's request for guaranteed bandwidth (voice/video stream) or a scheduled service was refused. | low | network | S2, S3, S6, S7, S32, S37 | no |  |
| ASSOC-09 | Wi-Fi 7 multi-link / priority-access refused | A newer Wi-Fi 7 device could not join or use a link on a multi-link access point. | medium | network | S130, S131, S132, S139, S140 | no |  |
| ASSOC-10 | Other advanced-feature refusal | A request for an optional feature (power save scheduling, fast session transfer, spectrum/energy features) was refused. | low | network | S5, S73, S74, S75, S78, S79 | no |  |

## EAP: 802.1X / EAP (enterprise login)

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| EAP-01 | 802.1X stall after EAP Identity | The badge check never starts: the access point asks 'who are you?' and nothing happens after that. | critical | identity/AAA |  | yes | 654 NET-C join attempts by 63 devices on 26 APs, 0 EAP method rounds, 0 Success/Failure, 0 M1; re-ask median 30.0 s; 12 devices seen answering Identity. |
| EAP-02 | 802.1X stall mid-method | The badge check starts but stops half way. | high | identity/AAA |  | no |  |
| EAP-03 | EAP Failure | The badge server explicitly says no. | high | identity/AAA |  | no | 0 EAP Failure frames. |
| EAP-04 | Kicked out: 802.1X authentication failed (reason 23) | The access point throws the device out because the badge check failed or timed out. | high | identity/AAA | R23 | yes | 506 reason-23 deauths; 488 of 489 measured exactly 60.0 s after association. |
| EAP-05 | Client does not answer EAP Identity | The device never replies to 'who are you?'. | high | device |  | n/a | 51 NET-C devices never heard answering, but 0 of their own join frames are heard either (vs ~48 each for the 12 that are heard answering): a visibility gap, not evidence. |
| EAP-06 | Slow 802.1X | Login works but takes too long, delaying the device every time it connects. | medium | identity/AAA |  | no |  |
| EAP-07 | EAPOL-Start storm | Devices keep restarting the badge check. | medium | device |  | no |  |
| EAP-08 | EAP method mismatch (NAK) | Device and server cannot agree on the badge-check method. | medium | identity/AAA |  | no |  |

## KEY: 4-way and group-key handshakes

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| KEY-01 | 4-way handshake: M2 never arrives (wrong key suspected) | The access point starts handing out the locker key but the device never answers correctly. | high | device | R15 | no | All 32 M1s to IoT are single; 31 followed by M3 in 0.3-2.5 ms. |
| KEY-02 | 4-way handshake: M4 missing / keys not installed | The device got the key but never confirmed it. | high | device | R15 | no |  |
| KEY-03 | MIC failure | The integrity check fails, often a wrong key or tampering. | high | security | R14 | no |  |
| KEY-04 | Group key handshake timeout | Devices miss the shared broadcast key update and drop. | medium | device | R16 | no |  |
| KEY-05 | Security element mismatch in handshake | Security details differ between advert and handshake (possible downgrade). | high | security | R17, R18, R19, R20, R21, R22 | no |  |
| KEY-06 | Handshake step not observed (visibility gap) | A handshake message was not captured, but later frames prove the step happened; not a failure. | info | none |  | yes | 1 IoT join: M1 then Block-Ack setup from AP 60 ms later, no deauth; M3 simply not captured. |

## SESS: Disconnects and session stability

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| SESS-01 | Join-fail-kick loop | A device keeps trying to connect, fails, is thrown out, waits and tries again, over and over. | high | network |  | yes | 63 NET-C devices, 654 cycles; backoff grows from ~28 s (first 5 min) to ~200 s (after 20 min). |
| SESS-02 | Fast reject / client exclusion (reason 2 repeated) | After several failures the network starts throwing the device out within seconds of every attempt, and keeps repeating it. | high | network | R2 | yes | 18 laptops (on 18 APs) switch after 3-5 reason-23 kicks, from 402 s to 641 s; 1,477 reason-2 frames at ~11-15 s (deauth) or ~26 s (disassoc) intervals; 0 reason-23 afterwards. |
| SESS-03 | Idle / inactivity disconnect | The network drops a device it thinks is idle. | low | network | R4 | no |  |
| SESS-04 | Disconnected because AP is full | The access point drops devices because it is overloaded. | high | network | R5, R33 | no |  |
| SESS-05 | State mismatch frames (class 2/3) | The device and access point disagree about whether the device is connected. | medium | network | R6, R7, R9 | no |  |
| SESS-06 | Steered away (BSS transition) | The network pushes the device to another access point. | low | network | R12 | no |  |
| SESS-07 | Disconnected for poor radio conditions | The link got too bad and the network dropped the device. | medium | network | R34, R71 | no |  |
| SESS-08 | Mass leave burst | Many devices disconnect within seconds, pointing to a shared trigger. | medium | network | R3, R8 | yes | 15 devices (6 laptops, 5 phones, 4 IoT) sent reason 3 within 9 s at start. |
| SESS-09 | Normal leave (not an incident) | A device says goodbye on its own: normal behaviour. | info | none | R3, R8, R36 | yes | 16 reason-3 frames from clients. |
| SESS-10 | Unspecified disconnect | Disconnected with no reason given. | low | network | R1 | no |  |
| SESS-11 | QoS / session-policy disconnect | Disconnected for a QoS, service-provider or access-policy reason. | low | network | R10, R11, R13, R25, R26, R27 | no |  |
| SESS-12 | Mesh-link events | Mesh backhaul peering problems (only on mesh deployments). | medium | network | R52, R53, R54, R55, R56, R57 | no |  |

## ROAM: Roaming

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| ROAM-01 | Normal roam (not an incident) | A device moves to a better access point: normal. | info | none |  | no | No device changed AP in 30 min. |
| ROAM-02 | Slow roam | Moving between access points takes too long and breaks connections. | medium | network |  | no |  |
| ROAM-03 | Sticky client | A device stays on a far, weak access point instead of moving to a closer one. | medium | device |  | no |  |
| ROAM-04 | Ping-pong roaming | A device keeps bouncing between two access points. | medium | network |  | no |  |

## RF: RF, airtime and congestion

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| RF-01 | Missing acknowledgements / high retries | Many messages are not acknowledged and have to be sent again. | medium | network |  | yes | 31.3% of probe responses retried (54,484); 60 other retries in 1.1 M frames. |
| RF-02 | Channel congestion | The radio lane is too busy. | high | network |  | no | Airtime estimate low except beacon overhead (see RF-03). |
| RF-03 | Beacon overhead | Access point adverts use a big share of the air before any useful work. | medium | network |  | yes | 10-19% per channel at the stated 1 Mbit/s; 1.7-3% if 6 Mbit/s. |
| RF-04 | Basic rate too low / legacy rate | Management frames are sent at a very slow rate, wasting air. | low | network |  | yes | All 914,057 beacons at 1 Mbit/s on 5 GHz. |
| RF-05 | Weak client signal | Devices are too far from the access point. | low | network |  | n/a | Clients heard at -80..-89 dBm but sensors are not co-located with APs, so this is not a valid client-signal measure. |
| RF-06 | Co-channel overlap | Neighbouring access points share the same lane and slow each other down. | low | network |  | n/a | Up to 5 APs on one channel; physical distances unknown (no map). |
| RF-07 | High noise floor | Background radio noise makes everything slower. | medium | network |  | no |  |

## CLIENT: Client behaviour and power save

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| CLIENT-01 | Power-save misbehaviour | Sleepy devices miss messages and drop. | low | device |  | no |  |
| CLIENT-02 | Null-data keepalive storm | A device sends too many 'still here' frames. | low | device |  | no | QoS Null frames present at low rate from IoT. |

## SEC: Security signatures (passive detection only)

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| SEC-01 | Deauthentication flood / spoofed deauth | Someone may be forcing devices off the network. | high | security |  | no | Reason-2 deauths carry the AP's own increasing sequence numbers at 10-30 s per client: sent by the AP itself (SESS-02), not a spoofed flood. |
| SEC-02 | Rogue / evil-twin AP | An unknown access point advertises the company network. | high | security |  | no | All 53 BSSIDs share one vendor OUI. |
| SEC-03 | Protected management frames not enforced | Management frames are not protected, making spoofed disconnects possible. | low | security |  | n/a | Not assessed: converter does not extract RSN capability bits yet. |

## INFRA: Infrastructure-level causes inferred from the air

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| INFRA-01 | Central authentication service outage | The same login failure happens on many access points at once, so the cause is a shared service behind them. | critical | identity/AAA |  | yes | EAP-01 on 26 APs, 8 channels, 8 sensors; NET-T on same radios: 31 handshakes, 0 failures. Streaming detector would fire at 47.5 s. |
| INFRA-02 | AP reboot | An access point restarted. | medium | network |  | no |  |
| INFRA-03 | Controller-wide behaviour change | Many APs change behaviour at the same moment (config push). | medium | network |  | no | SESS-02 onset is a rolling 15 s-per-client wave (402-641 s), not simultaneous. |

## SENS: Sensor and data quality

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| SENS-01 | Sensor deaf / silent | A sensor stops hearing anything. | high | platform |  | no | Longest beacon gap 0.41 s on any sensor. |
| SENS-02 | Sensor clock offset | Sensors' clocks disagree, so matching events across sensors needs tolerance. | low | platform |  | yes | Start epochs differ by up to 2.3 s; joins sit on an exact 2 s grid in per-sensor time only. Cannot tell offset from staggered start (no shared BSSID). |
| SENS-03 | Partial capture window | The analysed data covers only part of the recording. | info | platform |  | yes | Old JSON: 50 s of 1,802 s (2.8%). |
| SENS-04 | Physically impossible radio values | The capture contains values real radios cannot produce. | info | platform |  | yes | 1 Mbit/s beacons on 5 GHz; RSSI constant on 53/53 BSSIDs. |
| SENS-05 | Uplink not heard (visibility asymmetry) | Sensors hear access points far better than devices, so many device frames are missing. | info | platform |  | yes | 173,964 probe responses vs 6,024 probe requests; M2/M4 heard for 4 of 24 IoT devices. |
| SENS-06 | Truncated frames | Frames are cut to headers (by design); lengths must use the on-air size. | info | platform |  | yes | Data frames truncated (e.g. 49 of 137 bytes). |

## OTHER: Unclassified: goes to the discovery agent

| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |
|---|---|---|---|---|---|---|---|
| OTHER-CODE | Unknown or unmapped code | A status/reason/EAP code arrived that the catalog does not map (reserved or vendor-specific). | unknown | discovery-agent |  | no |  |
| OTHER-SEQ | Unexpected sequence | Frames arrived in an order no known pattern explains. | unknown | discovery-agent |  | no |  |
| OTHER-STAT | Statistical anomaly | A metric moved far from normal with no known explanation. | unknown | discovery-agent |  | no |  |

## Detection details

### DISC-01 Network not broadcast on an AP radio
- **Looks like:** BSSID for SSID X heard from an AP whose other BSSIDs are heard on the same channel, but no beacon for SSID X from it.
- **Rule:** For each AP (grouped by BSSID base), expected SSID set minus heard SSID set, over >= 60 s with the sensor alive.
- **Not to confuse with:** Network intentionally not deployed on that AP (needs config/inventory to rule out).
- **Likely causes:** WLAN disabled on radio or AP group; profile push failed; AP in wrong group
- **Confirm with:** controller WLAN-to-AP-group mapping
- **Standard fix:** re-apply WLAN profile to AP group; fix AP group membership

### DISC-02 Access point silent
- **Looks like:** No beacon from an expected AP on any monitored channel.
- **Rule:** Expected AP list (inventory, or gap in AP numbering) minus APs heard, for >= 60 s.
- **Not to confuse with:** AP on a channel no sensor monitors.
- **Likely causes:** AP down or rebooting; PoE/switch port failure; AP moved to an unmonitored channel
- **Confirm with:** switch port / PoE status; controller AP up/down list
- **Standard fix:** restore power/uplink; replace AP

### DISC-03 Probe storm
- **Looks like:** Probe requests/responses per client or per channel far above baseline; often many clients at once.
- **Rule:** Probe responses per client > 1/s sustained 60 s, or area-wide probe traffic > 3x rolling baseline.
- **Not to confuse with:** A few background scans per client per minute; burst during a roam.
- **Likely causes:** clients failing to connect keep scanning; aggressive client roaming settings; AP reboot wave
- **Confirm with:** check which clients are failing (link to EAP/KEY incidents)
- **Standard fix:** fix the underlying join failure; tune client scan/roam settings

### DISC-04 Probe unanswered
- **Looks like:** Directed probe requests for SSID X with no probe response for X within 100 ms on that channel.
- **Rule:** Unanswered directed probes per SSID per channel > 50% over 60 s.
- **Not to confuse with:** Client probing on a channel where the network is simply not deployed.
- **Likely causes:** SSID not configured on local APs; coverage hole
- **Confirm with:** RF plan vs client location
- **Standard fix:** deploy SSID / fix coverage

### DISC-05 Beacon loss
- **Looks like:** Beacon gaps of 2x..N x beacon interval for a BSSID while other BSSIDs are heard by the same sensor.
- **Rule:** Loss > 10% for a BSSID over 60 s, sensor alive.
- **Not to confuse with:** ~1-3% loss at a distant sensor is normal.
- **Likely causes:** interference; AP overloaded; sensor far away
- **Confirm with:** AP CPU/channel utilisation
- **Standard fix:** check interference / AP health

### DISC-06 Channel change / DFS event
- **Looks like:** Channel Switch Announcement element in beacons; BSSID disappears from one sensor and appears on another; mass deauth.
- **Rule:** Any CSA element, or BSSID first-heard on a new channel after vanishing.
- **Not to confuse with:** Planned channel change in a maintenance window.
- **Likely causes:** radar detection (DFS); auto channel planning
- **Confirm with:** controller RF event log
- **Standard fix:** pin non-DFS channels for critical areas

### DISC-07 Beacon configuration drift
- **Looks like:** Hash of beacon elements for a BSSID changes over time.
- **Rule:** Element hash change for a BSSID outside change window.
- **Not to confuse with:** Planned configuration push.
- **Likely causes:** config push; firmware change
- **Confirm with:** controller audit log
- **Standard fix:** roll back or confirm change

### DISC-08 Too many networks per channel
- **Looks like:** Count of BSSIDs beaconing on one channel.
- **Rule:** > 6 BSSIDs per channel heard by one sensor.
- **Likely causes:** too many SSIDs per AP; too many APs on the same channel
- **Standard fix:** reduce SSIDs; re-plan channels

### AUTH-01 802.11 authentication rejected
- **Looks like:** Authentication seq 2 with status != 0.
- **Rule:** Any non-zero status on Authentication response; group by status.
- **Not to confuse with:** Single reject followed by success on another AP.
- **Likely causes:** algorithm mismatch; SAE/password problems; ACL
- **Confirm with:** controller client log
- **Standard fix:** fix client/AP security profile

### AUTH-02 802.11 authentication timeout
- **Looks like:** Authentication seq 1 from client, no seq 2 from AP within 100 ms (repeated).
- **Rule:** 3+ unanswered auth requests from one client in 10 s, AP otherwise alive.
- **Not to confuse with:** Sensor did not hear the AP's answer (check visibility).
- **Likely causes:** AP overloaded; client on wrong channel/BSSID
- **Standard fix:** check AP load

### AUTH-03 WPA3-SAE failure
- **Looks like:** SAE (auth alg 3) commit/confirm with non-zero status or repeated commits.
- **Rule:** Status 76/77/123/126 or >= 3 SAE commit rounds without confirm.
- **Not to confuse with:** Anti-clogging token exchange (status 76) once is normal under load.
- **Likely causes:** wrong password; unsupported group; password identifier unknown
- **Confirm with:** client and AP SAE settings
- **Standard fix:** fix passphrase / SAE groups

### AUTH-04 Fast-transition (802.11r) authentication failure
- **Looks like:** Auth alg 2 (FT) with non-zero status, or reassoc with FT elements rejected.
- **Rule:** Status 28/52/53/54/55 on FT auth/reassoc.
- **Likely causes:** R0KH unreachable; stale key cache; mobility domain mismatch
- **Confirm with:** controller FT/mobility config
- **Standard fix:** fix mobility domain / key distribution

### AUTH-05 Authentication flood
- **Looks like:** Auth requests per AP far above baseline, many clients.
- **Rule:** > 20 auth requests/s on one AP for 10 s.
- **Not to confuse with:** Shift start: many devices join at once (short burst).
- **Likely causes:** reboot wave; attack or misbehaving client
- **Standard fix:** rate-limit / investigate source

### ASSOC-01 Association rejected: AP full / capacity
- **Looks like:** Association response status 17 (or 33, 93).
- **Rule:** Any status 17/33/93; count per AP.
- **Likely causes:** too many clients per radio at shift start; client limit too low
- **Confirm with:** AP client counts
- **Standard fix:** add capacity / raise limit / load-balance

### ASSOC-02 Association rejected: capability or rate mismatch
- **Looks like:** Status 10, 18, 19, 22-25, 27, 35, 51, 104, 119, 135.
- **Rule:** Any such status.
- **Likely causes:** legacy device on HT/VHT-only network; basic rates set too high for device
- **Confirm with:** device spec vs WLAN rate/capability profile
- **Standard fix:** adjust WLAN profile or replace device

### ASSOC-03 Association rejected: PMF / temporary
- **Looks like:** Status 30 (try later) or 31 (robust management frame policy violation).
- **Rule:** Status 31 any time; status 30 repeated without later success.
- **Not to confuse with:** One status 30 followed by success (PMF SA query) is normal.
- **Likely causes:** legacy device on PMF-required WLAN; stale association
- **Confirm with:** WLAN PMF setting vs device
- **Standard fix:** set PMF optional for that SSID or update device

### ASSOC-04 Association rejected: security (RSN) mismatch
- **Looks like:** Status 40-46, 72.
- **Rule:** Any such status.
- **Likely causes:** cipher/AKM mismatch; WPA2/WPA3 transition misconfig
- **Confirm with:** WLAN security profile vs device
- **Standard fix:** align cipher/AKM

### ASSOC-05 Association refused: policy or external reason
- **Looks like:** Status 1, 12, 92, 125.
- **Rule:** Any such status.
- **Likely causes:** ACL/MAC filter; controller policy; client blocklist
- **Confirm with:** controller client log
- **Standard fix:** fix policy / remove block

### ASSOC-06 Reassociation denied
- **Looks like:** Reassociation response status 11 (or non-zero).
- **Rule:** Any non-zero reassoc status.
- **Likely causes:** roam to AP that lost state; controller mobility issue
- **Standard fix:** check mobility group

### ASSOC-07 Association timeout
- **Looks like:** Assoc request with no response within 100 ms, repeated.
- **Rule:** 3+ unanswered assoc requests in 10 s.
- **Not to confuse with:** Response missed by sensor.
- **Likely causes:** AP overloaded
- **Standard fix:** check AP

### ASSOC-08 QoS / traffic-stream request refused
- **Looks like:** ADDTS/TS/scheduling responses with these statuses (Action frames).
- **Rule:** Any such status; group by AP.
- **Not to confuse with:** Occasional refusals under load.
- **Likely causes:** admission control limits; QoS policy
- **Confirm with:** WMM/admission config
- **Standard fix:** tune admission control

### ASSOC-09 Wi-Fi 7 multi-link / priority-access refused
- **Looks like:** Statuses 130-132, 139, 140.
- **Rule:** Any such status.
- **Likely causes:** MLD config mismatch; EPCS authorisation
- **Confirm with:** AP MLD config
- **Standard fix:** align MLO settings

### ASSOC-10 Other advanced-feature refusal
- **Looks like:** Statuses listed in codes.
- **Rule:** Any such status; informational unless repeated for one client.
- **Likely causes:** feature not supported/allowed
- **Standard fix:** disable feature on client or enable on AP

### DISC-09 Passpoint / ANQP query failure
- **Looks like:** GAS/ANQP responses with these statuses.
- **Rule:** Any such status.
- **Likely causes:** ANQP server unreachable; Passpoint misconfig
- **Standard fix:** fix ANQP/advertisement server

### AUTH-06 FILS authentication failure
- **Looks like:** Auth alg 4-6 with status 112/113.
- **Rule:** Any such status.
- **Likely causes:** unknown authentication server; FILS key problem
- **Confirm with:** AAA config for FILS
- **Standard fix:** fix FILS/AAA config

### EAP-01 802.1X stall after EAP Identity
- **Looks like:** Assoc OK, EAP Request/Identity from AP, optionally Response/Identity from client, then no EAP method request, no Success/Failure, no EAPOL M1; AP re-sends Identity request on a fixed timer.
- **Rule:** No EAP method round within 20 s of Identity; confirm with >= 1 re-ask on a fixed interval.
- **Not to confuse with:** Slow but successful EAP (record as latency).
- **Likely causes:** RADIUS/AAA server down or unreachable; wrong RADIUS shared secret; controller-to-RADIUS firewall/VLAN change; RADIUS overloaded
- **Confirm with:** RADIUS server logs (requests arriving?); controller AAA server status/counters; ping/port test controller -> RADIUS
- **Standard fix:** restore RADIUS reachability; fix shared secret; fail over to secondary RADIUS

### EAP-02 802.1X stall mid-method
- **Looks like:** EAP method rounds (TLS/PEAP) start, then stop without Success/Failure.
- **Rule:** Last EAP frame is a method request/response and nothing follows for 20 s.
- **Not to confuse with:** Large TLS certificate chains take several rounds (slow, not stuck).
- **Likely causes:** certificate problem; MTU/fragmentation of EAP-TLS; RADIUS policy stuck
- **Confirm with:** RADIUS logs for the session
- **Standard fix:** fix certificate chain / fragment size

### EAP-03 EAP Failure
- **Looks like:** EAP code 4 (Failure).
- **Rule:** Any EAP Failure; group by client.
- **Likely causes:** wrong credentials; expired certificate; account disabled; policy mismatch
- **Confirm with:** RADIUS reject reason
- **Standard fix:** fix credentials/cert/policy

### EAP-04 Kicked out: 802.1X authentication failed (reason 23)
- **Looks like:** Deauthentication reason 23 from AP.
- **Rule:** Any reason 23; link to EAP-01/02/03 for cause.
- **Likely causes:** see EAP-01..03
- **Standard fix:** fix the underlying EAP problem

### EAP-05 Client does not answer EAP Identity
- **Looks like:** Repeated EAP Request/Identity with no Response/Identity while client frames are otherwise heard.
- **Rule:** 3+ Identity requests unanswered while the sensor hears that client.
- **Not to confuse with:** Sensor cannot hear that client's uplink (check visibility first).
- **Likely causes:** supplicant not configured for 802.1X; device expects PSK; driver bug
- **Confirm with:** device Wi-Fi profile
- **Standard fix:** deploy correct Wi-Fi profile to device

### EAP-06 Slow 802.1X
- **Looks like:** Identity -> Success > 2 s.
- **Rule:** Median EAP duration per SSID > 2 s over 10 attempts.
- **Likely causes:** RADIUS latency; remote RADIUS over WAN
- **Confirm with:** RADIUS response times
- **Standard fix:** local RADIUS / caching / PMK caching

### EAP-07 EAPOL-Start storm
- **Looks like:** Many EAPOL-Start frames from clients.
- **Rule:** > 3 EAPOL-Start per client per minute.
- **Likely causes:** supplicant retry loop
- **Standard fix:** fix supplicant config

### EAP-08 EAP method mismatch (NAK)
- **Looks like:** EAP Response type 3 (Legacy Nak).
- **Rule:** Any Nak followed by failure/timeout.
- **Not to confuse with:** One Nak then agreement is normal.
- **Likely causes:** server offers TLS, client wants PEAP (or vice versa)
- **Confirm with:** RADIUS policy
- **Standard fix:** align EAP methods

### KEY-01 4-way handshake: M2 never arrives (wrong key suspected)
- **Looks like:** EAPOL M1 repeated (replay counter increments) with no M3; often ends with reason 15 or 2.
- **Rule:** M1 sent >= 2 times without M3 within 5 s.
- **Not to confuse with:** One M1 retransmit then M3.
- **Likely causes:** wrong PSK after key rotation; weak uplink; client driver
- **Confirm with:** PSK on device vs controller
- **Standard fix:** update PSK on device

### KEY-02 4-way handshake: M4 missing / keys not installed
- **Looks like:** M3 repeated, no protected data afterwards, reason 15.
- **Rule:** M3 sent >= 2 times without data or M4.
- **Not to confuse with:** M4 not heard by this sensor but data follows.
- **Likely causes:** client power-save; driver bug
- **Standard fix:** driver update

### KEY-03 MIC failure
- **Looks like:** Deauth reason 14, or M2 followed by M1 retransmit (bad MIC).
- **Rule:** Any reason 14.
- **Likely causes:** wrong PSK; TKIP countermeasures
- **Standard fix:** fix key

### KEY-04 Group key handshake timeout
- **Looks like:** Deauth reason 16.
- **Rule:** Any reason 16; cluster by time (GTK rekey interval).
- **Likely causes:** power-save clients sleeping through rekey
- **Standard fix:** lengthen GTK rekey / fix PS

### KEY-05 Security element mismatch in handshake
- **Looks like:** Deauth reason 17-22, 24.
- **Rule:** Any such reason.
- **Likely causes:** misconfig; downgrade attack
- **Standard fix:** align RSN config

### KEY-06 Handshake step not observed (visibility gap)
- **Looks like:** M1 seen, M3 not seen, but AP continues the association (e.g. Block-Ack setup) and no failure reason follows.
- **Rule:** Emit as info only; never as an incident.
- **Likely causes:** sensor missed the frame
- **Standard fix:** none

### SESS-01 Join-fail-kick loop
- **Looks like:** >= 3 cycles of association -> failure/deauth for one client within 10 min.
- **Rule:** Count cycles per client; one incident per client, linked to cause.
- **Not to confuse with:** A single deauth during a roam.
- **Likely causes:** any persistent join failure (EAP-01, KEY-01, ...)
- **Standard fix:** fix the linked root cause

### SESS-02 Fast reject / client exclusion (reason 2 repeated)
- **Looks like:** Repeated deauth or disassoc reason 2 from AP to one client every ~10-30 s; each rejoin rejected within seconds; no more reason 23.
- **Rule:** >= 3 reason-2 deauth/disassoc to one client within 2 min.
- **Not to confuse with:** One reason-2 after an AP-side state reset.
- **Likely causes:** controller client-exclusion / block-list after repeated 802.1X failures; AP lost session state
- **Confirm with:** controller excluded-client list and its timer
- **Standard fix:** clear exclusion after fixing root cause; review exclusion policy

### SESS-03 Idle / inactivity disconnect
- **Looks like:** Deauth/disassoc reason 4.
- **Rule:** Many reason 4 on devices that are expected to stay online.
- **Not to confuse with:** Idle laptops overnight.
- **Likely causes:** idle timeout too short for IoT
- **Standard fix:** raise idle timeout for device class

### SESS-04 Disconnected because AP is full
- **Looks like:** Reason 5 or 33.
- **Rule:** Any.
- **Likely causes:** capacity
- **Standard fix:** add capacity

### SESS-05 State mismatch frames (class 2/3)
- **Looks like:** Deauth reason 6/7/9.
- **Rule:** > 3 per client in 5 min.
- **Not to confuse with:** One after an AP reboot.
- **Likely causes:** AP reboot; roam race; client sleeping through deauth
- **Standard fix:** check AP stability

### SESS-06 Steered away (BSS transition)
- **Looks like:** Reason 12, or BTM action frames.
- **Rule:** Frequent BTM disconnects for the same client.
- **Not to confuse with:** Occasional band/load steering.
- **Likely causes:** band steering too aggressive
- **Standard fix:** tune steering

### SESS-07 Disconnected for poor radio conditions
- **Looks like:** Reason 34 or 71.
- **Rule:** Any.
- **Likely causes:** coverage hole; interference
- **Confirm with:** RF survey
- **Standard fix:** fix coverage

### SESS-08 Mass leave burst
- **Looks like:** >= 8 distinct clients send leave/deauth within 10 s.
- **Rule:** Count distinct clients per 10 s window.
- **Not to confuse with:** End of shift.
- **Likely causes:** controller push; power event; shift change
- **Confirm with:** facility and change calendars
- **Standard fix:** correlate with events

### SESS-09 Normal leave (not an incident)
- **Looks like:** Deauth/disassoc reason 3 or 8 from the client, no repeat.
- **Rule:** Record only; never an incident unless part of SESS-01/08.

### SESS-10 Unspecified disconnect
- **Looks like:** Reason 1.
- **Rule:** Cluster by AP/client.
- **Likely causes:** vendor-specific
- **Confirm with:** controller log

### SESS-11 QoS / session-policy disconnect
- **Looks like:** Reasons 10, 11, 13, 25-32, 35, 37-39, 46-51.
- **Rule:** Any.
- **Likely causes:** policy; QoS admission
- **Confirm with:** controller policy

### SESS-12 Mesh-link events
- **Looks like:** Reasons 52-68.
- **Rule:** Any.
- **Likely causes:** mesh link loss
- **Standard fix:** check mesh backhaul

### ROAM-01 Normal roam (not an incident)
- **Looks like:** Leave on AP A then (re)assoc on AP B within ~1 s.
- **Rule:** Record roam latency only.

### ROAM-02 Slow roam
- **Looks like:** Roam gap > 150 ms (voice) / > 1 s (data).
- **Rule:** Median roam gap per SSID above threshold.
- **Likely causes:** no FT/OKC; full 802.1X on every roam
- **Standard fix:** enable 802.11r/OKC

### ROAM-03 Sticky client
- **Looks like:** RSSI of client at its AP falling, retries rising, while a stronger AP is heard by the same sensor.
- **Rule:** Signal < -75 dBm for 60 s with a >= 8 dB better AP available.
- **Not to confuse with:** Stationary device with a steady weak link.
- **Likely causes:** client roam threshold too low
- **Standard fix:** set min RSSI / enable 11k/v

### ROAM-04 Ping-pong roaming
- **Looks like:** >= 4 roams between the same two APs in 5 min.
- **Rule:** Count A<->B transitions per client.
- **Likely causes:** overlapping cells with equal signal
- **Standard fix:** tune TX power / roam thresholds

### RF-01 Missing acknowledgements / high retries
- **Looks like:** Retry flag share per transmitter/frame type; retransmit of same seq.
- **Rule:** Retry share > 20% (>= 30 frames) per transmitter or frame type.
- **Not to confuse with:** Short burst during a roam.
- **Likely causes:** receiver gone (scanning client); interference; hidden node
- **Standard fix:** fix cause (often DISC-03)

### RF-02 Channel congestion
- **Looks like:** High airtime use from frame durations and rates; many BSS per channel.
- **Rule:** Estimated airtime > 50% for 60 s.
- **Likely causes:** too many clients/SSIDs; low data rates
- **Standard fix:** re-plan channels, raise rates

### RF-03 Beacon overhead
- **Looks like:** Sum of beacon airtime per channel.
- **Rule:** > 10% at stated rate.
- **Likely causes:** many SSIDs per AP; low basic rate
- **Standard fix:** fewer SSIDs, higher basic rate

### RF-04 Basic rate too low / legacy rate
- **Looks like:** Beacon/mgmt rate at lowest rate of the band (or invalid for band).
- **Rule:** Any beacon rate < 12 Mbit/s on 5 GHz.
- **Likely causes:** default rate set
- **Confirm with:** WLAN basic rate config
- **Standard fix:** set minimum basic rate 12-24 Mbit/s

### RF-05 Weak client signal
- **Looks like:** Client RSSI at sensor near AP < -80 dBm (needs sensor near AP).
- **Rule:** Per-client RSSI trend.
- **Likely causes:** coverage hole
- **Confirm with:** survey
- **Standard fix:** add AP / move device

### RF-06 Co-channel overlap
- **Looks like:** Several APs on one channel heard at similar strength by one sensor.
- **Rule:** >= 3 APs within 6 dB on one channel.
- **Likely causes:** channel plan
- **Standard fix:** re-plan channels / TX power

### RF-07 High noise floor
- **Looks like:** radiotap noise > -85 dBm sustained.
- **Rule:** Median noise > -85 dBm over 60 s.
- **Likely causes:** non-Wi-Fi interference
- **Confirm with:** spectrum analysis
- **Standard fix:** remove interferer

### CLIENT-01 Power-save misbehaviour
- **Looks like:** PS bit toggling rapidly; group-key timeouts.
- **Rule:** > 10 PS toggles/s per client.
- **Likely causes:** driver
- **Standard fix:** driver update / disable aggressive PS

### CLIENT-02 Null-data keepalive storm
- **Looks like:** Null/QoS-Null frames per client per second.
- **Rule:** > 5/s sustained.
- **Likely causes:** driver
- **Standard fix:** driver update

### SEC-01 Deauthentication flood / spoofed deauth
- **Looks like:** Many deauths (often broadcast) with sequence numbers inconsistent with the AP's own counter.
- **Rule:** > 20 deauth/s or seq jumps vs AP's frames.
- **Not to confuse with:** Legitimate controller mass-deauth during change.
- **Likely causes:** attack; rogue device
- **Confirm with:** WIPS
- **Standard fix:** enable PMF (802.11w); locate source

### SEC-02 Rogue / evil-twin AP
- **Looks like:** Beacon with corporate SSID from a BSSID not in the inventory / other vendor OUI.
- **Rule:** Any unknown BSSID with a corporate SSID.
- **Not to confuse with:** New AP not yet in inventory.
- **Likely causes:** rogue AP
- **Confirm with:** inventory
- **Standard fix:** locate and remove

### SEC-03 Protected management frames not enforced
- **Looks like:** RSN capabilities MFPR=0 on corporate SSID.
- **Rule:** Beacon RSN MFPR bit.
- **Likely causes:** config
- **Standard fix:** require PMF where clients support it

### INFRA-01 Central authentication service outage
- **Looks like:** EAP-01/EAP-03 on >= 3 APs or >= 2 channels within 2 min, while another SSID on the same radios is healthy.
- **Rule:** Root-incident rule over EAP incidents + control comparison.
- **Likely causes:** RADIUS/AAA outage; controller-AAA path failure
- **Confirm with:** RADIUS health; controller AAA status
- **Standard fix:** restore AAA service

### INFRA-02 AP reboot
- **Looks like:** Beacons stop then resume with TSF reset near zero.
- **Rule:** Beacon gap > 5 s then TSF < previous.
- **Likely causes:** power; crash; firmware
- **Confirm with:** AP uptime
- **Standard fix:** check PoE/firmware

### INFRA-03 Controller-wide behaviour change
- **Looks like:** Same new pattern (e.g. new reason code) starts on many APs within a short window.
- **Rule:** New reason/status code on >= 3 APs within 60 s.
- **Likely causes:** config push
- **Confirm with:** change log
- **Standard fix:** review change

### SENS-01 Sensor deaf / silent
- **Looks like:** No beacons from any AP for > 2 s.
- **Rule:** Gap > 2 s in all beacons for a sensor.
- **Likely causes:** sensor down; channel change
- **Confirm with:** sensor heartbeat
- **Standard fix:** restart sensor

### SENS-02 Sensor clock offset
- **Looks like:** Same scripted/periodic event lines up on per-sensor relative time but not on wall-clock time.
- **Rule:** Estimate offset from shared BSSID TSF when available.
- **Likely causes:** no NTP/PTP
- **Standard fix:** sync sensor clocks

### SENS-03 Partial capture window
- **Looks like:** Converted window << capture length.
- **Rule:** Compare window to capture length.
- **Likely causes:** conversion limit
- **Standard fix:** convert full capture

### SENS-04 Physically impossible radio values
- **Looks like:** e.g. 1 Mbit/s on 5 GHz, constant RSSI.
- **Rule:** Rate not valid for band; RSSI variance 0 across > 100 frames.
- **Likely causes:** emulated capture; sensor driver bug
- **Standard fix:** treat airtime maths with care

### SENS-05 Uplink not heard (visibility asymmetry)
- **Looks like:** Ratio of AP-sent to client-sent frames in handshakes.
- **Rule:** Track per-client visibility; lower confidence of client-side verdicts.
- **Likely causes:** sensor placement
- **Standard fix:** place sensors nearer clients

### SENS-06 Truncated frames
- **Looks like:** caplen < frame length.
- **Rule:** Informational.
- **Likely causes:** header-only capture policy

### OTHER-CODE Unknown or unmapped code
- **Looks like:** Code value not in ieee_codes.json or not mapped to an entry.
- **Rule:** Every such frame -> unknown_events.jsonl.

### OTHER-SEQ Unexpected sequence
- **Looks like:** Episode state machine hits an undefined transition.
- **Rule:** Every such transition -> unknown_events.jsonl.

### OTHER-STAT Statistical anomaly
- **Looks like:** Per-metric z-score > 4 vs rolling baseline, no catalog detector fired.
- **Rule:** Every such spike -> unknown_events.jsonl.
