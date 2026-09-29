"""Streaming engine (Part 1): frames in, detections/incidents/snapshots out. Event time = per-sensor capture time."""

from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from . import config
from .catalog import Catalog
from .decode import Frame
from .incidents import Detection, Incident, IncidentManager

NORMAL_LEAVE_REASONS = {3, 8, 36}


def channel_of(freq: int | None) -> int | None:
    if not freq:
        return None
    if 2412 <= freq <= 2472:
        return (freq - 2407) // 5
    if freq == 2484:
        return 14
    if 5000 <= freq <= 5925:
        return (freq - 5000) // 5
    if 5955 <= freq <= 7115:
        return (freq - 5950) // 5
    return None


def beacon_airtime_us(length: int | None, rate: float | None) -> float:
    if not length or not rate:
        return 0.0
    return (192.0 if rate < 6 else 20.0) + length * 8.0 / rate


@dataclass
class BssidStat:
    bssid: str
    ap: str
    net: str | None
    akm: int | None
    sensor: int
    first_t: float
    last_t: float
    count: int = 0
    rssi_min: int = 999
    rssi_max: int = -999
    rate: float | None = None

    def loss(self) -> float:
        expected = (self.last_t - self.first_t) / 0.1024 + 1
        return max(0.0, 1 - self.count / expected) if expected > 1 else 0.0


@dataclass
class SensorState:
    s: int
    freqs: Counter = field(default_factory=Counter)
    frames: int = 0
    first_t: float | None = None
    last_t: float = 0.0
    last_beacon_t: float | None = None
    bssids: set = field(default_factory=set)

    @property
    def channel(self) -> int | None:
        return channel_of(self.freqs.most_common(1)[0][0]) if self.freqs else None


@dataclass
class Bucket:
    frames: int = 0
    beacons: int = 0
    beacon_air_us: float = 0.0
    probe_resp: int = 0
    probe_resp_retry: int = 0
    probe_req: int = 0
    other_frames: int = 0
    other_retry: int = 0
    joins: int = 0
    connected: int = 0
    kicks: int = 0
    fast_rejects: int = 0
    leaves: int = 0
    eap_req: int = 0


@dataclass
class Attempt:
    dev: str
    ap: str | None
    bssid: str | None
    net: str | None
    s: int
    t0: float
    eap_req: list = field(default_factory=list)
    answered: bool = False
    method: bool = False
    success: bool = False
    failure: bool = False
    m1: list = field(default_factory=list)
    m3: bool = False
    m3_n: int | None = None
    ba: bool = False
    data: bool = False
    end_t: float | None = None
    outcome: str | None = None
    reported: set = field(default_factory=set)

    @property
    def connected(self) -> bool:
        return self.m3 or self.success or self.data


@dataclass
class Device:
    id: str
    cclass: str
    first_t: float
    last_t: float = 0.0
    net: str | None = None
    ap: str | None = None
    sensors: set = field(default_factory=set)
    attempts: int = 0
    connected_n: int = 0
    kicks: int = 0
    fast_rejects: int = 0
    answered: bool = False
    state: str = "seen"
    failures: deque = field(default_factory=deque)
    reject2: deque = field(default_factory=deque)
    probe_ts: deque = field(default_factory=deque)
    last_leave: tuple | None = None
    story: list = field(default_factory=list)


class Engine:
    def __init__(self, catalog: Catalog, masker, out_dir=None):
        self.cat = catalog
        self.mk = masker
        self.out_dir = out_dir
        self.t = 0.0
        self.frames = 0
        self.sensors: dict[int, SensorState] = {}
        self.bssids: dict[str, BssidStat] = {}
        self.aps: dict[str, dict] = {}
        self.devices: dict[str, Device] = {}
        self.open_attempts: dict[str, Attempt] = {}
        self.buckets: dict[int, dict[int, Bucket]] = defaultdict(dict)
        self.feed: deque = deque(maxlen=200)
        self.unknown: list[dict] = []
        self.unknown_frame_by_id: dict[str, Frame] = {}
        self.observations: list[dict] = []
        self.frame_log: list[Frame] = []
        self.reask: dict[str, list] = defaultdict(list)
        self.kick_delay: dict[str, list] = defaultdict(list)
        self.leaves: deque = deque()
        self.flags: dict[str, dict] = {}
        self._reported: set = set()
        self._next_eval = 1.0
        self._det_times: dict[int, float] = {}
        self.inc = IncidentManager(catalog, self._incident_event)
        self.first_fail_join_t: float | None = None
        self.attempts_all: list[Attempt] = []

    # ------------------------------------------------------------------ helpers
    def _bucket(self, s: int, t: float) -> Bucket:
        i = int(t // config.BUCKET_S)
        b = self.buckets[s].get(i)
        if b is None:
            b = self.buckets[s][i] = Bucket()
        return b

    def _device(self, f: Frame) -> Device | None:
        if not f.client:
            return None
        d = self.devices.get(f.client)
        if d is None:
            d = self.devices[f.client] = Device(id=f.client, cclass=f.cclass or "device", first_t=f.t)
        d.last_t = max(d.last_t, f.t)
        d.sensors.add(f.s)
        return d

    def alias_dev(self, dev: str | None) -> str | None:
        d = self.devices.get(dev or "")
        return f"{d.cclass}-{d.id[:4]}" if d else None

    @staticmethod
    def alias_ap(ap: str | None) -> str | None:
        return f"AP-{ap[2:6]}" if ap else None

    def _story(self, d: Device, f: Frame, step: str, detail: str = "") -> None:
        if len(d.story) < 600:
            d.story.append({"t": round(f.t, 3), "s": f.s, "n": f.n, "step": step, "by": f.sender,
                            "ap": self.alias_ap(f.ap), "detail": detail})

    def _feed(self, t: float, kind: str, text: str, severity: str = "info", ref: str | None = None) -> None:
        self.feed.append({"t": round(t, 2), "kind": kind, "text": text, "severity": severity, "ref": ref})

    def _incident_event(self, kind: str, inc: Incident, t: float) -> None:
        verb = {"incident_opened": "opened", "incident_reopened": "reopened", "incident_resolved": "resolved"}[kind]
        if inc.parent is None:
            self._feed(t, kind, f"{inc.id} {verb}: {inc.title or inc.cid}", inc.severity if verb != "resolved" else "info", inc.id)

    def _detect(self, d: Detection) -> None:
        self._det_times[d.sensor or 0] = d.t
        inc = self.inc.add(d, self._title(d))
        pc = inc.metrics.get("per_channel")
        if pc:
            lo, hi = min(pc.values()), max(pc.values())
            rng = f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"
            n = f"{len(pc)} channel{'s' if len(pc) > 1 else ''}"
            inc.title = {
                "RF-01": f"High retries: {rng}% of {inc.metrics.get('frame_type')} unacknowledged on {n}",
                "RF-03": f"Beacon overhead {rng}% of airtime on {n}",
                "RF-04": f"Beacons sent at {rng} Mbit/s on {n} (minimum 12 recommended)",
            }.get(inc.cid, inc.title)
        if inc.is_root is False and inc.parent:
            root = self.inc.items[inc.parent]
            root.title = self._title_root(root)

    def _unknown(self, kind: str, f: Frame, detail: dict) -> None:
        d = self.devices.get(f.client or "")
        rec = {"id": f"UNK-{len(self.unknown) + 1:06d}", "kind": kind, "t": round(f.t, 3), "sensor": f.s,
               "channel": self.sensors[f.s].channel, "device": self.alias_dev(f.client), "device_id": f.client,
               "ap": self.alias_ap(f.ap), "net": f.net, "frame_kind": f.kind, "sender": f.sender,
               "detail": detail, "synthetic": f.synthetic,
               "context": {"timeline": (d.story[-10:] if d else []),
                           "open_incidents": [i.id for i in self.inc.top_level() if i.status == "open"][:5]}}
        self.unknown.append(rec)
        self.unknown_frame_by_id[rec["id"]] = f
        self._feed(f.t, "unknown", f"Unmatched event {rec['id']} ({kind}) saved for the catalog-learning agent", "unknown", rec["id"])
        if self.out_dir:
            with (self.out_dir / "unknown_events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")

    def ingest_reclassified(self, event_ids: list[str], catalog_id: str) -> int:
        """Turn events the catalog just learned to recognise into real incidents (re-runs the incident workflow)."""
        n = 0
        for eid in event_ids:
            f = self.unknown_frame_by_id.get(eid)
            if f is None:
                continue
            ch = self.sensors[f.s].channel if f.s in self.sensors else None
            what = f"reclassified by the catalog-learning agent: {f.kind} reason={f.reason} status={f.status} now mapped to {catalog_id}"
            self._detect(Detection(catalog_id, f.t, "device" if f.client else "site", f.client or f"auto:{eid}",
                                   sensor=f.s, ap=f.ap, device=f.client, net=f.net, channel=ch,
                                   evidence=(f.s, f.n, what), confidence=0.7))
            n += 1
        return n

    def _flag(self, key: str, t: float, sensor: int | None = None, text: str = "") -> None:
        """Data-quality flag, one per kind; sensors showing it are accumulated."""
        f = self.flags.setdefault(key, {"t": round(t, 2), "text": text, "sensors": set()})
        if sensor is not None:
            f["sensors"].add(sensor)

    # ------------------------------------------------------------------ titles
    def _title(self, d: Detection) -> str:
        dev, ap, ch = self.alias_dev(d.device), self.alias_ap(d.ap), d.channel
        m = d.metrics
        return {
            "EAP-01": f"Login stalls after 'who are you?' on {d.net} ({dev} at {ap})",
            "EAP-03": f"Login refused by the server ({dev} at {ap})",
            "EAP-04": f"Kicked out: 802.1X authentication failed ({dev} at {ap})",
            "SESS-01": f"Stuck in a join-fail-retry loop ({dev})",
            "SESS-02": f"Fast-rejected by the network, client exclusion suspected ({dev})",
            "KEY-01": f"Key handshake never completes, wrong key suspected ({dev} at {ap})",
            "KEY-02": f"Key handshake stalls after M3 ({dev} at {ap})",
            "DISC-01": f"{m.get('missing')} not offered on {ap}",
            "DISC-02": f"Access point suspected silent ({m.get('between', 'numbering gap')})",
            "DISC-03": f"Probe storm: {m.get('clients')} devices searching non-stop",
            "DISC-06": f"Channel change announced on {ap}",
            "RF-01": f"High retries on ch {ch}: {m.get('share_pct')}% of {m.get('frame_type')} unacknowledged",
            "RF-03": f"Beacon overhead {m.get('airtime_pct')}% of airtime on ch {ch}",
            "RF-04": f"Beacons sent at {m.get('rate')} Mbit/s on ch {ch} (minimum 12 recommended)",
            "SESS-08": f"{m.get('clients')} devices left within {int(config.LEAVE_BURST_WINDOW_S)} s",
            "SENS-01": f"Sensor S{d.sensor} went deaf for {m.get('gap_s')} s",
            "SENS-04": f"Radio values not physically possible on ch {ch} (data quality)",
        }.get(d.cid, f"{(self.cat.entry(d.cid) or {}).get('name', d.cid)} ({dev or ap or ('ch ' + str(ch))})")

    def _title_root(self, r: Incident) -> str:
        return (f"{r.net} login service not answering: {len(r.devices)} devices cannot connect "
                f"on {len(r.aps)} access points")

    # ------------------------------------------------------------------ ingest
    def process(self, f: Frame) -> None:
        if f.t > self.t:
            self.t = f.t
        self.frames += 1
        ss = self.sensors.get(f.s)
        if ss is None:
            ss = self.sensors[f.s] = SensorState(f.s, first_t=f.t)
        ss.frames += 1
        ss.last_t = f.t
        if f.freq:
            ss.freqs[f.freq] += 1
        b = self._bucket(f.s, f.t)
        b.frames += 1
        k = f.kind
        if k == "beacon":
            self._beacon(f, ss, b)
        elif k == "probe_resp":
            b.probe_resp += 1
            b.probe_resp_retry += f.retry
            d = self._device(f)
            if d:
                d.probe_ts.append(f.t)
        elif k == "probe_req":
            b.probe_req += 1
            self._device(f)
        else:
            b.other_frames += 1
            b.other_retry += f.retry
            if k != "ack":
                self.frame_log.append(f)
                self._mgmt(f, b)
        if f.t >= self._next_eval:
            self._evaluate(self.t - config.ALLOWED_LATENESS_S)
            self._next_eval = int(f.t) + 1.0

    def _beacon(self, f: Frame, ss: SensorState, b: Bucket) -> None:
        b.beacons += 1
        b.beacon_air_us += beacon_airtime_us(f.length, f.rate)
        ss.last_beacon_t = f.t
        bs = self.bssids.get(f.bssid)
        if bs is None:
            bs = self.bssids[f.bssid] = BssidStat(f.bssid, f.ap, f.net, f.akm, f.s, f.t, f.t, rate=f.rate)
            ss.bssids.add(f.bssid)
            ap = self.aps.setdefault(f.ap, {"id": f.ap, "nets": {}, "sensors": set(), "first_t": f.t})
            ap["nets"][f.net] = f.bssid
            ap["sensors"].add(f.s)
            if f.freq and f.freq >= 5000 and f.rate is not None:
                ch = channel_of(f.freq)
                if f.rate < 6:
                    self._flag("SENS-04:rate", f.t, sensor=f.s, text=f"Beacons are marked {f.rate:g} Mbit/s on 5 GHz, which is not a valid 5 GHz rate")
                if f.rate < config.MIN_BASIC_RATE_5GHZ:
                    self._detect(Detection("RF-04", f.t, "site", "RF-04", sensor=f.s, channel=ch,
                                           evidence=(f.s, f.n, f"beacon at {f.rate} Mbit/s on ch {ch}"),
                                           metrics={"rate": f.rate, "per_channel": {ch: f.rate}}, confidence=0.9))
        bs.count += 1
        bs.last_t = f.t
        if f.sig is not None:
            bs.rssi_min = min(bs.rssi_min, f.sig)
            bs.rssi_max = max(bs.rssi_max, f.sig)
        if f.csa is not None:
            self._detect(Detection("DISC-06", f.t, "ap", f.ap, sensor=f.s, ap=f.ap, channel=channel_of(f.freq),
                                   evidence=(f.s, f.n, f"CSA to channel {f.csa}"), confidence=0.95))

    # ------------------------------------------------------------------ management / security frames
    def _mgmt(self, f: Frame, b: Bucket) -> None:
        d = self._device(f)
        k = f.kind
        ch = self.sensors[f.s].channel
        if d is None:
            return
        if f.net and f.net != "*":
            d.net = f.net
        if f.ap:
            d.ap = f.ap
        a = self.open_attempts.get(d.id)

        if k == "auth":
            self._story(d, f, f"Auth {f.auth_seq}", f"status {f.status}")
            if f.sender == "ap" and f.status not in (0, None):
                self._code("status", f, d, ch)
        elif k in ("assoc_resp", "reassoc_resp") and f.sender == "ap":
            if f.status in (0, None):
                if a and a.end_t is None:
                    self._close(a, f.t, "superseded")
                net = self._net_of(f)
                a = self.open_attempts[d.id] = Attempt(d.id, f.ap, f.bssid, net, f.s, f.t)
                self.attempts_all.append(a)
                d.attempts += 1
                d.state = "joining"
                d.net = net or d.net
                b.joins += 1
                if d.last_leave and f.t - d.last_leave[0] <= config.ROAM_GAP_S and d.last_leave[1] != f.ap:
                    self.observations.append({"cid": "ROAM-01", "t": f.t, "device": self.alias_dev(d.id)})
                self._story(d, f, "Associated", f"status 0, network {net}")
            else:
                self._story(d, f, "Association refused", f"status {f.status}: {self.cat.code_text('status', f.status)}")
                self._code("status", f, d, ch)
        elif k in ("assoc_req", "reassoc_req"):
            self._story(d, f, "Association request", "")
        elif k == "eap":
            self._eap(f, d, a, b, ch)
        elif k == "eapol_key":
            self._key(f, d, a, ch)
        elif k == "action":
            if a and f.action_cat == 3:
                a.ba = True
        elif k in ("data", "null"):
            if a and not a.data:
                a.data = True
                self._story(d, f, "Data flowing", "protected data seen" if f.to_ds else "AP sends data")
                self._connected(a, d, f)
        elif k in ("deauth", "disassoc"):
            self._leave(f, d, a, b, ch)

    def _net_of(self, f: Frame) -> str | None:
        bs = self.bssids.get(f.bssid or "")
        return bs.net if bs else f.net

    def _eap(self, f: Frame, d: Device, a: Attempt | None, b: Bucket, ch) -> None:
        code, typ = f.eap_code, f.eap_type
        if f.sender == "ap" and code == 1:
            if typ == 1:
                b.eap_req += 1
                self._story(d, f, "EAP: who are you?", "Identity request")
                if a:
                    if a.eap_req:
                        gap = f.t - a.eap_req[-1]
                        if gap > 1:
                            self.reask[a.net or "?"].append(gap)
                    a.eap_req.append(f.t)
            else:
                self._story(d, f, "EAP method round", f"type {typ}")
                if a:
                    a.method = True
        elif f.sender == "client" and code == 2:
            self._story(d, f, "EAP: client answers", "Identity response" if typ == 1 else f"method type {typ}")
            d.answered = True
            if a:
                a.answered = True
                if typ != 1:
                    a.method = True
        elif code == 3:
            self._story(d, f, "EAP success", "")
            if a:
                a.success = True
                self._connected(a, d, f)
        elif code == 4:
            self._story(d, f, "EAP failure", "server refused")
            if a:
                a.failure = True
            self._detect(Detection("EAP-03", f.t, "device", d.id, sensor=f.s, ap=f.ap, device=d.id, net=d.net, channel=ch,
                                   evidence=(f.s, f.n, "EAP Failure"), confidence=0.95))

    def _key(self, f: Frame, d: Device, a: Attempt | None, ch) -> None:
        m = f.msgnr
        self._story(d, f, f"Key message M{m}", "sent by AP" if m in (1, 3) else "sent by device")
        if not a:
            if m in (3, 4):
                self._unknown("OTHER-SEQ", f, {"transition": f"M{m} with no association in progress"})
            return
        if m == 1:
            a.m1.append(f.t)
        elif m == 3:
            if not a.m1:
                self._unknown("OTHER-SEQ", f, {"transition": "M3 without M1 in this attempt"})
            a.m3 = True
            a.m3_n = f.n
            self._connected(a, d, f)
        elif m == 4 and a.m3:
            self._connected(a, d, f)

    def net_stats(self) -> dict[str, Counter]:
        out: dict[str, Counter] = defaultdict(Counter)
        for a in self.attempts_all:
            net = a.net or self._net_of_bssid(a.bssid) or "?"
            out[net]["attempts"] += 1
            out[net]["connected"] += a.outcome == "connected"
        return out

    def _net_of_bssid(self, bssid: str | None) -> str | None:
        bs = self.bssids.get(bssid or "")
        return bs.net if bs else None

    def _connected(self, a: Attempt, d: Device, f: Frame) -> None:
        if a.outcome == "connected":
            return
        a.outcome = "connected"
        d.connected_n += 1
        d.state = "connected"
        self._bucket(f.s, f.t).connected += 1

    def _close(self, a: Attempt, t: float, outcome: str) -> None:
        a.end_t = t
        if a.outcome != "connected":
            a.outcome = outcome
        self.open_attempts.pop(a.dev, None)

    def _leave(self, f: Frame, d: Device, a: Attempt | None, b: Bucket, ch) -> None:
        r = f.reason
        what = f"{'AP' if f.sender == 'ap' else 'device'} sends {f.kind} reason {r}: {self.cat.code_text('reason', r)}"
        self._story(d, f, f"{'Deauth' if f.kind == 'deauth' else 'Disassoc'} reason {r}", what)
        d.last_leave = (f.t, f.ap)
        if f.sender == "client" and r in NORMAL_LEAVE_REASONS:
            b.leaves += 1
            d.state = "left"
            if a:
                self._close(a, f.t, "left")
            self.leaves.append((f.t, d.id, f.s))
            return
        if f.sender == "ap" and r == 23:
            b.kicks += 1
            d.kicks += 1
            d.state = "failing"
            if a:
                self.kick_delay[a.net or "?"].append(f.t - a.t0)
                self._close(a, f.t, "kicked_8021x")
            self._failure(d, f, ch)
            self._detect(Detection("EAP-04", f.t, "device", d.id, sensor=f.s, ap=f.ap, device=d.id, net=d.net, channel=ch,
                                   evidence=(f.s, f.n, what), metrics={"reason": 23}, confidence=0.95))
            return
        if f.sender == "ap" and r == 2:
            b.fast_rejects += 1
            d.fast_rejects += 1
            d.state = "excluded"
            if a:
                self._close(a, f.t, "fast_reject")
            d.reject2.append(f.t)
            while d.reject2 and f.t - d.reject2[0] > config.FAST_REJECT_WINDOW_S:
                d.reject2.popleft()
            if len(d.reject2) >= config.FAST_REJECT_MIN:
                self._detect(Detection("SESS-02", f.t, "device", d.id, sensor=f.s, ap=f.ap, device=d.id, net=d.net,
                                       channel=ch, evidence=(f.s, f.n, what),
                                       metrics={"reason2_in_window": len(d.reject2)}, confidence=0.9))
            self._failure(d, f, ch)
            return
        if a:
            self._close(a, f.t, "disconnected")
        cid = self.cat.for_code("reason", r)
        if cid == "OTHER-CODE":
            self._unknown("OTHER-CODE", f, {"field": "reason", "code": r, "ieee_text": self.cat.code_text("reason", r)})
            return
        if cid in ("SESS-08", "SESS-09"):
            return
        self._detect(Detection(cid, f.t, "device", d.id, sensor=f.s, ap=f.ap, device=d.id, net=d.net, channel=ch,
                               evidence=(f.s, f.n, what), metrics={"reason": r}, confidence=0.85))
        if cid.startswith("KEY") or cid.startswith("EAP"):
            self._failure(d, f, ch)

    def _code(self, kind: str, f: Frame, d: Device, ch) -> None:
        code = f.status
        cid = self.cat.for_code(kind, code)
        if cid == "OTHER-CODE":
            self._unknown("OTHER-CODE", f, {"field": kind, "code": code, "ieee_text": self.cat.code_text(kind, code)})
            return
        if cid == "OK":
            return
        self._detect(Detection(cid, f.t, "device", d.id, sensor=f.s, ap=f.ap, device=d.id, net=d.net, channel=ch,
                               evidence=(f.s, f.n, f"{f.kind} status {code}: {self.cat.code_text(kind, code)}"),
                               metrics={"status": code}, confidence=0.95))

    def _failure(self, d: Device, f: Frame, ch) -> None:
        d.failures.append(f.t)
        if self.first_fail_join_t is None:
            self.first_fail_join_t = f.t
        while d.failures and f.t - d.failures[0] > config.LOOP_WINDOW_S:
            d.failures.popleft()
        if len(d.failures) >= config.LOOP_MIN_FAILURES:
            self._detect(Detection("SESS-01", f.t, "device", d.id, sensor=f.s, ap=f.ap, device=d.id, net=d.net, channel=ch,
                                   evidence=(f.s, f.n, f"failure #{d.attempts} for this device"),
                                   metrics={"failures_in_10min": len(d.failures)}, confidence=0.9))

    # ------------------------------------------------------------------ timers (event time)
    def _evaluate(self, wm: float) -> None:
        for a in list(self.open_attempts.values()):
            dev = self.devices[a.dev]
            ch = self.sensors[a.s].channel
            if a.eap_req and not (a.method or a.success or a.failure or a.m1) and wm - a.eap_req[0] >= config.EAP_STALL_S \
                    and "stall" not in a.reported:
                a.reported.add("stall")
                if self.first_fail_join_t is None:
                    self.first_fail_join_t = a.t0
                dev.state = "failing"
                self._detect(Detection("EAP-01", wm, "device", a.dev, sensor=a.s, ap=a.ap, device=a.dev, net=a.net, channel=ch,
                                       evidence=(a.s, None, f"no EAP method after identity request at t={a.eap_req[0]:.1f}s"
                                                 + ("; device answered" if a.answered else "")),
                                       metrics={"client_answered": a.answered, "identity_requests": len(a.eap_req)},
                                       confidence=0.9 if a.answered else 0.8))
            if len(a.m1) >= 2 and not a.m3 and wm - a.m1[0] >= config.KEY_M1_REPEAT_S and "key1" not in a.reported:
                a.reported.add("key1")
                self._detect(Detection("KEY-01", wm, "device", a.dev, sensor=a.s, ap=a.ap, device=a.dev, net=a.net, channel=ch,
                                       evidence=(a.s, None, f"M1 sent {len(a.m1)} times, no M3"), confidence=0.85))
            if a.m1 and not a.m3 and not a.data and wm - a.m1[0] >= config.KEY_M1_REPEAT_S and "key6" not in a.reported:
                a.reported.add("key6")
                if a.ba:
                    self.observations.append({"cid": "KEY-06", "t": round(wm, 2), "device": self.alias_dev(a.dev),
                                              "ap": self.alias_ap(a.ap),
                                              "text": "M3 not captured, but AP set up Block-Ack: association alive (not a failure)"})
            if wm - a.t0 > config.ATTEMPT_TIMEOUT_S:
                self._close(a, wm, "timeout")
        self._eval_leave_burst(wm)
        if int(wm) % 10 == 0:
            self._eval_windows(wm)
        if wm >= config.DISC_EVAL_AFTER_S and int(wm) % 60 == 0:
            self._eval_coverage(wm)
        self.inc.resolve_stale(wm)

    def _eval_leave_burst(self, wm: float) -> None:
        while self.leaves and wm - self.leaves[0][0] > config.LEAVE_BURST_WINDOW_S:
            self.leaves.popleft()
        devs = {d for _, d, _ in self.leaves}
        burst = getattr(self, "_burst", None)
        if burst and self.leaves and self.leaves[-1][0] - burst["last"] > config.LEAVE_BURST_WINDOW_S:
            self._burst = burst = None
        if len(devs) >= config.LEAVE_BURST_MIN_CLIENTS or burst:
            if not burst:
                self._burst = burst = {"key": f"burst:{self.leaves[0][0]:.0f}", "seen": set(), "last": 0.0}
            for t, d, s in self.leaves:
                if d not in burst["seen"]:
                    burst["seen"].add(d)
                    burst["last"] = t
                    self._detect(Detection("SESS-08", t, "site", burst["key"], sensor=s, device=d,
                                           channel=self.sensors[s].channel,
                                           metrics={"clients": len(burst["seen"])}, confidence=0.9))

    def _eval_windows(self, wm: float) -> None:
        nb = int(config.RETRY_WINDOW_S // config.BUCKET_S)
        cur = int(wm // config.BUCKET_S)
        for s, bk in self.buckets.items():
            win = [bk[i] for i in range(cur - nb, cur) if i in bk]
            if not win:
                continue
            ch = self.sensors[s].channel
            pr = sum(b.probe_resp for b in win)
            prr = sum(b.probe_resp_retry for b in win)
            if pr >= config.RETRY_MIN_FRAMES and prr / pr > config.RETRY_SHARE:
                self._detect(Detection("RF-01", wm, "site", "RF-01:probe", sensor=s, channel=ch,
                                       metrics={"frame_type": "probe replies", "window_s": config.RETRY_WINDOW_S,
                                                "per_channel": {ch: round(100 * prr / pr, 1)}}, confidence=0.9))
            of = sum(b.other_frames for b in win)
            ofr = sum(b.other_retry for b in win)
            if of >= config.RETRY_MIN_FRAMES and ofr / of > config.RETRY_SHARE:
                self._detect(Detection("RF-01", wm, "site", "RF-01:other", sensor=s, channel=ch,
                                       metrics={"frame_type": "other frames", "per_channel": {ch: round(100 * ofr / of, 1)}},
                                       confidence=0.85))
            span = len(win) * config.BUCKET_S * 1e6
            air = sum(b.beacon_air_us for b in win) / span
            if air > config.BEACON_AIRTIME_SHARE:
                self._detect(Detection("RF-03", wm, "site", "RF-03", sensor=s, channel=ch,
                                       metrics={"per_channel": {ch: round(100 * air, 1)}}, confidence=0.6))
            ss = self.sensors[s]
            if ss.last_beacon_t is not None and wm - ss.last_beacon_t > config.SENSOR_DEAF_S:
                self._detect(Detection("SENS-01", wm, "sensor", f"s{s}", sensor=s, channel=ch,
                                       metrics={"gap_s": round(wm - ss.last_beacon_t, 1)}, confidence=0.9))
            self._eval_stat(s, bk, cur, ch, wm)
        storm = [d for d in self.devices.values()
                 if self._probe_rate(d, wm) > config.PROBE_PER_CLIENT_PER_S]
        if len(storm) >= config.PROBE_STORM_MIN_CLIENTS:
            inc = self.inc.add(Detection("DISC-03", wm, "site", "site", metrics={
                "clients": len(storm), "per_client_per_s": round(st.median(self._probe_rate(d, wm) for d in storm), 2)},
                confidence=0.9), "")
            inc.devices |= {d.id for d in storm}
            inc.title = self._title(Detection("DISC-03", wm, "site", "site", metrics={"clients": len(inc.devices)}))
            inc.channels |= {ss.channel for ss in self.sensors.values()}
            self.inc.link_symptom(inc, {d.id for d in storm})

    def _probe_rate(self, d: Device, wm: float) -> float:
        while d.probe_ts and wm - d.probe_ts[0] > config.PROBE_WINDOW_S:
            d.probe_ts.popleft()
        return len(d.probe_ts) / config.PROBE_WINDOW_S

    def _eval_stat(self, s: int, bk: dict, cur: int, ch, wm: float) -> None:
        hist = [bk[i].kicks + bk[i].fast_rejects + bk[i].leaves for i in range(cur - 31, cur - 1) if i in bk]
        last = bk.get(cur - 1)
        if not last or len(hist) < 6:
            return
        v = last.kicks + last.fast_rejects + last.leaves
        mu, sd = st.mean(hist), st.pstdev(hist) or 1.0
        if v >= config.STAT_MIN_COUNT and (v - mu) / sd > config.STAT_ZSCORE and wm - self._det_times.get(s, -1e9) > config.BUCKET_S:
            fake = Frame(s=s, t=wm, n=0, kind="metric")
            self._unknown("OTHER-STAT", fake, {"metric": "disconnects_per_10s", "value": v, "mean": round(mu, 2),
                                               "z": round((v - mu) / sd, 1)})

    def _eval_coverage(self, wm: float) -> None:
        nets_per_ap = {a: set(v["nets"]) for a, v in self.aps.items()}
        if not nets_per_ap:
            return
        count = Counter(n for ns in nets_per_ap.values() for n in ns)
        expected = {n for n, c in count.items() if c / len(nets_per_ap) >= config.NETWORK_EXPECTED_SHARE}
        for ap, ns in nets_per_ap.items():
            missing = sorted(expected - ns)
            if missing:
                ap_info = self.aps[ap]
                s = min(ap_info["sensors"])
                self._detect(Detection("DISC-01", wm, "ap", ap, sensor=s, ap=ap, channel=self.sensors[s].channel,
                                       metrics={"missing": ", ".join(missing), "offered": ", ".join(sorted(ns))},
                                       confidence=0.7))
        self._numbering_gaps(wm)
        for bs in self.bssids.values():
            if bs.count >= 200 and bs.rssi_min == bs.rssi_max:
                self._flag("SENS-04:rssi", wm, sensor=bs.sensor,
                           text="Signal strength of every access point never changes (typical of an emulated capture)")

    def _numbering_gaps(self, wm: float) -> None:
        """Suspected silent AP: a hole in otherwise consecutive AP radio numbering (vendor numbering heuristic)."""
        heard = {rid: num for rid, num in self.mk.radio_numbers().items() if rid in self.aps}
        if len(heard) < 5:
            return
        nums = sorted(heard.values())
        diffs = [b - a for a, b in zip(nums, nums[1:])]
        step = Counter(diffs).most_common(1)[0][0]
        if step <= 0 or sum(1 for x in diffs if x % step == 0) < 0.8 * len(diffs):
            return
        by_num = {v: k for k, v in heard.items()}
        for a, b in zip(nums, nums[1:]):
            if (b - a) % step == 0 and b - a > step:
                for k in range(1, (b - a) // step):
                    between = f"between {self.alias_ap(by_num[a])} and {self.alias_ap(by_num[b])}"
                    self._detect(Detection("DISC-02", wm, "site", f"gap:{a + k * step}",
                                           metrics={"between": between}, confidence=0.5, severity="medium"))

    # ------------------------------------------------------------------ outputs
    def finish(self) -> None:
        self._evaluate(self.t + config.ALLOWED_LATENESS_S)
        self._eval_windows(self.t)
        self._eval_coverage(self.t)
