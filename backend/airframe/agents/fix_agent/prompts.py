"""System prompt for the Part 2 fix-proposal agent (text lives in agents/prompts/fix_agent.txt)."""

from __future__ import annotations

from .. import prompts

SYSTEM = prompts.load("fix_agent")
