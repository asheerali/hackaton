"""Masking at the edge: MACs -> keyed hashes, SSIDs -> labels. Nothing downstream sees raw identifiers."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from . import config

AKM_KIND = {1: "802.1X", 3: "802.1X", 5: "802.1X", 11: "802.1X", 12: "802.1X", 13: "802.1X",
            2: "PSK", 4: "PSK", 6: "PSK", 8: "SAE", 9: "SAE", 24: "SAE", 25: "SAE"}


def load_salt() -> bytes:
    env = os.environ.get("AIRFRAME_SALT")
    if env:
        return env.encode()
    if config.SALT_FILE.exists():
        return config.SALT_FILE.read_bytes().strip()
    salt = secrets.token_hex(32).encode()
    config.SALT_FILE.write_bytes(salt)
    return salt


class Masker:
    def __init__(self, salt: bytes | None = None):
        self._salt = salt if salt is not None else load_salt()
        self._mac: dict[str, str] = {}
        self._radio: dict[str, str] = {}
        self._radio_num: dict[str, int] = {}
        self._ssid: dict[str, str] = {}
        self._ssid_kind: dict[str, str] = {}
        self._kind_count: dict[str, int] = {}

    def _h(self, value: str, n: int = 8) -> str:
        return hmac.new(self._salt, value.encode(), hashlib.sha256).hexdigest()[:n]

    def mac(self, mac: str | None) -> str | None:
        if not mac:
            return None
        m = self._mac.get(mac)
        if m is None:
            low = mac.lower()
            if low == "ff:ff:ff:ff:ff:ff":
                m = "broadcast"
            elif int(low[:2], 16) & 1:
                m = "multicast"
            else:
                m = self._h(low)
            self._mac[mac] = m
        return m

    def radio(self, bssid: str | None) -> str | None:
        """Group BSSIDs of one AP radio: multi-SSID radios differ only in the last byte."""
        if not bssid:
            return None
        base = bssid.lower()[:14]
        rid = self._radio.get(base)
        if rid is None:
            rid = self._radio[base] = "ap" + self._h(base, 6)
            self._radio_num[rid] = int(base.replace(":", ""), 16)
        return rid

    def radio_numbers(self) -> dict[str, int]:
        """Internal-only numeric order of radios (for numbering-gap checks). Never exported."""
        return dict(self._radio_num)

    @staticmethod
    def device_class(mac: str | None) -> str:
        if not mac:
            return "unknown"
        return config.OUI_CLASSES.get(mac.lower()[:8], "device")

    def register_ssid(self, ssid: str, akm: int | None) -> str:
        """Label a beaconed SSID by its security type, e.g. 'ENT-1 (802.1X)'. Idempotent."""
        if ssid in self._ssid:
            return self._ssid[ssid]
        kind = AKM_KIND.get(akm, "OPEN" if akm is None else f"AKM{akm}")
        prefix = {"802.1X": "ENT", "PSK": "PSK", "SAE": "SAE"}.get(kind, "NET")
        self._kind_count[prefix] = self._kind_count.get(prefix, 0) + 1
        label = f"{prefix}-{self._kind_count[prefix]}"
        self._ssid[ssid] = label
        self._ssid_kind[label] = kind
        return label

    def ssid(self, ssid: str | None) -> str | None:
        if ssid is None:
            return None
        if ssid == "":
            return "*"
        return self._ssid.get(ssid) or ("SSID-" + self._h(ssid, 4))

    def network_kind(self, label: str | None) -> str | None:
        return self._ssid_kind.get(label or "")
