"""CLI: python -m airframe batch | serve"""

from __future__ import annotations

import argparse
import json
import time

from . import config


def batch(source: str, until: float | None) -> None:
    from .runner import build_engine, run_batch
    from .views import incident_dict

    config.OUT_DIR.mkdir(exist_ok=True)
    (config.OUT_DIR / "unknown_events.jsonl").unlink(missing_ok=True)
    eng = build_engine(out_dir=config.OUT_DIR)
    t0 = time.time()
    kind, n = run_batch(eng, source, until)
    wall = time.time() - t0
    tops = eng.inc.top_level()
    report = [incident_dict(eng, i, full=True) for i in tops]
    (config.OUT_DIR / "incidents.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"source={kind} frames={n:,} event_time={eng.t:.1f}s wall={wall:.1f}s ({n / wall:,.0f} frames/s)")
    for i in tops:
        print(f"  {i.id} {i.severity:8s} {i.cid:9s} dev={len(i.devices):3d} aps={len(i.aps):2d} kids={len(i.children):3d} "
              f"first={i.first_t:7.1f}s  {i.title}")
    print(f"unknown events: {len(eng.unknown)}  observations: {len(eng.observations)}  flags: {sorted(eng.flags)}")
    print(f"written: {config.OUT_DIR / 'incidents.json'}")


def main() -> None:
    p = argparse.ArgumentParser(prog="airframe")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("batch", help="replay all captures as fast as possible and write out/incidents.json")
    b.add_argument("--source", default="auto", choices=["auto", "jsonl", "pcap"])
    b.add_argument("--until", type=float, default=None, help="stop at this event time (s)")
    s = sub.add_parser("serve", help="run the API + live dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    if a.cmd == "batch":
        batch(a.source, a.until)
    else:
        import uvicorn
        uvicorn.run("airframe.server:app", host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
