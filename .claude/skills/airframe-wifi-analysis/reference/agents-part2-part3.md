# Part 2 and Part 3 contracts

Load the `claude-api` skill before writing agent code (current model ids, tool-use syntax, prompt caching). Agents only ever see masked data.

## Incident schema

Written by Part 1 to the incident store and `out/incidents.json`; the only input Part 2 needs.

```json
{
  "id": "INC-0001", "catalog_id": "EAP-01", "title": "Corporate login stalls after 'who are you?' on every AP",
  "status": "open|updating|resolved|closed", "severity": "critical", "confidence": 0.9,
  "blast_radius": "device|ap|channel|site", "network": "NET-C",
  "where": {"aps": ["AP01"], "channels": [36], "sensors": ["S1"]},
  "window": {"start_rel_s": 11.4, "end_rel_s": 1790.0},
  "devices_affected": 63, "devices": ["c:3f9a21bd"],
  "signature": {"last_step": "EAP-Identity", "reask_s": 30.0, "kick_s": 60.0, "deauth_reason": 23},
  "control": {"network": "NET-T", "same_radios": true, "handshakes_ok": 31, "handshakes_seen": 31},
  "children": ["INC-0002"], "parent": null,
  "evidence": [{"sensor": "S3", "n": 1140, "what": "client EAP Response/Identity within 1 ms"}],
  "data_quality": ["SENS-02", "SENS-04", "SENS-05"],
  "first_seen_rel_s": 47.5, "updated_rel_s": 1790.0
}
```

## Part 2: fix-proposal agent

**Trigger:** incident created/escalated with severity ≥ high, or user clicks "Explain & fix".

**Context pack** (built by code, not by the model): incident + children summary, catalog entry (`likely_causes`, `confirm_outside_headers`, `standard_fix`, `owner`, `normal_lookalike`), control comparison, similar past incidents + outcomes, site inventory if present, change calendar if present.

**Tools (all read-only, all return masked data):**
| Tool | Returns |
|---|---|
| `get_incident(id)` | incident JSON with children |
| `get_timeline(device, t_from, t_to)` | ordered steps with sensor + evidence ids |
| `query_frames(filter, limit)` | frames matching subtype/code/AP/time filter |
| `compare_control(incident_id)` | per-SSID success stats on the same radios |
| `catalog_lookup(id or code)` | catalog entry or code meaning from `ieee_codes.json` |
| `search_history(catalog_id)` | past incidents of that type and what fixed them |

No write, transmit or configuration tools exist, by construction.

**Reasoning steps the prompt enforces:** restate facts with evidence ids → rank hypotheses from catalog causes + history → test each with tools → choose the one outside check that separates the top two → fix steps, owner, risk, rollback → success criteria Part 1 can measure.

**Output (`fix_proposal.json`, schema-validated):**
```json
{
  "incident_id": "INC-0001", "root_cause": "802.1X requests not answered by the AAA path",
  "confidence": 0.8, "hypotheses": [{"cause": "RADIUS unreachable", "for": ["E12"], "against": [], "p": 0.6}],
  "deciding_check": "RADIUS logs: are Access-Requests from the controller arriving?",
  "fix_steps": ["restore controller -> RADIUS reachability", "clear client exclusion for 18 laptops (INC-0003)"],
  "owner": "identity/AAA", "risk": "low", "rollback": "n/a (no config change on Wi-Fi)",
  "success_criteria": [{"metric": "EAP-04 count", "op": "==", "value": 0, "window_s": 600},
                       {"metric": "NET-C login success rate", "op": ">", "value": 0.95, "window_s": 600}],
  "evidence": ["INC-0001", "S3:1140"], "needs_human": null
}
```

**Guardrails:** every factual claim cites an evidence id; every code is validated against `ieee_codes.json`; confidence < 0.6 → `needs_human` with the missing fact instead of a fix; output rejected if the schema fails or contains a MAC/SSID pattern.

**Verification loop:** on approval, Part 1 evaluates `success_criteria` live; met → incident resolved and outcome stored for `search_history`; not met after the window → agent re-run with new evidence.

**Golden test (this dataset):** for the NET-C root incident the proposal must (a) blame the 802.1X/AAA path, not RF; (b) cite the healthy NET-T control; (c) include clearing the exclusion for the 18 SESS-02 laptops; (d) propose a measurable success test; (e) not suggest channel or power changes.

## Part 3: catalog and discovery agent

**Catalog:** `catalog/error_catalog.json` built by `catalog/build_catalog.py` from curated entries + `ieee_codes.json`. Entry fields: `id, category, name, plain, signature, detect, normal_lookalike, default_severity, likely_causes, confirm_outside_headers, standard_fix, owner, codes{reason,status}, header_visibility, dataset{seen,evidence}`. `code_index` maps every reason/status code to an entry; reserved values map to `OTHER-CODE`. Current: v1.0.0, 79 entries, 13 categories, 63/63 reason and 120/139 status codes mapped (19 reserved).

**Unknown event record** (`out/unknown_events.jsonl`):
```json
{"id": "UNK-000123", "kind": "OTHER-CODE|OTHER-SEQ|OTHER-STAT", "rel_s": 812.4, "sensor": "S4",
 "device": "c:ab12cd34", "ap": "AP22", "network": "NET-C",
 "detail": {"frame": "Deauthentication", "reason": 99} ,
 "context": {"timeline": ["-10s..+10s steps"], "open_incidents": ["INC-0001"], "metrics": {"retry_share": 0.31}}}
```

**Discovery run:** when a cluster reaches 20 events, has a high-severity hint, or hourly.
1. Cluster by (kind, code or transition or metric, sender role, device class, network).
2. Investigate per cluster with the read-only tools above plus the IEEE text.
3. Decide: variant of an existing entry (extend its codes/signature) or new entry.
4. Draft the entry in catalog schema and a **rule in the JSON rule DSL** (below); never free-form code.
5. Validate automatically: schema, unique id, codes exist in `ieee_codes.json`, backtest fires on the cluster, false-positive rate on healthy windows < 1%.
6. Human review: approve / edit / reject (reject labels the cluster benign so it is not raised again).
7. Merge: bump catalog version, append changelog, hot-reload detectors, re-classify stored OTHER events, expose new causes/fixes to Part 2.

**Rule DSL** (interpreted by one generic detector):
```json
{
  "id": "SESS-02",
  "match": {"subtype": ["Deauthentication", "Disassociation"], "reason": [2], "sender_role": "ap"},
  "group_by": ["device", "ap"],
  "window_s": 120,
  "threshold": {"count": {">=": 3}},
  "suppress_if": [{"catalog_id": "ROAM-01", "within_s": 1}]
}
```
Allowed match keys: frame fields from the normaliser (`subtype`, `reason`, `status`, `eap_code`, `eapol_msg`, `sender_role`, `network`, `retry`, `rate_mbps`, `freq_mhz`), metric names from the counters, and episode states. Allowed thresholds: `count`, `rate_per_s`, `share`, `absent_for_s`, `zscore`.
