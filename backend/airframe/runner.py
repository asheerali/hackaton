"""Batch run and paced real-time replay controller."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from . import config
from .catalog import Catalog
from .decode import normalise
from .engine import Engine
from .privacy import Masker
from .sources import merged
from .views import snapshot


def build_engine(catalog: Catalog | None = None, out_dir: Path | None = None) -> Engine:
    return Engine(catalog or Catalog(), Masker(), out_dir=out_dir)


def run_batch(eng: Engine, source: str = "auto", until: float | None = None) -> tuple[str, int]:
    kind, it, _ = merged(source)
    n = 0
    for s, raw in it:
        if until is not None and raw["t"] > until:
            break
        eng.process(normalise(raw, s, eng.mk))
        n += 1
    eng.finish()
    return kind, n


class Replay:
    """Runs one engine in a background thread, paced by event time x speed; publishes snapshots ~1/s."""

    SPEEDS = (1, 5, 10, 30, 60, 0)          # 0 = as fast as possible

    def __init__(self, catalog: Catalog):
        self.cat = catalog
        self.lock = threading.RLock()
        self.version = 0
        self.snap: dict | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self.speed = 10
        self.source = "auto"
        self.kind = None
        self.state = "idle"
        self.duration = None
        self.engine: Engine | None = None
        self._inject: list = []
        self.fps = 0.0

    # ---- control ----
    def start(self, speed: float | None = None, source: str | None = None) -> None:
        self.stop()
        if speed is not None:
            self.speed = speed
        if source:
            self.source = source
        config.OUT_DIR.mkdir(exist_ok=True)
        (config.OUT_DIR / "unknown_events.jsonl").unlink(missing_ok=True)
        self.engine = Engine(self.cat, Masker(), out_dir=config.OUT_DIR)
        self._stop.clear()
        self._pause.clear()
        self.state = "running"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def pause(self) -> None:
        if self.state == "running":
            self._pause.set()
            self.state = "paused"
            self._publish()

    def resume(self) -> None:
        if self.state == "paused":
            self._pause.clear()
            self.state = "running"

    def set_speed(self, speed: float) -> None:
        self.speed = speed
        self._rebase = True

    def inject(self, frames: list[tuple[int, dict]]) -> None:
        """Queue frames for the running replay, or process them now if the replay is paused/finished."""
        with self.lock:
            if self.state == "running":
                self._inject.extend(frames)
                return
            if self.engine:
                for s, raw in frames:
                    raw["t"] = self.engine.t
                    self.engine.process(normalise(raw, s, self.engine.mk))
        self._publish()

    # ---- loop ----
    def _clock(self) -> dict:
        return {"state": self.state, "speed": self.speed, "source": self.kind, "duration": self.duration,
                "fps": round(self.fps)}

    def _publish(self) -> None:
        if not self.engine:
            return
        with self.lock:
            snap = snapshot(self.engine, self._clock())
            self.snap = snap
            self.version += 1

    def _run(self) -> None:
        eng = self.engine
        try:
            self.kind, it, self.duration = merged(self.source)
        except Exception as exc:  # surfaced to the UI
            self.state = f"error: {exc}"
            return
        self._rebase = True
        base_wall = base_t = 0.0
        last_pub = 0.0
        count_mark, wall_mark = 0, time.perf_counter()
        n = 0
        for s, raw in it:
            if self._stop.is_set():
                return
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.05)
                self._rebase = True
            now = time.perf_counter()
            if self._rebase:
                base_wall, base_t, self._rebase = now, raw["t"], False
            if self.speed:
                due = base_wall + (raw["t"] - base_t) / self.speed
                if due > now:
                    time.sleep(min(due - now, 0.5))
            if self._inject:
                with self.lock:
                    pending, self._inject = self._inject, []
                with self.lock:
                    for js, jraw in pending:
                        jraw["t"] = eng.t
                        eng.process(normalise(jraw, js, eng.mk))
            with self.lock:
                eng.process(normalise(raw, s, eng.mk))
            n += 1
            now = time.perf_counter()
            if now - last_pub >= config.SNAPSHOT_EVERY_S:
                self.fps = (n - count_mark) / max(now - wall_mark, 1e-6)
                count_mark, wall_mark = n, now
                last_pub = now
                self._publish()
        with self.lock:
            eng.finish()
        self.state = "finished"
        self._publish()
