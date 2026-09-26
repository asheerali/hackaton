"""Safe JSON rule language for catalog detection rules (Part 3). Interpreted, never executed as code."""

from __future__ import annotations

from collections import defaultdict

MATCH_KEYS = {"kind", "reason", "status", "eap_code", "eap_type", "msgnr", "sender", "net", "retry", "sensor", "synthetic"}
GROUP_KEYS = {"device": "client", "ap": "ap", "sensor": "s", "network": "net"}
OPS = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "==": lambda a, b: a == b, "<=": lambda a, b: a <= b}


def validate(rule: dict) -> list[str]:
    errs = []
    if not isinstance(rule, dict):
        return ["rule must be an object"]
    m = rule.get("match")
    if not isinstance(m, dict) or not m:
        errs.append("match must be a non-empty object")
    else:
        for k, v in m.items():
            if k not in MATCH_KEYS:
                errs.append(f"unknown match key '{k}' (allowed: {sorted(MATCH_KEYS)})")
            if not isinstance(v, (list, str, int, bool)):
                errs.append(f"match value for '{k}' must be a list or scalar")
    for g in rule.get("group_by", []):
        if g not in GROUP_KEYS:
            errs.append(f"unknown group_by '{g}' (allowed: {sorted(GROUP_KEYS)})")
    w = rule.get("window_s")
    if not isinstance(w, (int, float)) or not 1 <= w <= 3600:
        errs.append("window_s must be a number between 1 and 3600")
    th = rule.get("threshold", {}).get("count")
    if not isinstance(th, dict) or len(th) != 1 or next(iter(th)) not in OPS or not isinstance(next(iter(th.values())), int):
        errs.append("threshold must be {'count': {'>=': <int>}} (ops: >=, >, ==, <=)")
    return errs


def _matches(frame, match: dict) -> bool:
    for k, v in match.items():
        fv = getattr(frame, "s" if k == "sensor" else k, None)
        vals = v if isinstance(v, list) else [v]
        if fv not in vals:
            return False
    return True


def evaluate(rule: dict, frames) -> list[dict]:
    """Return one hit per group whose matching-frame count within any window meets the threshold."""
    groups = defaultdict(list)
    keys = [GROUP_KEYS[g] for g in rule.get("group_by", [])]
    for f in frames:
        if _matches(f, rule["match"]):
            groups[tuple(getattr(f, k, None) for k in keys)].append(f)
    (op, n), = rule["threshold"]["count"].items()
    hits = []
    w = rule["window_s"]
    for g, fs in groups.items():
        fs.sort(key=lambda f: f.t)
        lo = 0
        best = 0
        for hi in range(len(fs)):
            while fs[hi].t - fs[lo].t > w:
                lo += 1
            best = max(best, hi - lo + 1)
        if OPS[op](best, n):
            hits.append({"group": dict(zip(rule.get("group_by", []), g)), "max_in_window": best,
                         "frames": [(f.s, f.n) for f in fs[:5]], "first_t": fs[0].t})
    return hits
