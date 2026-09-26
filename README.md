# Airframe: live Wi-Fi diagnostics from header-only captures

Finds **what** is wrong on the air and **where** (Part 1, real time), proposes **how to fix it** (Part 2, AI agent), and
**learns new error types** from anything it cannot match (Part 3, error catalog + discovery agent).

```
hackaton/
  backend/     Python + FastAPI engine, agents, tests   (package: backend/airframe)
  frontend/    React + TypeScript + Vite dashboard
  catalog/     error catalog (JSON + generator)
  json_full/   converted captures (python convert_full.py)
  out/         incidents.json, unknown_events.jsonl, fix_history.jsonl
```

## Run the demo

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
python convert_full.py                                  # once: pcaps -> json_full/ (~100 s, needs Wireshark/tshark)
cd frontend; npm install; npm run build; cd ..           # once: builds the dashboard into frontend/dist
cd backend; ..\.venv\Scripts\python.exe -m airframe serve
```

Open http://127.0.0.1:8000. The replay starts at 10× speed; use the header to pause, change speed (1× to Max) or restart.

- **Overview**: the headline problem in plain words, KPIs, login outcomes and probe storm over time, live events.
- **Incidents**: one line per real problem (de-duplicated across sensors), full evidence, control group, error-catalog guidance, and **"Explain & propose fix"** (Part 2) with approve/reject and a success test measured live.
- **Devices**: every client and its login sequence, frame by frame.
- **Air & sensors**: sensor coverage, beacon airtime and unacknowledged replies per channel, access point × network matrix, data-quality flags.
- **Learning (Part 3)**: unmatched events (OTHER), clusters, drafted catalog entries with validation and back-test, approve to grow the catalog. The captures contain no unknown codes, so a clearly-labelled synthetic injection demonstrates the loop.

## AI agents (Parts 2 and 3)

Both agents (the Part 2 fix proposal and the Part 3 catalog-entry draft) share the same read-only
tools and pick a provider automatically, in this order:

1. **OpenRouter, DeepSeek** (`deepseek/deepseek-v4.1-flash` by default) - used when `OPENROUTER_API_KEY` is set. Override the model with `AIRFRAME_OPENROUTER_MODEL`. Implementation: `backend/airframe/agents/llm_loop_openrouter.py` (the tool-call loop, over plain `httpx` against OpenRouter's OpenAI-compatible Chat Completions API) plus `agents/fix_agent/openrouter_backend.py` and `agents/discovery/openrouter_backend.py`.
2. **Claude** (`claude-opus-5` by default) - used when `ANTHROPIC_API_KEY` is set and no OpenRouter key is present. Override the model with `AIRFRAME_MODEL`. Implementation: `agents/llm_loop.py`, `agents/fix_agent/claude_backend.py`, `agents/discovery/claude_backend.py`.
3. **Offline** catalog playbook / heuristic - used when neither key is set. Implementation: `agents/fix_agent/playbook.py`, `agents/discovery/heuristic.py`.

The dashboard always shows which one actually answered (including a note if a provider errored and
the offline fallback stepped in). Force a specific provider with `AIRFRAME_AGENT_MODE=openrouter|claude|offline`
instead of auto-detecting from whichever keys are set.

Agents never change anything: tools are read-only, every claim cites evidence, codes are checked
against the IEEE tables, and identifiers stay masked. Every provider's output goes through the same
`validate()` guardrails (`agents/fix_agent/validate.py`, `agents/discovery/validate.py`) before it's
shown or adopted, and falls back to offline automatically if it fails them.

## Other commands

All run from `backend/` unless noted.

| Command | What it does |
|---|---|
| `..\.venv\Scripts\python.exe -m airframe batch` | Replay all 30 min at full speed (~14 s) and write `out/incidents.json` |
| `..\.venv\Scripts\python.exe -m pytest -q tests` | Unit, golden (verified facts) and end-to-end API tests |
| `..\.venv\Scripts\python.exe tests\ui_check.py [out_dir] [--dark]` | Drives the running dashboard in Edge and saves screenshots |
| `python ..\verify_findings.py` (repo root) | Re-computes every number in the v3 report (36 checks) |
| `python ..\realtime_bench.py 1 60` (repo root) | Live-pipe latency benchmark |
| `cd frontend; npm run dev` | Dashboard dev server with hot reload (proxies `/api` to port 8000) |

## Privacy

MAC addresses are replaced by keyed hashes in the normaliser before anything else sees them; network names become `ENT-1` (802.1X) / `PSK-1` (pre-shared key). The key is `AIRFRAME_SALT` or a random secret generated into `.airframe_salt` at the repo root: keep that file private and out of version control.
