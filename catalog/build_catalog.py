"""Build the Airframe error catalog (Part 3).

Inputs : catalog/ieee_codes.json   (Wireshark value tables = IEEE 802.11 / RFC 3748 codes)
Outputs: catalog/error_catalog.json (machine-readable, used by detectors and the AI agents)
         catalog/error_catalog.md   (human-readable)

Every IEEE reason/status code is mapped to exactly one catalog entry, so any code the pipeline
meets is either a known problem or explicitly OTHER. Anything a detector cannot match goes to
OTHER-* and into out/unknown_events.jsonl for the Part 3 discovery agent.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
CODES = json.loads((HERE / "ieee_codes.json").read_text(encoding="utf-8"))
VERSION = "1.0.0"

CATEGORIES = {
    "DISC": "Discovery and beacons",
    "AUTH": "802.11 authentication (open, SAE, FT)",
    "ASSOC": "Association and reassociation",
    "EAP": "802.1X / EAP (enterprise login)",
    "KEY": "4-way and group-key handshakes",
    "SESS": "Disconnects and session stability",
    "ROAM": "Roaming",
    "RF": "RF, airtime and congestion",
    "CLIENT": "Client behaviour and power save",
    "SEC": "Security signatures (passive detection only)",
    "INFRA": "Infrastructure-level causes inferred from the air",
    "SENS": "Sensor and data quality",
    "OTHER": "Unclassified: goes to the discovery agent",
}

ENTRIES: list[dict] = []


def E(id, name, plain, signature, rule, lookalike="", severity="medium", causes=(), confirm=(), fix=(), owner="network",
      reasons=(), statuses=(), visibility="full", seen=None, evidence=""):
    ENTRIES.append({
        "id": id, "category": id.split("-")[0], "name": name, "plain": plain, "signature": signature,
        "detect": rule, "normal_lookalike": lookalike, "default_severity": severity,
        "likely_causes": list(causes), "confirm_outside_headers": list(confirm), "standard_fix": list(fix),
        "owner": owner, "codes": {"reason": list(reasons), "status": list(statuses)},
        "header_visibility": visibility,
        "dataset": {"seen": seen, "evidence": evidence},
    })


# ---------------- DISC ----------------
E("DISC-01", "Network not broadcast on an AP radio",
  "An access point advertises one of the site's networks but not the other, so devices that need it cannot find it there.",
  "BSSID for SSID X heard from an AP whose other BSSIDs are heard on the same channel, but no beacon for SSID X from it.",
  "For each AP (grouped by BSSID base), expected SSID set minus heard SSID set, over >= 60 s with the sensor alive.",
  "Network intentionally not deployed on that AP (needs config/inventory to rule out).", "medium",
  ["WLAN disabled on radio or AP group", "profile push failed", "AP in wrong group"],
  ["controller WLAN-to-AP-group mapping"], ["re-apply WLAN profile to AP group", "fix AP group membership"],
  "network", seen=True, evidence="NET-C missing on AP03, AP13, AP16, AP17; NET-T missing on AP06, AP13, AP28 for all 30 min; the 8 NET-C devices homed on those APs never join.")
E("DISC-02", "Access point silent",
  "An access point that should exist is not heard at all.",
  "No beacon from an expected AP on any monitored channel.",
  "Expected AP list (inventory, or gap in AP numbering) minus APs heard, for >= 60 s.",
  "AP on a channel no sensor monitors.", "high",
  ["AP down or rebooting", "PoE/switch port failure", "AP moved to an unmonitored channel"],
  ["switch port / PoE status", "controller AP up/down list"], ["restore power/uplink", "replace AP"],
  "network", seen=True, evidence="AP13 never heard in 30 min on the 8 monitored channels (could be on an unmonitored channel).")
E("DISC-03", "Probe storm",
  "Devices search for networks far more than normal, flooding the air with questions and answers.",
  "Probe requests/responses per client or per channel far above baseline; often many clients at once.",
  "Probe responses per client > 1/s sustained 60 s, or area-wide probe traffic > 3x rolling baseline.",
  "A few background scans per client per minute; burst during a roam.", "high",
  ["clients failing to connect keep scanning", "aggressive client roaming settings", "AP reboot wave"],
  ["check which clients are failing (link to EAP/KEY incidents)"], ["fix the underlying join failure", "tune client scan/roam settings"],
  "network", seen=True, evidence="173,964 probe responses in 30 min, peak 13,015/min (217/s) in minute 3, falling as failing clients back off.")
E("DISC-04", "Probe unanswered",
  "Devices ask for a network and no access point answers.",
  "Directed probe requests for SSID X with no probe response for X within 100 ms on that channel.",
  "Unanswered directed probes per SSID per channel > 50% over 60 s.",
  "Client probing on a channel where the network is simply not deployed.", "medium",
  ["SSID not configured on local APs", "coverage hole"], ["RF plan vs client location"], ["deploy SSID / fix coverage"], "network", visibility="partial", seen=None)
E("DISC-05", "Beacon loss",
  "The access point's heartbeat goes missing more than normal.",
  "Beacon gaps of 2x..N x beacon interval for a BSSID while other BSSIDs are heard by the same sensor.",
  "Loss > 10% for a BSSID over 60 s, sensor alive.",
  "~1-3% loss at a distant sensor is normal.", "low",
  ["interference", "AP overloaded", "sensor far away"], ["AP CPU/channel utilisation"], ["check interference / AP health"], "network",
  seen=False, evidence="Loss 1.7-2.3% on all 53 BSSIDs, max gap 0.41 s: below threshold, not an incident.")
E("DISC-06", "Channel change / DFS event",
  "An access point jumps to another channel, briefly disconnecting its devices.",
  "Channel Switch Announcement element in beacons; BSSID disappears from one sensor and appears on another; mass deauth.",
  "Any CSA element, or BSSID first-heard on a new channel after vanishing.",
  "Planned channel change in a maintenance window.", "medium",
  ["radar detection (DFS)", "auto channel planning"], ["controller RF event log"], ["pin non-DFS channels for critical areas"], "network",
  seen=False, evidence="0 CSA elements, every BSSID stays on one channel.")
E("DISC-07", "Beacon configuration drift",
  "An access point changes what it advertises (security, rates, capabilities) without a planned change.",
  "Hash of beacon elements for a BSSID changes over time.", "Element hash change for a BSSID outside change window.",
  "Planned configuration push.", "low", ["config push", "firmware change"], ["controller audit log"], ["roll back or confirm change"], "network",
  visibility="full", seen=None, evidence="Not assessed: converter does not keep full element hash yet.")
E("DISC-08", "Too many networks per channel",
  "Too many networks share one radio lane, so their adverts crowd the air.",
  "Count of BSSIDs beaconing on one channel.", "> 6 BSSIDs per channel heard by one sensor.",
  "", "low", ["too many SSIDs per AP", "too many APs on the same channel"], [], ["reduce SSIDs", "re-plan channels"], "network",
  seen=True, evidence="5-9 BSSIDs per channel; 9 on channels 36 and 40.")

# ---------------- AUTH ----------------
E("AUTH-01", "802.11 authentication rejected",
  "The access point refuses the very first 'may I talk to you' step.",
  "Authentication seq 2 with status != 0.", "Any non-zero status on Authentication response; group by status.",
  "Single reject followed by success on another AP.", "high",
  ["algorithm mismatch", "SAE/password problems", "ACL"], ["controller client log"], ["fix client/AP security profile"], "network",
  statuses=[1, 13, 14, 15, 16], seen=False, evidence="All 685 authentication responses status 0.")
E("AUTH-02", "802.11 authentication timeout",
  "A device asks to talk and never gets an answer.",
  "Authentication seq 1 from client, no seq 2 from AP within 100 ms (repeated).", "3+ unanswered auth requests from one client in 10 s, AP otherwise alive.",
  "Sensor did not hear the AP's answer (check visibility).", "medium", ["AP overloaded", "client on wrong channel/BSSID"], [], ["check AP load"], "network", visibility="partial", seen=False)
E("AUTH-03", "WPA3-SAE failure",
  "Password-based WPA3 login fails.",
  "SAE (auth alg 3) commit/confirm with non-zero status or repeated commits.", "Status 76/77/123/126 or >= 3 SAE commit rounds without confirm.",
  "Anti-clogging token exchange (status 76) once is normal under load.", "high",
  ["wrong password", "unsupported group", "password identifier unknown"], ["client and AP SAE settings"], ["fix passphrase / SAE groups"], "network",
  statuses=[76, 77, 123, 126], seen=False)
E("AUTH-04", "Fast-transition (802.11r) authentication failure",
  "A fast roam fails and the device has to do a full login.",
  "Auth alg 2 (FT) with non-zero status, or reassoc with FT elements rejected.", "Status 28/52/53/54/55 on FT auth/reassoc.",
  "", "medium", ["R0KH unreachable", "stale key cache", "mobility domain mismatch"], ["controller FT/mobility config"], ["fix mobility domain / key distribution"], "network",
  statuses=[28, 52, 53, 54, 55], seen=False)
E("AUTH-05", "Authentication flood",
  "Many authentication attempts at once, overloading an access point.",
  "Auth requests per AP far above baseline, many clients.", "> 20 auth requests/s on one AP for 10 s.",
  "Shift start: many devices join at once (short burst).", "medium", ["reboot wave", "attack or misbehaving client"], [], ["rate-limit / investigate source"], "security", visibility="partial", seen=False)

# ---------------- ASSOC ----------------
E("ASSOC-01", "Association rejected: AP full / capacity",
  "The access point says it cannot take more devices.",
  "Association response status 17 (or 33, 93).", "Any status 17/33/93; count per AP.",
  "", "high", ["too many clients per radio at shift start", "client limit too low"], ["AP client counts"], ["add capacity / raise limit / load-balance"], "network",
  statuses=[17, 33, 93], seen=False)
E("ASSOC-02", "Association rejected: capability or rate mismatch",
  "The device does not support something the network requires.",
  "Status 10, 18, 19, 22-25, 27, 35, 51, 104, 119, 135.", "Any such status.",
  "", "medium", ["legacy device on HT/VHT-only network", "basic rates set too high for device"], ["device spec vs WLAN rate/capability profile"], ["adjust WLAN profile or replace device"], "network",
  statuses=[10, 18, 19, 22, 23, 24, 25, 27, 35, 51, 103, 104, 119, 135], seen=False)
E("ASSOC-03", "Association rejected: PMF / temporary",
  "The network requires protected management frames or asks the device to come back later.",
  "Status 30 (try later) or 31 (robust management frame policy violation).", "Status 31 any time; status 30 repeated without later success.",
  "One status 30 followed by success (PMF SA query) is normal.", "medium", ["legacy device on PMF-required WLAN", "stale association"], ["WLAN PMF setting vs device"], ["set PMF optional for that SSID or update device"], "network",
  statuses=[30, 31], seen=False)
E("ASSOC-04", "Association rejected: security (RSN) mismatch",
  "The device and network disagree on the security settings.",
  "Status 40-46, 72.", "Any such status.",
  "", "high", ["cipher/AKM mismatch", "WPA2/WPA3 transition misconfig"], ["WLAN security profile vs device"], ["align cipher/AKM"], "network",
  statuses=[40, 41, 42, 43, 44, 45, 46, 72], seen=False)
E("ASSOC-05", "Association refused: policy or external reason",
  "The access point refuses for a reason outside the Wi-Fi standard (policy, ACL, controller).",
  "Status 1, 12, 92, 125.", "Any such status.",
  "", "medium", ["ACL/MAC filter", "controller policy", "client blocklist"], ["controller client log"], ["fix policy / remove block"], "network",
  statuses=[1, 12, 92, 125], seen=False)
E("ASSOC-06", "Reassociation denied",
  "A device moving between access points is refused.", "Reassociation response status 11 (or non-zero).", "Any non-zero reassoc status.",
  "", "medium", ["roam to AP that lost state", "controller mobility issue"], [], ["check mobility group"], "network", statuses=[11], seen=False)
E("ASSOC-07", "Association timeout",
  "A device asks to join and gets no answer.",
  "Assoc request with no response within 100 ms, repeated.", "3+ unanswered assoc requests in 10 s.",
  "Response missed by sensor.", "medium", ["AP overloaded"], [], ["check AP"], "network", visibility="partial", seen=False)

E("ASSOC-08", "QoS / traffic-stream request refused",
  "A device's request for guaranteed bandwidth (voice/video stream) or a scheduled service was refused.",
  "ADDTS/TS/scheduling responses with these statuses (Action frames).", "Any such status; group by AP.",
  "Occasional refusals under load.", "low", ["admission control limits", "QoS policy"], ["WMM/admission config"], ["tune admission control"], "network",
  statuses=[2, 3, 6, 7, 32, 37, 38, 39, 47, 49, 50, 56, 57, 58, 80, 81, 83, 84, 97, 98, 100, 101, 102, 116, 117, 118, 128, 129, 133, 134, 141],
  seen=False)
E("ASSOC-09", "Wi-Fi 7 multi-link / priority-access refused",
  "A newer Wi-Fi 7 device could not join or use a link on a multi-link access point.",
  "Statuses 130-132, 139, 140.", "Any such status.", "", "medium", ["MLD config mismatch", "EPCS authorisation"], ["AP MLD config"], ["align MLO settings"], "network",
  statuses=[130, 131, 132, 139, 140], seen=False)
E("ASSOC-10", "Other advanced-feature refusal",
  "A request for an optional feature (power save scheduling, fast session transfer, spectrum/energy features) was refused.",
  "Statuses listed in codes.", "Any such status; informational unless repeated for one client.",
  "", "low", ["feature not supported/allowed"], [], ["disable feature on client or enable on AP"], "network",
  statuses=[5, 73, 74, 75, 78, 79, 82, 85, 86, 87, 88, 89, 94, 96, 99, 105, 106, 107, 108, 109, 110, 111, 121, 122],
  seen=False)
E("DISC-09", "Passpoint / ANQP query failure",
  "A device asking the network for service information (Hotspot 2.0) got no or a failed answer.",
  "GAS/ANQP responses with these statuses.", "Any such status.", "", "low", ["ANQP server unreachable", "Passpoint misconfig"], [], ["fix ANQP/advertisement server"], "network",
  statuses=[59, 60, 61, 62, 63, 64, 65, 67, 68, 95, 120], seen=False)
E("AUTH-06", "FILS authentication failure",
  "Fast initial link setup (FILS) login failed.", "Auth alg 4-6 with status 112/113.", "Any such status.", "", "medium",
  ["unknown authentication server", "FILS key problem"], ["AAA config for FILS"], ["fix FILS/AAA config"], "identity/AAA", statuses=[112, 113], seen=False)

# ---------------- EAP ----------------
E("EAP-01", "802.1X stall after EAP Identity",
  "The badge check never starts: the access point asks 'who are you?' and nothing happens after that.",
  "Assoc OK, EAP Request/Identity from AP, optionally Response/Identity from client, then no EAP method request, no Success/Failure, no EAPOL M1; AP re-sends Identity request on a fixed timer.",
  "No EAP method round within 20 s of Identity; confirm with >= 1 re-ask on a fixed interval.",
  "Slow but successful EAP (record as latency).", "critical",
  ["RADIUS/AAA server down or unreachable", "wrong RADIUS shared secret", "controller-to-RADIUS firewall/VLAN change", "RADIUS overloaded"],
  ["RADIUS server logs (requests arriving?)", "controller AAA server status/counters", "ping/port test controller -> RADIUS"],
  ["restore RADIUS reachability", "fix shared secret", "fail over to secondary RADIUS"], "identity/AAA",
  seen=True, evidence="654 NET-C join attempts by 63 devices on 26 APs, 0 EAP method rounds, 0 Success/Failure, 0 M1; re-ask median 30.0 s; 12 devices seen answering Identity.")
E("EAP-02", "802.1X stall mid-method",
  "The badge check starts but stops half way.",
  "EAP method rounds (TLS/PEAP) start, then stop without Success/Failure.", "Last EAP frame is a method request/response and nothing follows for 20 s.",
  "Large TLS certificate chains take several rounds (slow, not stuck).", "high",
  ["certificate problem", "MTU/fragmentation of EAP-TLS", "RADIUS policy stuck"], ["RADIUS logs for the session"], ["fix certificate chain / fragment size"], "identity/AAA", seen=False)
E("EAP-03", "EAP Failure",
  "The badge server explicitly says no.",
  "EAP code 4 (Failure).", "Any EAP Failure; group by client.",
  "", "high", ["wrong credentials", "expired certificate", "account disabled", "policy mismatch"], ["RADIUS reject reason"], ["fix credentials/cert/policy"], "identity/AAA", seen=False, evidence="0 EAP Failure frames.")
E("EAP-04", "Kicked out: 802.1X authentication failed (reason 23)",
  "The access point throws the device out because the badge check failed or timed out.",
  "Deauthentication reason 23 from AP.", "Any reason 23; link to EAP-01/02/03 for cause.",
  "", "high", ["see EAP-01..03"], [], ["fix the underlying EAP problem"], "identity/AAA",
  reasons=[23], seen=True, evidence="506 reason-23 deauths; 488 of 489 measured exactly 60.0 s after association.")
E("EAP-05", "Client does not answer EAP Identity",
  "The device never replies to 'who are you?'.",
  "Repeated EAP Request/Identity with no Response/Identity while client frames are otherwise heard.",
  "3+ Identity requests unanswered while the sensor hears that client.",
  "Sensor cannot hear that client's uplink (check visibility first).", "high",
  ["supplicant not configured for 802.1X", "device expects PSK", "driver bug"], ["device Wi-Fi profile"], ["deploy correct Wi-Fi profile to device"], "device", visibility="partial",
  seen=None, evidence="51 NET-C devices never heard answering, but 0 of their own join frames are heard either (vs ~48 each for the 12 that are heard answering): a visibility gap, not evidence.")
E("EAP-06", "Slow 802.1X",
  "Login works but takes too long, delaying the device every time it connects.",
  "Identity -> Success > 2 s.", "Median EAP duration per SSID > 2 s over 10 attempts.",
  "", "medium", ["RADIUS latency", "remote RADIUS over WAN"], ["RADIUS response times"], ["local RADIUS / caching / PMK caching"], "identity/AAA", seen=False)
E("EAP-07", "EAPOL-Start storm",
  "Devices keep restarting the badge check.",
  "Many EAPOL-Start frames from clients.", "> 3 EAPOL-Start per client per minute.", "", "medium",
  ["supplicant retry loop"], [], ["fix supplicant config"], "device", seen=False)
E("EAP-08", "EAP method mismatch (NAK)",
  "Device and server cannot agree on the badge-check method.",
  "EAP Response type 3 (Legacy Nak).", "Any Nak followed by failure/timeout.", "One Nak then agreement is normal.", "medium",
  ["server offers TLS, client wants PEAP (or vice versa)"], ["RADIUS policy"], ["align EAP methods"], "identity/AAA", seen=False)

# ---------------- KEY ----------------
E("KEY-01", "4-way handshake: M2 never arrives (wrong key suspected)",
  "The access point starts handing out the locker key but the device never answers correctly.",
  "EAPOL M1 repeated (replay counter increments) with no M3; often ends with reason 15 or 2.",
  "M1 sent >= 2 times without M3 within 5 s.", "One M1 retransmit then M3.", "high",
  ["wrong PSK after key rotation", "weak uplink", "client driver"], ["PSK on device vs controller"], ["update PSK on device"], "device",
  reasons=[15], seen=False, evidence="All 32 M1s to IoT are single; 31 followed by M3 in 0.3-2.5 ms.")
E("KEY-02", "4-way handshake: M4 missing / keys not installed",
  "The device got the key but never confirmed it.",
  "M3 repeated, no protected data afterwards, reason 15.", "M3 sent >= 2 times without data or M4.", "M4 not heard by this sensor but data follows.", "high",
  ["client power-save", "driver bug"], [], ["driver update"], "device", reasons=[15], seen=False)
E("KEY-03", "MIC failure", "The integrity check fails, often a wrong key or tampering.", "Deauth reason 14, or M2 followed by M1 retransmit (bad MIC).",
  "Any reason 14.", "", "high", ["wrong PSK", "TKIP countermeasures"], [], ["fix key"], "security", reasons=[14], seen=False)
E("KEY-04", "Group key handshake timeout", "Devices miss the shared broadcast key update and drop.", "Deauth reason 16.", "Any reason 16; cluster by time (GTK rekey interval).",
  "", "medium", ["power-save clients sleeping through rekey"], [], ["lengthen GTK rekey / fix PS"], "device", reasons=[16], seen=False)
E("KEY-05", "Security element mismatch in handshake", "Security details differ between advert and handshake (possible downgrade).", "Deauth reason 17-22, 24.",
  "Any such reason.", "", "high", ["misconfig", "downgrade attack"], [], ["align RSN config"], "security", reasons=[17, 18, 19, 20, 21, 22, 24], seen=False)
E("KEY-06", "Handshake step not observed (visibility gap)",
  "A handshake message was not captured, but later frames prove the step happened; not a failure.",
  "M1 seen, M3 not seen, but AP continues the association (e.g. Block-Ack setup) and no failure reason follows.",
  "Emit as info only; never as an incident.", "", "info", ["sensor missed the frame"], [], ["none"], "none", seen=True,
  evidence="1 IoT join: M1 then Block-Ack setup from AP 60 ms later, no deauth; M3 simply not captured.")

# ---------------- SESS ----------------
E("SESS-01", "Join-fail-kick loop",
  "A device keeps trying to connect, fails, is thrown out, waits and tries again, over and over.",
  ">= 3 cycles of association -> failure/deauth for one client within 10 min.", "Count cycles per client; one incident per client, linked to cause.",
  "A single deauth during a roam.", "high", ["any persistent join failure (EAP-01, KEY-01, ...)"], [], ["fix the linked root cause"], "network",
  seen=True, evidence="63 NET-C devices, 654 cycles; backoff grows from ~28 s (first 5 min) to ~200 s (after 20 min).")
E("SESS-02", "Fast reject / client exclusion (reason 2 repeated)",
  "After several failures the network starts throwing the device out within seconds of every attempt, and keeps repeating it.",
  "Repeated deauth or disassoc reason 2 from AP to one client every ~10-30 s; each rejoin rejected within seconds; no more reason 23.",
  ">= 3 reason-2 deauth/disassoc to one client within 2 min.",
  "One reason-2 after an AP-side state reset.", "high",
  ["controller client-exclusion / block-list after repeated 802.1X failures", "AP lost session state"],
  ["controller excluded-client list and its timer"], ["clear exclusion after fixing root cause", "review exclusion policy"], "network",
  reasons=[2], seen=True, evidence="18 laptops (on 18 APs) switch after 3-5 reason-23 kicks, from 402 s to 641 s; 1,477 reason-2 frames at ~11-15 s (deauth) or ~26 s (disassoc) intervals; 0 reason-23 afterwards.")
E("SESS-03", "Idle / inactivity disconnect", "The network drops a device it thinks is idle.", "Deauth/disassoc reason 4.",
  "Many reason 4 on devices that are expected to stay online.", "Idle laptops overnight.", "low", ["idle timeout too short for IoT"], [], ["raise idle timeout for device class"], "network", reasons=[4], seen=False)
E("SESS-04", "Disconnected because AP is full", "The access point drops devices because it is overloaded.", "Reason 5 or 33.", "Any.", "", "high",
  ["capacity"], [], ["add capacity"], "network", reasons=[5, 33], seen=False)
E("SESS-05", "State mismatch frames (class 2/3)", "The device and access point disagree about whether the device is connected.",
  "Deauth reason 6/7/9.", "> 3 per client in 5 min.", "One after an AP reboot.", "medium", ["AP reboot", "roam race", "client sleeping through deauth"], [], ["check AP stability"], "network",
  reasons=[6, 7, 9], seen=False)
E("SESS-06", "Steered away (BSS transition)", "The network pushes the device to another access point.", "Reason 12, or BTM action frames.",
  "Frequent BTM disconnects for the same client.", "Occasional band/load steering.", "low", ["band steering too aggressive"], [], ["tune steering"], "network", reasons=[12], seen=False)
E("SESS-07", "Disconnected for poor radio conditions", "The link got too bad and the network dropped the device.", "Reason 34 or 71.", "Any.", "", "medium",
  ["coverage hole", "interference"], ["RF survey"], ["fix coverage"], "network", reasons=[34, 71], seen=False)
E("SESS-08", "Mass leave burst", "Many devices disconnect within seconds, pointing to a shared trigger.",
  ">= 8 distinct clients send leave/deauth within 10 s.", "Count distinct clients per 10 s window.", "End of shift.", "medium",
  ["controller push", "power event", "shift change"], ["facility and change calendars"], ["correlate with events"], "network",
  reasons=[3, 8], seen=True, evidence="15 devices (6 laptops, 5 phones, 4 IoT) sent reason 3 within 9 s at start.")
E("SESS-09", "Normal leave (not an incident)", "A device says goodbye on its own: normal behaviour.", "Deauth/disassoc reason 3 or 8 from the client, no repeat.",
  "Record only; never an incident unless part of SESS-01/08.", "", "info", [], [], [], "none", reasons=[3, 8, 36], seen=True, evidence="16 reason-3 frames from clients.")
E("SESS-10", "Unspecified disconnect", "Disconnected with no reason given.", "Reason 1.", "Cluster by AP/client.", "", "low", ["vendor-specific"], ["controller log"], [], "network", reasons=[1], seen=False)
E("SESS-11", "QoS / session-policy disconnect", "Disconnected for a QoS, service-provider or access-policy reason.",
  "Reasons 10, 11, 13, 25-32, 35, 37-39, 46-51.", "Any.", "", "low", ["policy", "QoS admission"], ["controller policy"], [], "network",
  reasons=[10, 11, 13, 25, 26, 27, 28, 29, 30, 31, 32, 35, 37, 38, 39, 46, 47, 48, 49, 50, 51], seen=False)
E("SESS-12", "Mesh-link events", "Mesh backhaul peering problems (only on mesh deployments).", "Reasons 52-68.", "Any.", "", "medium",
  ["mesh link loss"], [], ["check mesh backhaul"], "network", reasons=list(range(52, 69)), seen=False)

# ---------------- ROAM ----------------
E("ROAM-01", "Normal roam (not an incident)", "A device moves to a better access point: normal.",
  "Leave on AP A then (re)assoc on AP B within ~1 s.", "Record roam latency only.", "", "info", [], [], [], "none", seen=False,
  evidence="No device changed AP in 30 min.")
E("ROAM-02", "Slow roam", "Moving between access points takes too long and breaks connections.", "Roam gap > 150 ms (voice) / > 1 s (data).",
  "Median roam gap per SSID above threshold.", "", "medium", ["no FT/OKC", "full 802.1X on every roam"], [], ["enable 802.11r/OKC"], "network", seen=False)
E("ROAM-03", "Sticky client", "A device stays on a far, weak access point instead of moving to a closer one.",
  "RSSI of client at its AP falling, retries rising, while a stronger AP is heard by the same sensor.", "Signal < -75 dBm for 60 s with a >= 8 dB better AP available.",
  "Stationary device with a steady weak link.", "medium", ["client roam threshold too low"], [], ["set min RSSI / enable 11k/v"], "device", visibility="partial", seen=False)
E("ROAM-04", "Ping-pong roaming", "A device keeps bouncing between two access points.", ">= 4 roams between the same two APs in 5 min.",
  "Count A<->B transitions per client.", "", "medium", ["overlapping cells with equal signal"], [], ["tune TX power / roam thresholds"], "network", seen=False)

# ---------------- RF ----------------
E("RF-01", "Missing acknowledgements / high retries",
  "Many messages are not acknowledged and have to be sent again.",
  "Retry flag share per transmitter/frame type; retransmit of same seq.", "Retry share > 20% (>= 30 frames) per transmitter or frame type.",
  "Short burst during a roam.", "medium", ["receiver gone (scanning client)", "interference", "hidden node"], [], ["fix cause (often DISC-03)"], "network",
  seen=True, evidence="31.3% of probe responses retried (54,484); 60 other retries in 1.1 M frames.")
E("RF-02", "Channel congestion", "The radio lane is too busy.", "High airtime use from frame durations and rates; many BSS per channel.",
  "Estimated airtime > 50% for 60 s.", "", "high", ["too many clients/SSIDs", "low data rates"], [], ["re-plan channels, raise rates"], "network", visibility="partial", seen=False,
  evidence="Airtime estimate low except beacon overhead (see RF-03).")
E("RF-03", "Beacon overhead", "Access point adverts use a big share of the air before any useful work.",
  "Sum of beacon airtime per channel.", "> 10% at stated rate.", "", "medium", ["many SSIDs per AP", "low basic rate"], [], ["fewer SSIDs, higher basic rate"], "network",
  seen=True, evidence="10-19% per channel at the stated 1 Mbit/s; 1.7-3% if 6 Mbit/s.")
E("RF-04", "Basic rate too low / legacy rate", "Management frames are sent at a very slow rate, wasting air.",
  "Beacon/mgmt rate at lowest rate of the band (or invalid for band).", "Any beacon rate < 12 Mbit/s on 5 GHz.",
  "", "low", ["default rate set"], ["WLAN basic rate config"], ["set minimum basic rate 12-24 Mbit/s"], "network", seen=True, evidence="All 914,057 beacons at 1 Mbit/s on 5 GHz.")
E("RF-05", "Weak client signal", "Devices are too far from the access point.", "Client RSSI at sensor near AP < -80 dBm (needs sensor near AP).",
  "Per-client RSSI trend.", "", "low", ["coverage hole"], ["survey"], ["add AP / move device"], "network", visibility="partial", seen=None,
  evidence="Clients heard at -80..-89 dBm but sensors are not co-located with APs, so this is not a valid client-signal measure.")
E("RF-06", "Co-channel overlap", "Neighbouring access points share the same lane and slow each other down.",
  "Several APs on one channel heard at similar strength by one sensor.", ">= 3 APs within 6 dB on one channel.", "", "low",
  ["channel plan"], [], ["re-plan channels / TX power"], "network", seen=None, evidence="Up to 5 APs on one channel; physical distances unknown (no map).")
E("RF-07", "High noise floor", "Background radio noise makes everything slower.", "radiotap noise > -85 dBm sustained.", "Median noise > -85 dBm over 60 s.",
  "", "medium", ["non-Wi-Fi interference"], ["spectrum analysis"], ["remove interferer"], "network", seen=False)

# ---------------- CLIENT ----------------
E("CLIENT-01", "Power-save misbehaviour", "Sleepy devices miss messages and drop.", "PS bit toggling rapidly; group-key timeouts.", "> 10 PS toggles/s per client.",
  "", "low", ["driver"], [], ["driver update / disable aggressive PS"], "device", seen=False)
E("CLIENT-02", "Null-data keepalive storm", "A device sends too many 'still here' frames.", "Null/QoS-Null frames per client per second.", "> 5/s sustained.",
  "", "low", ["driver"], [], ["driver update"], "device", seen=False, evidence="QoS Null frames present at low rate from IoT.")

# ---------------- SEC ----------------
E("SEC-01", "Deauthentication flood / spoofed deauth", "Someone may be forcing devices off the network.",
  "Many deauths (often broadcast) with sequence numbers inconsistent with the AP's own counter.", "> 20 deauth/s or seq jumps vs AP's frames.",
  "Legitimate controller mass-deauth during change.", "high", ["attack", "rogue device"], ["WIPS"], ["enable PMF (802.11w)", "locate source"], "security", seen=False,
  evidence="Reason-2 deauths carry the AP's own increasing sequence numbers at 10-30 s per client: sent by the AP itself (SESS-02), not a spoofed flood.")
E("SEC-02", "Rogue / evil-twin AP", "An unknown access point advertises the company network.",
  "Beacon with corporate SSID from a BSSID not in the inventory / other vendor OUI.", "Any unknown BSSID with a corporate SSID.",
  "New AP not yet in inventory.", "high", ["rogue AP"], ["inventory"], ["locate and remove"], "security", seen=False, evidence="All 53 BSSIDs share one vendor OUI.")
E("SEC-03", "Protected management frames not enforced", "Management frames are not protected, making spoofed disconnects possible.",
  "RSN capabilities MFPR=0 on corporate SSID.", "Beacon RSN MFPR bit.", "", "low", ["config"], [], ["require PMF where clients support it"], "security", seen=None,
  evidence="Not assessed: converter does not extract RSN capability bits yet.")

# ---------------- INFRA ----------------
E("INFRA-01", "Central authentication service outage",
  "The same login failure happens on many access points at once, so the cause is a shared service behind them.",
  "EAP-01/EAP-03 on >= 3 APs or >= 2 channels within 2 min, while another SSID on the same radios is healthy.",
  "Root-incident rule over EAP incidents + control comparison.", "", "critical",
  ["RADIUS/AAA outage", "controller-AAA path failure"], ["RADIUS health", "controller AAA status"], ["restore AAA service"], "identity/AAA",
  seen=True, evidence="EAP-01 on 26 APs, 8 channels, 8 sensors; NET-T on same radios: 31 handshakes, 0 failures. Streaming detector would fire at 47.5 s.")
E("INFRA-02", "AP reboot", "An access point restarted.", "Beacons stop then resume with TSF reset near zero.", "Beacon gap > 5 s then TSF < previous.",
  "", "medium", ["power", "crash", "firmware"], ["AP uptime"], ["check PoE/firmware"], "network", seen=False)
E("INFRA-03", "Controller-wide behaviour change", "Many APs change behaviour at the same moment (config push).",
  "Same new pattern (e.g. new reason code) starts on many APs within a short window.", "New reason/status code on >= 3 APs within 60 s.",
  "", "medium", ["config push"], ["change log"], ["review change"], "network", seen=False,
  evidence="SESS-02 onset is a rolling 15 s-per-client wave (402-641 s), not simultaneous.")

# ---------------- SENS ----------------
E("SENS-01", "Sensor deaf / silent", "A sensor stops hearing anything.", "No beacons from any AP for > 2 s.", "Gap > 2 s in all beacons for a sensor.",
  "", "high", ["sensor down", "channel change"], ["sensor heartbeat"], ["restart sensor"], "platform", seen=False, evidence="Longest beacon gap 0.41 s on any sensor.")
E("SENS-02", "Sensor clock offset", "Sensors' clocks disagree, so matching events across sensors needs tolerance.",
  "Same scripted/periodic event lines up on per-sensor relative time but not on wall-clock time.", "Estimate offset from shared BSSID TSF when available.",
  "", "low", ["no NTP/PTP"], [], ["sync sensor clocks"], "platform", seen=True,
  evidence="Start epochs differ by up to 2.3 s; joins sit on an exact 2 s grid in per-sensor time only. Cannot tell offset from staggered start (no shared BSSID).")
E("SENS-03", "Partial capture window", "The analysed data covers only part of the recording.", "Converted window << capture length.", "Compare window to capture length.",
  "", "info", ["conversion limit"], [], ["convert full capture"], "platform", seen=True, evidence="Old JSON: 50 s of 1,802 s (2.8%).")
E("SENS-04", "Physically impossible radio values", "The capture contains values real radios cannot produce.",
  "e.g. 1 Mbit/s on 5 GHz, constant RSSI.", "Rate not valid for band; RSSI variance 0 across > 100 frames.", "", "info",
  ["emulated capture", "sensor driver bug"], [], ["treat airtime maths with care"], "platform", seen=True, evidence="1 Mbit/s beacons on 5 GHz; RSSI constant on 53/53 BSSIDs.")
E("SENS-05", "Uplink not heard (visibility asymmetry)", "Sensors hear access points far better than devices, so many device frames are missing.",
  "Ratio of AP-sent to client-sent frames in handshakes.", "Track per-client visibility; lower confidence of client-side verdicts.",
  "", "info", ["sensor placement"], [], ["place sensors nearer clients"], "platform", seen=True, evidence="173,964 probe responses vs 6,024 probe requests; M2/M4 heard for 4 of 24 IoT devices.")
E("SENS-06", "Truncated frames", "Frames are cut to headers (by design); lengths must use the on-air size.", "caplen < frame length.", "Informational.",
  "", "info", ["header-only capture policy"], [], [], "platform", seen=True, evidence="Data frames truncated (e.g. 49 of 137 bytes).")

# ---------------- OTHER ----------------
E("OTHER-CODE", "Unknown or unmapped code", "A status/reason/EAP code arrived that the catalog does not map (reserved or vendor-specific).",
  "Code value not in ieee_codes.json or not mapped to an entry.", "Every such frame -> unknown_events.jsonl.", "", "unknown", [], [], [], "discovery-agent", visibility="full", seen=False)
E("OTHER-SEQ", "Unexpected sequence", "Frames arrived in an order no known pattern explains.",
  "Episode state machine hits an undefined transition.", "Every such transition -> unknown_events.jsonl.", "", "unknown", [], [], [], "discovery-agent", seen=False)
E("OTHER-STAT", "Statistical anomaly", "A metric moved far from normal with no known explanation.",
  "Per-metric z-score > 4 vs rolling baseline, no catalog detector fired.", "Every such spike -> unknown_events.jsonl.", "", "unknown", [], [], [], "discovery-agent", seen=False)


def build() -> dict:
    ids = [e["id"] for e in ENTRIES]
    assert len(ids) == len(set(ids)), "duplicate ids"
    reason_map, status_map = {}, {}
    for e in ENTRIES:
        for r in e["codes"]["reason"]:
            reason_map.setdefault(str(r), e["id"])
        for s in e["codes"]["status"]:
            status_map.setdefault(str(s), e["id"])
    reasons = CODES["wlan.fixed.reason_code"]
    statuses = CODES["wlan.fixed.status_code"]
    code_index = {
        "reason": {k: {"text": v, "entry": reason_map.get(k, "OTHER-CODE")} for k, v in reasons.items()},
        "status": {k: {"text": v, "entry": ("OK" if k == "0" else status_map.get(k, "ASSOC-05" if "Association" in v or "association" in v else "OTHER-CODE"))}
                   for k, v in statuses.items()},
        "eap_code": CODES["eap.code"], "eap_type": CODES["eap.type"], "eapol_type": CODES["eapol.type"],
        "auth_alg": CODES["wlan.fixed.auth.alg"],
    }
    unknown_codes = [c for c in list(reason_map) + list(status_map) if c not in reasons and c not in statuses]
    assert not unknown_codes, f"catalog references codes not in IEEE tables: {unknown_codes}"
    return {
        "version": VERSION, "source_codes": CODES["_source"], "categories": CATEGORIES,
        "entries": ENTRIES, "code_index": code_index,
        "other_policy": "Any frame, sequence or metric that no entry matches is stored in out/unknown_events.jsonl as OTHER-* and handed to the discovery agent (Part 3).",
    }


def to_markdown(cat: dict) -> str:
    lines = [f"# Airframe error catalog v{cat['version']}", "",
             f"{len(cat['entries'])} entries in {len(cat['categories'])} categories. Codes verified against {cat['source_codes']}.", "",
             "`seen`: yes = found in the provided captures (evidence given), no = checked and not present, n/a = not assessable yet.", ""]
    for cid, cname in cat["categories"].items():
        es = [e for e in cat["entries"] if e["category"] == cid]
        if not es:
            continue
        lines += [f"## {cid}: {cname}", "", "| ID | Problem | Plain meaning | Severity | Owner | Codes | Seen | Evidence |", "|---|---|---|---|---|---|---|---|"]
        for e in es:
            codes = ", ".join([f"R{r}" for r in e["codes"]["reason"]][:6] + [f"S{s}" for s in e["codes"]["status"]][:6])
            seen = {True: "yes", False: "no", None: "n/a"}[e["dataset"]["seen"]]
            lines.append(f"| {e['id']} | {e['name']} | {e['plain']} | {e['default_severity']} | {e['owner']} | {codes} | {seen} | {e['dataset']['evidence']} |")
        lines.append("")
    lines += ["## Detection details", ""]
    for e in cat["entries"]:
        lines += [f"### {e['id']} {e['name']}", f"- **Looks like:** {e['signature']}", f"- **Rule:** {e['detect']}"]
        if e["normal_lookalike"]:
            lines.append(f"- **Not to confuse with:** {e['normal_lookalike']}")
        if e["likely_causes"]:
            lines.append(f"- **Likely causes:** {'; '.join(e['likely_causes'])}")
        if e["confirm_outside_headers"]:
            lines.append(f"- **Confirm with:** {'; '.join(e['confirm_outside_headers'])}")
        if e["standard_fix"]:
            lines.append(f"- **Standard fix:** {'; '.join(e['standard_fix'])}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    cat = build()
    (HERE / "error_catalog.json").write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    (HERE / "error_catalog.md").write_text(to_markdown(cat), encoding="utf-8")
    seen = sum(1 for e in cat["entries"] if e["dataset"]["seen"])
    mapped_r = sum(1 for v in cat["code_index"]["reason"].values() if v["entry"] != "OTHER-CODE")
    mapped_s = sum(1 for v in cat["code_index"]["status"].values() if v["entry"] != "OTHER-CODE")
    print(f"entries={len(cat['entries'])} seen_in_dataset={seen} reason_codes_mapped={mapped_r}/{len(cat['code_index']['reason'])} "
          f"status_codes_mapped={mapped_s}/{len(cat['code_index']['status'])}")


if __name__ == "__main__":
    main()
