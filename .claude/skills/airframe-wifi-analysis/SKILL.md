---
name: airframe-wifi-analysis
description: Build, extend, test or run the Airframe system for header-only 802.11 / 802.1X sensor captures from several overlapping sensors. Part 1 is a real-time pipeline + live dashboard that says WHAT is wrong on the Wi-Fi and WHERE (de-duplicated, evidence-backed incidents). Part 2 is a read-only AI agent that proposes fixes for an incident. Part 3 is the error catalog (every known problem) plus a discovery agent that turns unmatched OTHER events into new catalog entries. Use for any work on convert_full.py, ingest/streaming, decoding, episode state machines, detectors, correlation, incidents.json, the dashboard, the catalog in catalog/, or the Part 2/3 agents, and when analysing sensorNN.pcap / json_full/*.jsonl.
---

# Airframe: find what is wrong on the air, where, and how to fix it

## Mission and definition of done

| Part | Produces | Done when |
|---|---|---|
| 1 What + where (real time) | incident store + `out/incidents.json` + live dashboard | Replaying `json_full/` (or live tshark pipes) reproduces every fact in [reference/dataset-facts.md](reference/dataset-facts.md); root incident for the NET-C outage appears ≤ 40 s after the first failing join; no raw MAC/SSID/EAP identity anywhere in outputs |
| 2 How to fix (agent) | `fix_proposal.json` per incident, shown next to it | For the NET-C root incident it names the 802.1X/AAA path, the deciding check, the owner, the exclusion-list clean-up for the 18 fast-reject laptops, and a measurable success test; every claim cites evidence ids |
| 3 Catalog + discovery | `catalog/error_catalog.json` vN, `out/unknown_events.jsonl`, draft entries | Every detector maps to a catalog id; every unmatched frame/sequence/metric lands in OTHER with context; a draft entry passes schema, code and backtest checks before human review |

Contracts and agent details: [reference/agents-part2-part3.md](reference/agents-part2-part3.md). Protocol facts: [reference/protocol-cheatsheet.md](reference/protocol-cheatsheet.md). Flows: `v3/flows.md` (Mermaid) and `v3/flows.html`. Report: `v3/Airframe_Analysis_v3.pdf`. (`v4/` is abandoned: ignore it.)

## Implementation stack (decided 2026-09-26)

| Layer | Choice | Why |
|---|---|---|
| Ingest | tshark 4.6.9 (`-r - -l -T fields`), one process per sensor; JSONL replay for fast demo | Measured 30× faster than scapy; brief provides Wireshark/tshark |
| Engine + API | Python 3.13, FastAPI + uvicorn, asyncio, in-process state; SSE push every 1 s | Brief provides Python; converter/oracle/benchmark already Python |
| Dashboard | React 19 + TypeScript + Vite, Recharts, plain CSS variables (light/dark) | Typed, fast live UI; built to static files served by FastAPI → one-command demo |
| Agents (Part 2/3) | Anthropic Python SDK tool use when `ANTHROPIC_API_KEY` is set; deterministic catalog playbook otherwise (labelled "offline") | No key on this machine; demo must still work |
| Tests | pytest: unit per stage + golden replay of `json_full/` against dataset-facts | Oracle-driven |

Repo layout: `backend/airframe/` (Python package), `backend/tests/`, `backend/requirements.txt`, `frontend/` (React dashboard, builds to `frontend/dist`), shared data dirs (`hackaton_airframe/`, `json_full/`, `catalog/`, `out/`) at the repo root. `config.ROOT` resolves three parents up from `backend/airframe/config.py`, so it always points at the repo root regardless of cwd.

Run (from `backend/`, with the repo-root `.venv` activated or referenced as `..\.venv\Scripts\python.exe`): `python -m airframe serve` (dashboard at http://127.0.0.1:8000), `python -m airframe batch` (full replay, writes `../out/`), `pytest`.

## Discoveries to design around (all verified)

- Clock: use per-sensor relative time `t` as event time. Joins sit on an exact 2 s grid in `t`; epochs are offset by up to 2.3 s.
- Homing rule (0 exceptions): laptop N → AP N, phone N → AP N+5, IoT N → AP N+12 (mod 30). Useful for tests only; never hard-code in detectors.
- Timers: EAP Identity re-ask 30.0 s; reason-23 kick 60.0 s after association (488/489 within ±0.1 s). Backoff between attempts grows 28 s → ~200 s.
- Fast-reject (SESS-02) starts per laptop after 3–5 reason-23 kicks; afterwards only reason 2, never 23.
- Streaming detection targets: first stall visible at t = 41.4 s; root (3rd AP) at t = 47.5 s; kicks confirm at 77.5 s.
- Catalog v1.0.0: 79 entries / 13 categories; 63/63 reason and 120/139 status codes mapped (19 reserved → OTHER-CODE). This dataset produces no OTHER-CODE events, so Part 3 demos need a clearly labelled synthetic injection.

## Hard rules (challenge brief)

- **Header-only.** No payload, no layer 3. Never infer from payload bytes.
- **Passive.** Never transmit; never touch real APs, controllers, sensors or RADIUS. Agents get read-only tools only.
- **Privacy.** HMAC-SHA256 MACs with secret `AIRFRAME_SALT` (never committed), show 8 hex chars; SSIDs → `NET-C`, `NET-T`; never store EAP identities. Mask in the normaliser, before any other stage or any LLM sees data.
- **Normal is not a failure.** Single leave (reason 3/8) + join elsewhere within ~1 s = roam. Device already connected at start = healthy. A step not heard by any capable sensor = `not_observed`, never `missing`.
- **One client = one finding.** Same device + same catalog entry + overlapping window = one incident with `seen_by`; same entry on ≥ 3 APs or ≥ 2 channels within 2 min = one root incident with children.
- Captures stay in the approved environment.

## Data and tools (verified 2026-09-25)

- `hackaton_airframe/hackaton_airframe/sensorNN.pcap`: 8 sensors, 30.0 min each (1,802 s), 1,118,853 frames, radiotap linktype 127.
- `json/sensorNN.json`: old scapy conversion, **first 50 s only (2.8%)**. Do not build on it.
- `python convert_full.py` → `json_full/sensorNN.jsonl` (+ `.meta.json`) in ~100 s using tshark (`C:\Program Files\Wireshark\tshark.exe`, v4.6.9, not on PATH). Same field names as the scapy converter plus `bssid`, `akm`, `eapol.msgnr`, `action_category`, `csa_new_channel`, `pwr_mgt`. `python validate_converter.py` proves equality with scapy on the 28,536 overlapping frames (only `len` differs on 171 truncated data frames: tshark gives on-air length).
- `python verify_findings.py`: 36 checks = the test oracle. Keep it green.
- `python realtime_bench.py <speed> <seconds>`: replays pcaps into `tshark -r - -l` pipes. Measured: 1× → p50 2.8 ms, p99 10.5 ms; max ≈ 9,500 frames/s (≈15× live) on this laptop.
- scapy parses only ~244 frames/s per core: never use it on the hot path.
- `catalog/ieee_codes.json`: Wireshark value tables (63 reason, 139 status, EAP/EAPOL/auth-alg). The only allowed source for code meanings.

## Architecture (Part 1, streaming)

```
per sensor: pcap stream (live pipe | dumpcap | replay) -> tshark -r - -l -T fields
  -> normalise+mask -> event queue (asyncio; Kafka/NATS at scale)
  -> [beacon tracker | sliding counters | episode state machines]
  -> detectors (= catalog entries) -> correlator (5 s grace) -> incident store (SQLite/DuckDB)
  -> API + Server-Sent Events (1 s) -> browser dashboard
unmatched -> out/unknown_events.jsonl (Part 3)
```

Implemented layout (built 2026-09-26; 20 tests green, browser-verified light/dark/mobile; reorganised into backend/frontend 2026-09-27):
```
backend/airframe/    (Python package; run from backend/: `..\.venv\Scripts\python.exe -m airframe serve`)
  config.py      every threshold, paths, agent mode/model (AIRFRAME_AGENT_MODE, AIRFRAME_MODEL, AIRFRAME_AUTOSTART)
  tshark.py      FIELDS + row_to_dict (converter schema) + stream_pcap(); no scapy on the hot path
  sources.py     merged(kind): heap-merge of 8 sensor streams by per-sensor t (jsonl via orjson, or pcap via threaded tshark)
  privacy.py     Masker: HMAC MACs, radio id = hash of bssid[:14], SSID -> ENT-n/PSK-n by AKM, internal radio numbers
  decode.py      normalise(raw) -> Frame (slots): kind, sender ap|client, masked client/ap/bssid, codes, EAP, msgnr
  catalog.py     Catalog: base + catalog/extensions.json (Part 3 adoptions), for_code(), code_text(), add_extension()
  engine.py      Engine.process(frame): beacon/bssid/AP tracking, 10 s buckets, attempts (per device), all detectors;
                 _evaluate(watermark) runs event-time timers; attempts_all -> net_stats() computed at read time
  incidents.py   Detection/Incident/IncidentManager: one incident per (catalog id, key), reopen within 30 min,
                 INFRA-01 root per network when login-family hits >=3 APs, symptom linking, lifecycle
  views.py       snapshot(), incident_dict(full), device_story(), control(); the only JSON leaving the engine
  rules.py       JSON rule DSL validate()/evaluate() for Part 3 drafts
  runner.py      build_engine/run_batch; Replay thread (speed, pause, inject), RLock shared with agents, publish ~1/s
  server.py      FastAPI: /api/stream (SSE), /api/snapshot, /api/replay, /api/incidents/{id}[/fix[/decision]],
                 /api/devices/{id}, /api/discovery/{cluster}/draft, /api/discovery/drafts/{id}/decision,
                 /api/debug/inject-unknown (synthetic, labelled), /api/jobs/{key}; serves web/dist
  agents/tools.py       read-only tools (get_incident, get_device_timeline, query_frames, compare_control,
                        catalog_lookup, search_history); MAC-blocking output filter
  agents/fix_agent.py   Part 2: Claude manual tool loop (beta messages, adaptive thinking, json_schema output,
                        fallbacks="default") or offline playbook; validate(); measure()/check_success() live
  agents/discovery.py   Part 3: cluster(), draft() (Claude or heuristic), validate(), backtest(), adopt()
frontend/ (React 19 + TS + Vite + Recharts, builds to frontend/dist)  src/api.ts (types, useSnapshot SSE hook),
     components/{Overview,Incidents,Devices,Air,Learning,Charts,ui}.tsx, styles.css (tokens light/dark, validated
     4-slot palette, status colours)
backend/tests/ test_units.py, test_golden.py (verified facts), test_api.py (end to end), ui_check.py (Playwright + Edge)
```

Implementation rules learned while building:
- Anything that changes what the UI shows after the replay has finished (agent result, decision, draft) must call `REPLAY._publish()`; SSE only pushes on a new snapshot version.
- Every engine read from an API/agent thread goes through `REPLAY.lock` (RLock); the replay thread holds it per frame.
- Keep per-network stats derived from `attempts_all` at read time: joins can precede the AP's first beacon.
- The UI check adopts a synthetic catalog entry; it restores `catalog/extensions.json` itself, but a running server keeps the entry in memory until restarted.
- Device channel = its access point's sensor channel (devices are heard probing on every sensor).

### Streaming rules
- Timers run on **event time** with a watermark = max event time seen − `ALLOWED_LATENESS_S=3`. "Nothing happened for 30 s" is judged on capture time, never wall time.
- Sensors' start epochs differ by up to 2.3 s and no BSSID is shared, so TSF alignment is impossible here: merge with `MERGE_WINDOW_S=5`.
- Incident lifecycle: `open → updating → resolved` (no new evidence for 2 cycle lengths) `→ closed`. Update counts on the same incident; never add a row per minute.
- Dashboard views: overview (health, open incidents, devices failing), incident list ("seen by S1–S8, counted once"), device story (join ladder coloured by sensor), channel health (retries, probe load, beacon overhead), sensor coverage (channel, BSSIDs, missing networks). Push every 1 s over SSE; replay mode at 1×/10× for the demo.

## Decoding essentials

- Transmitter = `addr2`; ACK/CTS have none. Data: `from_ds` → AP sent it, `to_ds` → client sent it.
- AP role = sends beacons. BSSID pattern here `00:0b:86:XX:00:0Y` (XX = AP number hex, Y 0 = NET-C, 1 = NET-T); derive roles from beacons, use the pattern only in tests.
- NET-C beacons carry AKM 1 (802.1X), NET-T AKM 2 (PSK), read from the air.
- EAPOL-Key message: use `eapol.msgnr` (tshark); flag rule (ack/mic/secure) gives the same answer on this data. EAPOL rides in Data frames. EAP codes 1 Req, 2 Resp, 3 Success, 4 Failure.
- Always read status (0 = OK) and reason codes; always record who sent a deauth/disassoc.

## Episode state machine (per client, BSSID)

`IDLE → AUTH → ASSOC → EAP → KEY(M1..M4) → CONNECTED → LEFT`, event-time timeout 90 s. Each step: `seen | proven | not_observed | missing`.

Proof rules (AP side first):
| AP frame | Proves |
|---|---|
| Auth seq 2 status 0 | client sent auth request |
| Assoc resp status 0 | client asked and was accepted |
| EAPOL M1 | assoc (and EAP on 802.1X) succeeded |
| EAPOL M3 | AP received a valid M2 |
| Block-Ack (Action cat 3) setup after join | association alive (use when M3 not captured) |
| Protected data relayed / ACKed | keys installed |

Undefined transition → emit `OTHER-SEQ` with ±10 s timeline, do not crash or guess.

## Detectors = catalog entries

Every detector declares the catalog id it implements and must check the entry's `normal_lookalike` before emitting. Key ones for this data (full list and rules in `catalog/error_catalog.md`):

| Catalog id | Fires when (thresholds in config.py) |
|---|---|
| EAP-01 | Identity request, no EAP method/Success/Failure/M1 within 20 s; confirm by fixed-interval re-ask |
| EAP-04 | deauth reason 23 from AP |
| SESS-01 | ≥ 3 join→failure cycles per client in 10 min |
| SESS-02 | ≥ 3 reason-2 deauth/disassoc from AP to one client in 2 min |
| DISC-01 / DISC-02 | expected SSID missing on an AP radio / AP never heard, ≥ 60 s with sensor alive |
| DISC-03 | probe responses per client > 1/s for 60 s, or area > 3× baseline |
| RF-01 | retry share > 20% (≥ 30 frames) per transmitter or frame type |
| RF-03 / RF-04 | beacon airtime > 10% at stated rate / beacon rate < 12 Mbit/s on 5 GHz or invalid for band |
| SESS-08 | ≥ 8 distinct clients leaving within 10 s |
| KEY-01..05 | handshake failures (none present here: must stay silent) |
| INFRA-01 | root rule over EAP incidents + healthy control SSID on same radios |
| SENS-* | data-quality flags; lower confidence, never incidents on their own |

Anything code-based that maps to `OTHER-CODE` in `catalog.code_index`, or a metric z-score > 4 with no detector (`OTHER-STAT`), goes to `out/unknown_events.jsonl`.

## Correlate, score, report

1. Merge same client + entry within 5 s → `seen_by` union.
2. Root: same entry on ≥ 3 APs or ≥ 2 channels within 120 s → root incident, `blast_radius=site|channel`, children linked.
3. Causal links: SESS-01, SESS-02, DISC-03 become children of an EAP/KEY root when clients overlap.
4. Control comparison: health of the other SSID on the same radios (here NET-T: 31/31 handshakes reach M3).
5. Score: severity from devices × duration × network; confidence reduced by `not_observed` steps, single-sensor evidence, SENS flags.
6. `incidents.json` entry schema: see [reference/agents-part2-part3.md](reference/agents-part2-part3.md#incident-schema).

## Pitfalls found in this data

- The old JSON window (50 s) hides the whole story: reason-23 kicks start at 71 s, fast-reject at 402 s.
- Beacons claim 1 Mbit/s on 5 GHz (impossible); RSSI is constant per BSSID; first attempts sit on an exact 2 s grid: emulated. Protocol logic transfers; airtime maths does not.
- 51 of 63 NET-C devices and 20 of 24 IoT devices are inaudible in their own join exchange. Absence of client frames is never evidence.
- 54,484 of 54,544 retries are probe responses: always break retries down by frame type.
- Reason 3 comes from clients (normal); reason 23 and reason 2 come from APs. Reason-2 frames use the AP's own sequence numbers (not spoofed).
- No device roams and no status code is non-zero: roam and reject detectors must stay silent (false-positive guard).
- One IoT join shows M1 but no M3, followed by AP Block-Ack setup: `KEY-06 not_observed`, not a KEY-01 failure.

## Working method

1. Read [reference/dataset-facts.md](reference/dataset-facts.md) first; it is the oracle.
2. Build stage by stage; after each stage add a unit test and print a per-sensor summary.
3. Mirror `verify_findings.py` in `tests/test_golden.py` early and keep it green.
4. Before finishing any change, grep outputs and dashboard build for `[0-9a-f]{2}(:[0-9a-f]{2}){5}` and the real SSID strings: both must return nothing.
5. Write incident titles in plain words; the audience includes non-network people.
