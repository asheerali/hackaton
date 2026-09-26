"""System prompt for the Part 3 catalog-discovery agent (text lives in agents/prompts/discovery.txt)."""

from __future__ import annotations

from .. import prompts

SYSTEM = prompts.load("discovery")
