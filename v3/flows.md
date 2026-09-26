# Airframe flows: Part 1, Part 2, Part 3 (high level and deep level)

Plain version. Renders in VS Code (Markdown Preview Mermaid Support), GitHub, or https://mermaid.live.
The styled version is `v3/flows.html`.

---

## 0. The whole system at a glance

```mermaid
flowchart LR
    S[/"Sensors (8 now, thousands later)<br/>live pcap streams or replayed files"/] --> P1
    subgraph P1["Part 1: WHAT and WHERE (real time)"]
        direction TB
        A1[Decode + mask] --> A2[Device stories + counters] --> A3[Match against error catalog] --> A4[Incidents: dedupe, root cause grouping, location]
    end
    A4 --> D[(Live dashboard<br/>graphs + incident list)]
    A4 -->|known problem| P2
    A3 -->|no match| P3
    subgraph P2["Part 2: HOW TO FIX (AI agent)"]
        B1[Investigate with read-only tools] --> B2[Fix proposal + owner + risk] --> B3[Human approves]
    end
    subgraph P3["Part 3: LEARN NEW PROBLEMS (AI agent)"]
        C1[OTHER store] --> C2[Cluster + investigate] --> C3[Draft new catalog entry + rule + fix] --> C4[Backtest + human review]
    end
    B3 --> T[Ticket / runbook for the owning team]
    C4 -->|catalog v+1| CAT[(Error catalog)]
    CAT --> A3
    CAT --> B1
    T -.->|fix applied| A4
```

---

## 1. Real-time data path (measured on this laptop)

```mermaid
flowchart LR
    subgraph Edge["Per sensor"]
        R1["pcap stream<br/>(live pipe / dumpcap / replay)"] --> R2["tshark -r - -l<br/>header fields only"]
    end
    R2 -->|"rows, p99 < 11 ms"| R3["Normalise + mask<br/>(HMAC MACs, SSID labels)"]
    R3 --> Q[["Event queue<br/>(asyncio now, Kafka/NATS at scale)"]]
    Q --> W1["Episode state machines<br/>event-time timers + watermark"]
    Q --> W2["Sliding counters<br/>1 s / 60 s per AP, channel, client"]
    W1 --> DET[Detectors]
    W2 --> DET
    DET --> COR["Correlator<br/>5 s grace for clock skew"]
    COR --> DB[("Incident store<br/>SQLite / DuckDB")]
    DB --> API["API + Server-Sent Events<br/>push every 1 s"]
    API --> UI["Browser dashboard<br/>live graphs, incident list"]
```

Measured: 8 sensors at live pace = 571 frames/s, p50 2.8 ms, p99 10.5 ms from pipe to decoded row. The laptop sustains about 15x the live rate (≈ 9,500 frames/s). The site-wide login outage would appear 36 s after the first failed join (first 30 s re-ask on the third AP at t = 47.5 s).

---

## 2. Part 1: find WHAT is wrong and WHERE

### 2a. High level

```mermaid
flowchart LR
    IN[/Frames from all sensors/] --> SEE["What can we see?<br/>decode, mask, sensor coverage"]
    SEE --> WHAT["WHAT is wrong?<br/>device stories, detectors, catalog match"]
    WHAT --> ONE["Count once<br/>1 device + 1 problem + 1 window = 1 incident<br/>many APs, same failure = 1 root incident"]
    ONE --> WHERE["WHERE and how bad?<br/>AP, channel, sensors, blast radius, severity, confidence"]
    WHERE --> OUT[("incidents.json + live dashboard")]
```

### 2b. Deep level

```mermaid
flowchart TD
    F["Frame row (sensor_id, ts, rate, freq, rssi, type, flags,<br/>ra, ta, bssid, seq, codes, EAP, EAPOL msgnr)"] --> M["Mask: HMAC-SHA256(MAC, site salt)[:8];<br/>SSID -> NET-C / NET-T; drop EAP identity"]
    M --> ROLE["Role + direction:<br/>beacon sender = AP; from_ds/to_ds; ACK has no sender"]
    ROLE --> SPLIT{Frame kind}
    SPLIT -->|beacon| BC["Per-BSSID beacon tracker<br/>interval, loss, rate, AKM, SSID set per AP"]
    SPLIT -->|probe / ack / data| CNT["Sliding counters<br/>probes per client, retry share, airtime"]
    SPLIT -->|auth / assoc / EAP / EAPOL / deauth / disassoc| EP["Episode state machine per (client, BSSID)<br/>IDLE→AUTH→ASSOC→EAP→KEY(M1..M4)→CONNECTED→LEFT"]
    EP --> INF["Inference rules (AP side first)<br/>M3 proves M2; assoc status 0 proves request; Block-Ack setup proves association"]
    INF --> VIS{"Step not heard:<br/>was a sensor able to hear it?"}
    VIS -->|no| NO["not_observed → info only (KEY-06)"]
    VIS -->|yes| MISS["missing → evidence for a detector"]
    BC --> DETS
    CNT --> DETS
    MISS --> DETS
    EP --> DETS["Detectors = catalog entries<br/>EAP-01 stall, EAP-04 reason 23, SESS-01 loop, SESS-02 fast reject,<br/>DISC-01 missing network, DISC-03 probe storm, RF-01 retries, RF-03 overhead, ..."]
    DETS --> MATCH{Matched a catalog entry?}
    MATCH -->|no| OTHER[["OTHER-CODE / OTHER-SEQ / OTHER-STAT<br/>→ unknown_events.jsonl (Part 3)"]]
    MATCH -->|yes| MERGE["Merge: same client + entry within 5 s → 1 incident<br/>(union of sensors = seen_by)"]
    MERGE --> ROOT["Root grouping: same entry on ≥ 3 APs or ≥ 2 channels in 2 min<br/>→ 1 root incident, clients as children"]
    ROOT --> CAUSE["Causal links: loop / fast-reject / probe storm → child of EAP root"]
    CAUSE --> CTRL["Control comparison: other SSID on the same radios healthy?"]
    CTRL --> SCORE["Score: severity (devices × duration × network), confidence<br/>(visibility, sensor count, data-quality flags), blast radius"]
    SCORE --> LOC["Location: APs, channels, sensors, time window"]
    LOC --> LIFE["Lifecycle: open → updating → resolved (quiet 2 cycles) → closed"]
    LIFE --> OUT[("incidents.json / incident store → dashboard + Part 2")]
```

---

## 3. Part 2: AI agent that proposes HOW TO FIX

### 3a. High level

```mermaid
flowchart LR
    I[/"Incident from Part 1<br/>(what, where, evidence)"/] --> C["Build context<br/>incident + catalog entry + history + site info"]
    C --> A["AI agent investigates<br/>read-only tools, ranks causes"]
    A --> P["Fix proposal<br/>cause, confirm step, fix, owner, risk, rollback, success test"]
    P --> H{Human approves?}
    H -->|yes| T[Ticket / runbook to owning team]
    H -->|edit / no| A
    T --> V["Part 1 checks the success test live"]
    V -->|resolved| K[(Knowledge base: what worked)]
    V -->|not resolved| A
```

### 3b. Deep level

```mermaid
flowchart TD
    TR{"Trigger"} -->|"new or escalated incident ≥ high"| CTX
    TR -->|"operator clicks 'Explain & fix'"| CTX
    CTX["Context pack (masked)<br/>• incident JSON + evidence frame refs<br/>• catalog entry: causes, confirm steps, standard fix, owner<br/>• control comparison + blast radius + timers<br/>• similar past incidents + outcomes<br/>• site inventory: AP groups, WLAN profiles, AAA servers (if available)<br/>• change calendar"] --> LOOP
    subgraph LOOP["Agent loop (Claude, tool use)"]
        direction TB
        L1["1 Restate facts; no new claims without evidence"] --> L2["2 Hypotheses from catalog causes + history"]
        L2 --> L3["3 For each: supporting / refuting header evidence<br/>tools: get_timeline, query_frames, compare_control, catalog_lookup"]
        L3 --> L4["4 Pick the check that separates the top 2 hypotheses<br/>(e.g. 'RADIUS logs: are requests arriving?')"]
        L4 --> L5["5 Fix steps + owner + risk + rollback"]
        L5 --> L6["6 Success criteria Part 1 can measure<br/>(e.g. EAP-04 count = 0 and EAP success > 95% for 10 min)"]
    end
    LOOP --> G["Guardrails<br/>• read-only tools only; never touches APs/controllers/RADIUS<br/>• every claim cites evidence ids<br/>• codes validated against ieee_codes.json<br/>• identifiers stay masked<br/>• JSON schema validation of output"]
    G --> CONF{confidence ≥ 0.6?}
    CONF -->|no| ASK["Return 'needs human' with the missing fact to collect"]
    CONF -->|yes| OUT["fix_proposal.json<br/>root_cause, confidence, confirm_steps, fix_steps,<br/>owner, risk, rollback, success_criteria, evidence"]
    OUT --> UI["Dashboard: proposal next to the incident"]
    ASK --> UI
    UI --> HUM{Engineer decision}
    HUM -->|approve| TK["Ticket for owner team (AAA / network / device)"]
    HUM -->|edit| LOOP
    HUM -->|reject + reason| FB
    TK --> WATCH["Part 1 watches success criteria in real time"]
    WATCH -->|met| RES["Incident resolved; store outcome"] --> FB[(Feedback / knowledge base)]
    WATCH -->|not met after window| LOOP
```

---

## 4. Part 3: catalog of all errors + learning the unknown ones

### 4a. High level

```mermaid
flowchart LR
    E[/"Every frame, sequence and metric"/] --> MT{"In the error catalog?"}
    MT -->|yes| KNOWN["Known problem → Part 1 incident → Part 2 fix"]
    MT -->|no| OTH[("OTHER store<br/>unknown_events.jsonl")]
    OTH --> AG["Discovery AI agent<br/>cluster, investigate, name it"]
    AG --> DR["Draft entry: name, meaning, signature,<br/>detection rule, look-alike, causes, fix, owner"]
    DR --> BT["Backtest on stored data"]
    BT --> HR{Human review}
    HR -->|approve| CAT[("Error catalog v+1")]
    HR -->|reject| OTH
    CAT --> MT
```

### 4b. Deep level

```mermaid
flowchart TD
    subgraph CAPTURE["Capture unknowns (inside Part 1, real time)"]
        U1["OTHER-CODE: reason/status/EAP code not mapped<br/>(reserved, vendor-specific)"]
        U2["OTHER-SEQ: episode state machine hit an undefined transition"]
        U3["OTHER-STAT: metric z-score > 4 vs rolling baseline, no detector fired"]
    end
    U1 --> REC
    U2 --> REC
    U3 --> REC
    REC["Unknown event record<br/>id, time, sensor, masked ids, frame fields,<br/>±10 s timeline, co-occurring incidents, metrics"] --> STORE[("unknown_events.jsonl / table")]
    STORE --> SCHED{"Run discovery when<br/>cluster ≥ 20 events, or severity hint high, or hourly"}
    SCHED --> CL["1 Cluster by signature<br/>(code, transition, metric, sender role, device class)"]
    CL --> INV["2 Investigate each cluster (Claude, read-only tools)<br/>timelines, IEEE code text, related catalog entries, change log"]
    INV --> DEC{"3 Variant of an existing entry?"}
    DEC -->|yes| EXT["Propose extending that entry<br/>(new code, new signature variant)"]
    DEC -->|no| NEW["Propose new entry in catalog schema"]
    EXT --> RULE
    NEW --> RULE["4 Detection rule in safe rule DSL (JSON, no free code)<br/>match fields + window + group_by + threshold"]
    RULE --> VAL["5 Validate<br/>• schema + unique id<br/>• every code exists in ieee_codes.json<br/>• backtest: fires on the cluster, not elsewhere<br/>• false-positive estimate on healthy periods"]
    VAL -->|fails| INV
    VAL -->|passes| REV{"6 Human review<br/>(network SME)"}
    REV -->|approve| MERGE["7 Merge: catalog version bump + changelog"]
    REV -->|edit| RULE
    REV -->|reject| LBL["Label cluster 'benign/noise' so it is not raised again"]
    MERGE --> HOT["8 Hot-reload detectors in Part 1"]
    HOT --> RECL["9 Re-classify stored OTHER events with the new entry"]
    RECL --> P2L["10 New entry's causes + fix feed the Part 2 agent"]
```
