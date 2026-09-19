"""Prompt/instruction builder for Jev Studio MCP server.

Self-contained: no external repo imports so the package ships standalone on
PyPI. Extend `MODES` / `_INSTRUCTIONS` with the real Jev ruleset.
"""
from __future__ import annotations

MODES: tuple[str, ...] = ("lite", "full", "ultra")
DEFAULT_MODE: str = "full"

_INSTRUCTIONS: dict[str, str] = {
    "lite": "Jev — lite mode. Concise, minimal guidance.",
    "full": "Jev — full mode. Standard ruleset.",
    "ultra": "Jev — ultra mode. Maximum intensity.",
}


def resolve_mode(requested: str | None) -> str:
    asked = (requested or "").strip().lower()
    if asked in MODES:
        return asked
    return DEFAULT_MODE


def build_instructions(requested: str | None) -> str:
    return _INSTRUCTIONS[resolve_mode(requested)]
