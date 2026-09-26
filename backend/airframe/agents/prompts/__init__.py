"""Loader for the plain-text system prompts shared by the fix and discovery agents."""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent


def load(name: str) -> str:
    return (_DIR / f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")
