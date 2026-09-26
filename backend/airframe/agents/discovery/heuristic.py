"""Offline (no Claude credentials) catalog-entry draft, built from the cluster signature alone."""

from __future__ import annotations

from ...engine import Engine


def build(e: Engine, c: dict) -> dict:
    code, field = c["code"], c["what"]
    ieee = c.get("ieee_text") or ""
    undefined = "not defined" in ieee
    kinds = [c["frame_kind"]] if c["frame_kind"] and c["frame_kind"] != "metric" else []
    is_reason = field == "reason"
    name = (f"{'Disconnect' if is_reason else 'Refusal'} with {'undefined' if undefined else 'unmapped'} "
            f"{field} code {code}") if code is not None else f"Unexpected {c['kind'].split('-')[1].lower()}: {field}"
    return {
        "extends": None, "category": "SESS" if is_reason else ("ASSOC" if field == "status" else "SENS"),
        "name": name,
        "plain": (f"{'Access points' if c['sender'] == 'ap' else 'Devices'} send {c['frame_kind']} frames with "
                  f"{field} code {code}, which {'is not defined in the Wi-Fi standard (vendor-specific)' if undefined else 'the catalog did not map'}. "
                  f"Seen {c['count']} times on {len(c['sensors'])} sensor(s)."),
        "signature": f"{c['frame_kind']} from {c['sender']} with {field} {code}",
        "normal_lookalike": "A single occurrence during a firmware upgrade or reboot.",
        "default_severity": "medium", "likely_causes": ["vendor-specific controller behaviour", "firmware bug or new feature"],
        "confirm_outside_headers": [f"Vendor documentation / controller logs for {field} code {code}"],
        "standard_fix": [f"Identify the vendor meaning of {field} {code} and map it to an existing entry or keep this one"],
        "owner": "network", "reason_codes": [code] if is_reason and code is not None else [],
        "status_codes": [code] if field == "status" and code is not None else [],
        "vendor_specific_codes": undefined,
        "rule": {"match": {"kind": kinds, "reason": [code] if is_reason and code is not None else [],
                           "status": [code] if field == "status" and code is not None else [],
                           "sender": [c["sender"]] if c["sender"] else []},
                 "group_by": ["device"], "window_s": 300, "min_count": 1},
        "reasoning": "Offline heuristic: drafted from the cluster signature and the IEEE code table.",
    }
