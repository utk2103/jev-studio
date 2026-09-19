#!/usr/bin/env python3
"""UserPromptSubmit hook: parse `/jev lite|full|ultra|off` and mutate state.

Non-matching prompts pass through untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _jev_common import (
    MODES,
    build_instructions,
    clear_mode,
    emit_prompt_submit,
    read_mode,
    read_stdin_json,
    write_mode,
)

_CMD = re.compile(r"^\s*/(?:jev-studio:)?jev\s+(\S+)\s*$", re.IGNORECASE)
_BARE = re.compile(r"^\s*/(?:jev-studio:)?jev\s*$", re.IGNORECASE)
_OFF = re.compile(r"^\s*(stop\s+jev|normal\s+mode|/(?:jev-studio:)?jev\s+off)\s*$", re.IGNORECASE)

# Claude Code delivers slash commands as an envelope, not the literal command.
_ENVELOPE_NAME = re.compile(r"<command-name>\s*([^<\s]+)\s*</command-name>", re.IGNORECASE)
_ENVELOPE_ARGS = re.compile(r"<command-args>\s*([^<]*?)\s*</command-args>", re.IGNORECASE)
_JEV_SLASH = re.compile(r"^/(?:jev-studio:)?jev$", re.IGNORECASE)


def _unwrap(prompt: str) -> str | None:
    name = _ENVELOPE_NAME.search(prompt)
    if not name:
        return prompt
    cmd = name.group(1)
    if not _JEV_SLASH.match(cmd):
        return None
    args_m = _ENVELOPE_ARGS.search(prompt)
    args = args_m.group(1).strip() if args_m else ""
    return f"{cmd} {args}".strip()


def main() -> None:
    payload = read_stdin_json()
    prompt = str(payload.get("prompt", ""))

    # Scheduled/background runs must not receive Jev reinforcement.
    if "<scheduled-task" in prompt:
        return

    unwrapped = _unwrap(prompt)
    if unwrapped is None:
        return
    prompt = unwrapped

    if _OFF.match(prompt):
        clear_mode()
        emit_prompt_submit(system_message="JEV MODE OFF")
        return

    if _BARE.match(prompt):
        emit_prompt_submit(system_message=f"JEV MODE: {read_mode()}")
        return

    m = _CMD.match(prompt)
    if not m:
        return

    arg = m.group(1).lower()
    if arg not in MODES:
        emit_prompt_submit(system_message=f"JEV: unknown mode '{arg}'. Valid: {', '.join(MODES)}")
        return

    write_mode(arg)
    emit_prompt_submit(
        system_message=f"JEV MODE → {arg}",
        additional_context=build_instructions(arg),
    )


if __name__ == "__main__":
    main()
