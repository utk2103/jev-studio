#!/usr/bin/env python3
"""SubagentStart hook: inject the Jev ruleset into fresh subagent context."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _jev_common import OFF_MODE, build_instructions, emit_session_context, read_mode


def main() -> None:
    mode = read_mode()
    if mode == OFF_MODE:
        return
    try:
        emit_session_context(build_instructions(mode))
    except Exception:
        pass


if __name__ == "__main__":
    main()
