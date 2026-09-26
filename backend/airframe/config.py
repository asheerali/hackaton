"""Paths and every detection threshold in one place."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
PCAP_DIR = ROOT / "hackaton_airframe" / "hackaton_airframe"
JSONL_DIR = ROOT / "json_full"
CATALOG_DIR = ROOT / "catalog"
OUT_DIR = ROOT / "out"
WEB_DIST = ROOT / "frontend" / "dist"
SALT_FILE = ROOT / ".airframe_salt"

TSHARK_CANDIDATES = [
    os.environ.get("TSHARK", ""),
    r"C:\Program Files\Wireshark\tshark.exe",
    "/usr/bin/tshark",
    "/usr/local/bin/tshark",
    "/Applications/Wireshark.app/Contents/MacOS/tshark",
]

# Device classes by OUI (vendor prefix). Site-specific; only the class leaves the normaliser.
OUI_CLASSES = {
    "3c:58:c2": "laptop",
    "f0:18:98": "phone",
    "b8:27:eb": "iot",
}

# --- streaming ---
SNAPSHOT_EVERY_S = 1.0          # wall-clock push interval
AUTOSTART = os.environ.get("AIRFRAME_AUTOSTART", "1") == "1"
BUCKET_S = 10.0                 # chart bucket (event time)
ALLOWED_LATENESS_S = 3.0        # watermark = max event time - lateness

# --- episodes / 802.1X ---
EAP_STALL_S = 20.0              # identity request with no method/success/failure/M1
ATTEMPT_TIMEOUT_S = 90.0
KEY_M1_REPEAT_S = 5.0

# --- disconnect patterns ---
LOOP_WINDOW_S = 600.0
LOOP_MIN_FAILURES = 3
FAST_REJECT_WINDOW_S = 120.0
FAST_REJECT_MIN = 3
LEAVE_BURST_WINDOW_S = 10.0
LEAVE_BURST_MIN_CLIENTS = 8
ROAM_GAP_S = 1.0

# --- discovery / RF ---
PROBE_WINDOW_S = 60.0
PROBE_PER_CLIENT_PER_S = 1.0
PROBE_STORM_MIN_CLIENTS = 5
RETRY_WINDOW_S = 60.0
RETRY_SHARE = 0.20
RETRY_MIN_FRAMES = 30
BEACON_AIRTIME_SHARE = 0.10
MIN_BASIC_RATE_5GHZ = 12.0
NETWORK_EXPECTED_SHARE = 0.5    # a network on >= 50% of APs is expected on all
DISC_EVAL_AFTER_S = 60.0
SENSOR_DEAF_S = 2.0

# --- correlation ---
MERGE_WINDOW_S = 5.0
ROOT_MIN_APS = 3
ROOT_WINDOW_S = 120.0
RESOLVE_AFTER_S = 600.0         # longest observed retry backoff is ~9 min
REOPEN_WITHIN_S = 1800.0        # same device + same entry within 30 min = same finding (reopened, not new)
STAT_ZSCORE = 4.0
STAT_MIN_COUNT = 20

# --- agents ---
AGENT_MODEL = os.environ.get("AIRFRAME_MODEL", "claude-opus-5")
AGENT_MODE = os.environ.get("AIRFRAME_AGENT_MODE", "auto")   # auto | claude | offline
AGENT_MAX_TURNS = 12
AGENT_MIN_CONFIDENCE = 0.6
