"""Frame sources: merged, time-ordered streams from all sensors (JSONL replay or tshark on pcaps)."""

from __future__ import annotations

import heapq
import json
import queue
import threading
from pathlib import Path
from typing import Iterator

from . import config
from .tshark import find_tshark, stream_pcap

try:
    import orjson
    _loads = orjson.loads
except ImportError:  # pragma: no cover
    _loads = json.loads


def discover(kind: str) -> dict[int, Path]:
    if kind == "jsonl":
        files = sorted(config.JSONL_DIR.glob("sensor*.jsonl"))
    else:
        files = sorted(config.PCAP_DIR.glob("sensor*.pcap"))
    return {int(p.stem.replace("sensor", "")): p for p in files}


def _jsonl(path: Path) -> Iterator[dict]:
    with path.open("rb") as fh:
        for line in fh:
            yield _loads(line)


def _threaded(it: Iterator[dict], maxsize: int = 20000) -> Iterator[dict]:
    """Run a blocking iterator (tshark pipe) in a thread so all sensors decode in parallel."""
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    done = object()

    def pump():
        try:
            for x in it:
                q.put(x)
        finally:
            q.put(done)

    threading.Thread(target=pump, daemon=True).start()
    while True:
        x = q.get()
        if x is done:
            return
        yield x


def merged(kind: str = "auto") -> tuple[str, Iterator[tuple[int, dict]], float | None]:
    """Returns (kind used, iterator of (sensor, raw) in event-time order, expected duration if known)."""
    if kind == "auto":
        kind = "jsonl" if discover("jsonl") else "pcap"
    files = discover(kind)
    if not files:
        raise FileNotFoundError(f"no {kind} captures found")
    duration = None
    if kind == "jsonl":
        metas = [json.loads(p.with_suffix(".meta.json").read_text()) for p in files.values()
                 if p.with_suffix(".meta.json").exists()]
        duration = max((m["duration_s"] for m in metas), default=None)
        streams = {s: _jsonl(p) for s, p in files.items()}
    else:
        tshark = find_tshark()
        if not tshark:
            raise FileNotFoundError("tshark not found (set TSHARK)")
        streams = {s: _threaded(stream_pcap(p, tshark)) for s, p in files.items()}

    def gen():
        heap = []
        for s, it in streams.items():
            first = next(it, None)
            if first is not None:
                heap.append((first["t"], s, first, it))
        heapq.heapify(heap)
        while heap:
            t, s, raw, it = heapq.heappop(heap)
            yield s, raw
            nxt = next(it, None)
            if nxt is not None:
                heapq.heappush(heap, (nxt["t"], s, nxt, it))

    return kind, gen(), duration
