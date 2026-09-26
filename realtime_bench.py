"""Real-time feasibility test.

Replays each sensor pcap into its own `tshark -r - -l` process through a pipe, paced by the capture
timestamps at SPEED x real time, and measures, per frame, the delay from "bytes written to the pipe"
to "decoded row available in Python" plus the throughput of the incremental processing step.

usage: python realtime_bench.py [speed] [capture_seconds]
"""

from __future__ import annotations

import statistics
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

from convert_full import FIELDS, PCAP_DIR, TSHARK, row_to_dict

SPEED = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
WINDOW = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0


def pcap_records(path: Path):
    with path.open("rb") as fh:
        gh = fh.read(24)
        magic = struct.unpack("<I", gh[:4])[0]
        endian = "<" if magic in (0xA1B2C3D4, 0xA1B23C4D) else ">"
        nano = magic in (0xA1B23C4D, 0x4D3CB2A1)
        yield gh, None
        while True:
            hdr = fh.read(16)
            if len(hdr) < 16:
                return
            sec, frac, incl, _ = struct.unpack(endian + "IIII", hdr)
            data = fh.read(incl)
            yield hdr + data, sec + frac / (1e9 if nano else 1e6)


class SensorStream:
    def __init__(self, idx: int):
        self.idx = idx
        self.sent_wall: list[float] = []
        self.latency: list[float] = []
        self.rows = 0
        self.state: dict = {}
        cmd = [TSHARK, "-r", "-", "-l", "-T", "fields", "-E", "separator=\t", "-E", "occurrence=f"]
        for f in FIELDS:
            cmd += ["-e", f]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=1 << 16)

    def feed(self, t_start: float):
        t0 = None
        for blob, ts in pcap_records(PCAP_DIR / f"sensor{self.idx:02d}.pcap"):
            if ts is None:
                self.proc.stdin.write(blob)
                continue
            if t0 is None:
                t0 = ts
            if ts - t0 > WINDOW:
                break
            due = t_start + (ts - t0) / SPEED
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            self.sent_wall.append(time.perf_counter())
            self.proc.stdin.write(blob)
            self.proc.stdin.flush()
        self.proc.stdin.close()

    def consume(self):
        t0 = None
        for raw in self.proc.stdout:
            now = time.perf_counter()
            vals = raw.decode("utf-8", "replace").rstrip("\r\n").split("\t")
            f = dict(zip(FIELDS, vals + [""] * (len(FIELDS) - len(vals))))
            n = int(f["frame.number"])
            if t0 is None:
                t0 = float(f["frame.time_epoch"])
            rec = row_to_dict(f, n, t0)
            self.update_state(rec)
            self.rows += 1
            if n - 1 < len(self.sent_wall):
                self.latency.append(now - self.sent_wall[n - 1])

    def update_state(self, rec: dict):
        # minimal incremental work comparable to the real pipeline: per-client last step + counters
        c = self.state.setdefault("counts", {})
        c[rec.get("subtype")] = c.get(rec.get("subtype"), 0) + 1
        if "eap" in rec or "assoc_resp" in rec or "deauth" in rec or "disassoc" in rec:
            self.state.setdefault("last", {})[rec.get("addr1")] = (rec["t"], rec.get("subtype"))


def main() -> None:
    streams = [SensorStream(i) for i in range(1, 9)]
    start = time.perf_counter() + 0.5
    threads = []
    for s in streams:
        threads.append(threading.Thread(target=s.feed, args=(start,), daemon=True))
        threads.append(threading.Thread(target=s.consume, daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - start
    lat = sorted(x for s in streams for x in s.latency)
    rows = sum(s.rows for s in streams)
    pct = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))] * 1000
    print(f"speed={SPEED}x capture_window={WINDOW:.0f}s wall={wall:.1f}s frames={rows} "
          f"throughput={rows / wall:,.0f} frames/s (real-time arrival for 8 sensors ~ {rows / WINDOW:,.0f} frames/s)")
    print(f"pipe->row latency ms: p50={pct(0.5):.1f} p90={pct(0.9):.1f} p99={pct(0.99):.1f} max={lat[-1] * 1000:.1f} "
          f"mean={statistics.mean(lat) * 1000:.1f}")


if __name__ == "__main__":
    main()
