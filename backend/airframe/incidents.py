"""Correlator: detections -> de-duplicated incidents, root grouping, causal links, lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .catalog import Catalog

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}
LOGIN_FAMILY = {"EAP-01", "EAP-02", "EAP-03", "EAP-04", "KEY-01", "KEY-02", "KEY-03"}
ROOT_CHILDREN = LOGIN_FAMILY | {"SESS-01", "SESS-02"}


@dataclass
class Detection:
    cid: str
    t: float
    scope: str                    # device | ap | sensor | site
    key: str                      # device id / ap id / sensor id / "site"
    sensor: int | None = None
    ap: str | None = None
    device: str | None = None
    net: str | None = None
    channel: int | None = None
    evidence: tuple | None = None  # (sensor, n, what)
    metrics: dict = field(default_factory=dict)
    confidence: float = 0.8
    severity: str | None = None


@dataclass
class Incident:
    id: str
    cid: str
    scope: str
    key: str
    title: str
    severity: str
    first_t: float
    last_t: float
    confidence: float
    net: str | None = None
    count: int = 0
    status: str = "open"
    devices: set = field(default_factory=set)
    aps: set = field(default_factory=set)
    sensors: set = field(default_factory=set)
    channels: set = field(default_factory=set)
    evidence: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    parent: str | None = None
    children: list = field(default_factory=list)
    is_root: bool = False


class IncidentManager:
    def __init__(self, catalog: Catalog, on_event):
        self.cat = catalog
        self.on_event = on_event
        self.items: dict[str, Incident] = {}
        self.by_key: dict[tuple, str] = {}
        self._seq = 0
        self.first_root_t: float | None = None

    def _new_id(self) -> str:
        self._seq += 1
        return f"INC-{self._seq:04d}"

    def add(self, d: Detection, title: str) -> Incident:
        k = (d.cid, d.key)
        inc = self.items.get(self.by_key.get(k, ""))
        if inc is None or d.t - inc.last_t > config.REOPEN_WITHIN_S:
            entry = self.cat.entry(d.cid) or {}
            inc = Incident(id=self._new_id(), cid=d.cid, scope=d.scope, key=d.key, title=title,
                           severity=d.severity or entry.get("default_severity", "medium"), first_t=d.t, last_t=d.t,
                           confidence=d.confidence, net=d.net)
            self.items[inc.id] = inc
            self.by_key[k] = inc.id
            self._attach_to_root(inc)
            self.on_event("incident_opened", inc, d.t)
        else:
            if inc.status != "open":
                inc.status = "open"
                self.on_event("incident_reopened", inc, d.t)
            inc.title = title
        inc.count += 1
        inc.last_t = max(inc.last_t, d.t)
        inc.confidence = max(inc.confidence, d.confidence)
        for s, v in ((inc.devices, d.device), (inc.aps, d.ap), (inc.sensors, d.sensor), (inc.channels, d.channel)):
            if v is not None:
                s.add(v)
        if d.net and not inc.net:
            inc.net = d.net
        if d.evidence and len(inc.evidence) < 12:
            inc.evidence.append(d.evidence)
        for mk_, mv in d.metrics.items():
            if mk_ == "per_channel":
                inc.metrics.setdefault("per_channel", {}).update(mv)
            else:
                inc.metrics[mk_] = mv
        if d.cid in LOGIN_FAMILY and d.scope == "device":
            self._maybe_root(d)
        if inc.parent:
            self._touch_parent(inc)
        return inc

    # ---- root grouping ----
    def _maybe_root(self, d: Detection) -> None:
        recent = [i for i in self.items.values()
                  if i.cid in LOGIN_FAMILY and i.scope == "device" and i.net == d.net
                  and d.t - i.last_t <= config.ROOT_WINDOW_S]
        aps = set().union(*(i.aps for i in recent)) if recent else set()
        chans = set().union(*(i.channels for i in recent)) if recent else set()
        if len(aps) < config.ROOT_MIN_APS and len(chans) < 2:
            return
        rk = ("INFRA-01", f"net:{d.net}")
        root = self.items.get(self.by_key.get(rk, ""))
        if root is None:
            entry = self.cat.entry("INFRA-01") or {}
            root = Incident(id=self._new_id(), cid="INFRA-01", scope="site", key=f"net:{d.net}", title="",
                            severity=entry.get("default_severity", "critical"), first_t=d.t, last_t=d.t,
                            confidence=0.7, net=d.net, is_root=True)
            self.items[root.id] = root
            self.by_key[rk] = root.id
            if self.first_root_t is None:
                self.first_root_t = d.t
            self.on_event("incident_opened", root, d.t)
        for i in self.items.values():
            if i.scope == "device" and i.cid in ROOT_CHILDREN and i.net == d.net and i.parent is None and i.id != root.id:
                self._link(root, i)
        self._refresh_root(root, d.t)

    def _attach_to_root(self, inc: Incident) -> None:
        if inc.scope != "device" or inc.cid not in ROOT_CHILDREN:
            return
        root = self.items.get(self.by_key.get(("INFRA-01", f"net:{inc.net}"), ""))
        if root:
            self._link(root, inc)

    def link_symptom(self, inc: Incident, overlap_devices: set) -> None:
        """Attach a site-level symptom (e.g. probe storm) to the root whose devices overlap it most."""
        best, best_share = None, 0.0
        for r in self.items.values():
            if r.is_root and r.status == "open" and overlap_devices:
                share = len(r.devices & overlap_devices) / len(overlap_devices)
                if share > best_share:
                    best, best_share = r, share
        if best and best_share >= 0.3 and inc.parent is None:
            self._link(best, inc)
            inc.metrics["share_of_devices_in_root"] = round(best_share, 2)

    def _link(self, root: Incident, child: Incident) -> None:
        child.parent = root.id
        if child.id not in root.children:
            root.children.append(child.id)

    def _touch_parent(self, inc: Incident) -> None:
        root = self.items.get(inc.parent)
        if root:
            self._refresh_root(root, inc.last_t)

    def _refresh_root(self, root: Incident, t: float) -> None:
        kids = [self.items[c] for c in root.children]
        login = [k for k in kids if k.scope == "device"]
        root.devices = set().union(*(k.devices for k in login)) if login else set()
        root.aps = set().union(*(k.aps for k in login)) if login else set()
        root.sensors = set().union(*(k.sensors for k in kids)) if kids else set()
        root.channels = set().union(*(k.channels for k in kids)) if kids else set()
        root.last_t = max(root.last_t, t)
        root.count = sum(k.count for k in login)
        root.confidence = round(min(0.95, 0.6 + 0.03 * len(root.aps) + (0.05 if len(root.sensors) > 1 else 0)), 2)
        root.severity = "critical" if len(root.devices) >= 10 else "high"
        framed = [e for k in login for e in k.evidence if e[1] is not None]
        unframed = [e for k in login for e in k.evidence if e[1] is None]
        root.evidence = (framed[:6] + unframed[:6])[:12]
        if root.status != "open":
            root.status = "open"

    # ---- lifecycle ----
    def resolve_stale(self, t: float) -> None:
        for inc in self.items.values():
            if inc.status == "open" and t - inc.last_t > config.RESOLVE_AFTER_S:
                if inc.is_root and any(self.items[c].status == "open" for c in inc.children):
                    continue
                inc.status = "resolved"
                self.on_event("incident_resolved", inc, t)

    def top_level(self) -> list[Incident]:
        tops = [i for i in self.items.values() if i.parent is None]
        return sorted(tops, key=lambda i: (i.status != "open", SEVERITY_RANK.get(i.severity, 9), -len(i.devices), i.first_t))
