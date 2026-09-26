"""Read-only tools shared by the Part 2 fix agent and the Part 3 discovery agent. Masked data only."""

from __future__ import annotations

import json
import re

from .. import config
from ..engine import Engine
from ..views import device_story, incident_dict

MAC_RE = re.compile(r"\b[0-9a-f]{2}(:[0-9a-f]{2}){5}\b", re.I)
HISTORY = config.OUT_DIR / "fix_history.jsonl"


def _find_device(e: Engine, ref: str) -> str | None:
    if ref in e.devices:
        return ref
    for d in e.devices.values():
        if e.alias_dev(d.id) == ref or d.id.startswith(ref.split("-")[-1]):
            return d.id
    return None


def get_incident(e: Engine, incident_id: str) -> dict:
    inc = e.inc.items.get(incident_id)
    if not inc:
        return {"error": f"no incident {incident_id}"}
    d = incident_dict(e, inc, full=True)
    d["children_list"] = d["children_list"][:15]
    return d


def get_device_timeline(e: Engine, device: str, limit: int = 40) -> dict:
    did = _find_device(e, device)
    if not did:
        return {"error": f"no device {device}"}
    s = device_story(e, did)
    s["story"] = s["story"][: max(1, min(limit, 120))]
    return s


def query_frames(e: Engine, kind: str | None = None, reason: int | None = None, status: int | None = None,
                 sensor: int | None = None, t_from: float | None = None, t_to: float | None = None, limit: int = 30) -> dict:
    out = []
    total = 0
    for f in e.frame_log:
        if kind and f.kind != kind:
            continue
        if reason is not None and f.reason != reason:
            continue
        if status is not None and f.status != status:
            continue
        if sensor is not None and f.s != sensor:
            continue
        if t_from is not None and f.t < t_from:
            continue
        if t_to is not None and f.t > t_to:
            continue
        total += 1
        if len(out) < max(1, min(limit, 50)):
            out.append({"evidence_id": f"S{f.s}:{f.n}", "t": round(f.t, 3), "kind": f.kind, "sender": f.sender,
                        "device": e.alias_dev(f.client), "ap": e.alias_ap(f.ap), "network": f.net, "reason": f.reason,
                        "status": f.status, "eap_code": f.eap_code, "eap_type": f.eap_type, "msgnr": f.msgnr,
                        "synthetic": f.synthetic})
    return {"total_matching": total, "frames": out}


def compare_control(e: Engine, incident_id: str) -> dict:
    inc = e.inc.items.get(incident_id)
    if not inc:
        return {"error": f"no incident {incident_id}"}
    from ..views import control
    per_net = {n: dict(c) for n, c in e.net_stats().items() if n != "?"}
    return {"incident_network": inc.net, "control_networks_on_same_aps": control(e, inc) if inc.aps else [],
            "all_networks": per_net}


def catalog_lookup(e: Engine, ref: str) -> dict:
    m = re.fullmatch(r"(reason|status)[:\s]*(\d+)", ref.strip().lower())
    if m:
        kind, code = m.group(1), int(m.group(2))
        cid = e.cat.for_code(kind, code)
        return {"code": f"{kind} {code}", "ieee_text": e.cat.code_text(kind, code), "catalog_entry": cid,
                "entry": e.cat.entry(cid)}
    ent = e.cat.entry(ref.strip().upper())
    return ent or {"error": f"no catalog entry {ref}", "known_ids": sorted(e.cat.entries)[:120]}


def search_history(e: Engine, catalog_id: str) -> dict:
    items = []
    if HISTORY.exists():
        for line in HISTORY.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("catalog_id") == catalog_id:
                items.append(rec)
    return {"catalog_id": catalog_id, "past": items[-10:]}


TOOLS = {
    "get_incident": (get_incident, "Full masked incident with children, evidence, catalog entry, signature and control comparison.",
                     {"incident_id": {"type": "string"}}, ["incident_id"]),
    "get_device_timeline": (get_device_timeline, "Ordered join/login/leave steps of one device (alias like 'laptop-3f9a' or id).",
                            {"device": {"type": "string"}, "limit": {"type": "integer"}}, ["device", "limit"]),
    "query_frames": (query_frames, "Search management/security frames. Filters are optional; use null for unused ones.",
                     {"kind": {"type": ["string", "null"], "enum": ["auth", "assoc_resp", "assoc_req", "reassoc_resp", "deauth", "disassoc",
                                                                    "eap", "eapol_key", "action", "data", "null", None]},
                      "reason": {"type": ["integer", "null"]}, "status": {"type": ["integer", "null"]},
                      "sensor": {"type": ["integer", "null"]}, "t_from": {"type": ["number", "null"]},
                      "t_to": {"type": ["number", "null"]}, "limit": {"type": "integer"}},
                     ["kind", "reason", "status", "sensor", "t_from", "t_to", "limit"]),
    "compare_control": (compare_control, "Join success of the other networks on the same access points (control group).",
                        {"incident_id": {"type": "string"}}, ["incident_id"]),
    "catalog_lookup": (catalog_lookup, "Look up a catalog entry by id (e.g. 'EAP-01') or an IEEE code ('reason 23', 'status 17').",
                       {"ref": {"type": "string"}}, ["ref"]),
    "search_history": (search_history, "Past fix proposals and outcomes for a catalog id.",
                       {"catalog_id": {"type": "string"}}, ["catalog_id"]),
}


def tool_specs(names=None) -> list[dict]:
    specs = []
    for name, (_, desc, props, req) in TOOLS.items():
        if names and name not in names:
            continue
        specs.append({"name": name, "description": desc, "strict": True,
                      "input_schema": {"type": "object", "properties": props, "required": req, "additionalProperties": False}})
    return specs


def run_tool(e: Engine, name: str, args: dict) -> str:
    if name not in TOOLS:
        return json.dumps({"error": f"unknown tool {name}"})
    fn = TOOLS[name][0]
    try:
        out = json.dumps(fn(e, **args), default=str)
    except TypeError as exc:
        return json.dumps({"error": f"bad arguments: {exc}"})
    if MAC_RE.search(out):
        return json.dumps({"error": "tool output blocked: contained a raw MAC"})
    return out[:20000]
