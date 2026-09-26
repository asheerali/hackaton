"""Error catalog (Part 3): base catalog + human-approved extensions, hot-reloadable."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config

BASE = config.CATALOG_DIR / "error_catalog.json"
EXT = config.CATALOG_DIR / "extensions.json"
CODES = config.CATALOG_DIR / "ieee_codes.json"


class Catalog:
    def __init__(self, base: Path = BASE, ext: Path = EXT):
        self._base_path, self._ext_path = base, ext
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        with self._lock:
            base = json.loads(self._base_path.read_text(encoding="utf-8"))
            ext = json.loads(self._ext_path.read_text(encoding="utf-8")) if self._ext_path.exists() else {"entries": [], "changelog": []}
            self.base_version = base["version"]
            self.ext_count = len(ext["entries"])
            self.version = f"{self.base_version}+ext{self.ext_count}" if self.ext_count else self.base_version
            self.categories = base["categories"]
            self.entries = {e["id"]: e for e in base["entries"]}
            self.code_index = {k: dict(v) for k, v in base["code_index"].items()}
            for e in ext["entries"]:
                self.entries[e["id"]] = e
                for r in e.get("codes", {}).get("reason", []):
                    self.code_index["reason"].setdefault(str(r), {"text": e["name"], "entry": e["id"]})["entry"] = e["id"]
                for s in e.get("codes", {}).get("status", []):
                    self.code_index["status"].setdefault(str(s), {"text": e["name"], "entry": e["id"]})["entry"] = e["id"]
            self.changelog = ext.get("changelog", [])
            self.ieee = json.loads(CODES.read_text(encoding="utf-8"))

    def entry(self, cid: str) -> dict | None:
        return self.entries.get(cid)

    def for_code(self, kind: str, code: int | None) -> str:
        """kind: 'reason' | 'status'. Unknown or reserved codes -> OTHER-CODE."""
        if code is None:
            return "OTHER-CODE"
        if kind == "status" and code == 0:
            return "OK"
        hit = self.code_index.get(kind, {}).get(str(code))
        return hit["entry"] if hit else "OTHER-CODE"

    def code_text(self, kind: str, code: int | None) -> str:
        table = self.ieee.get("wlan.fixed.reason_code" if kind == "reason" else "wlan.fixed.status_code", {})
        return table.get(str(code), "not defined in IEEE 802.11 tables")

    def add_extension(self, entry: dict, note: str) -> str:
        with self._lock:
            ext = json.loads(self._ext_path.read_text(encoding="utf-8")) if self._ext_path.exists() else {"entries": [], "changelog": []}
            ext["entries"] = [e for e in ext["entries"] if e["id"] != entry["id"]] + [entry]
            ext["changelog"].append({"id": entry["id"], "note": note})
            self._ext_path.write_text(json.dumps(ext, indent=1), encoding="utf-8")
        self.reload()
        return self.version

    def summary(self) -> dict:
        return {"version": self.version, "entries": len(self.entries), "categories": len(self.categories),
                "extensions": self.ext_count}
