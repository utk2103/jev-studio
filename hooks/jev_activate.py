#!/usr/bin/env python3
"""SessionStart hook: persist mode flag + inject the Jev ruleset."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _jev_common import (
    OFF_MODE,
    build_instructions,
    emit_session_context,
    has_persisted_mode,
    read_mode,
    write_mode,
)


def main() -> None:
    persisted = has_persisted_mode()
    mode = read_mode()
    if persisted:
        write_mode(mode)
    if mode == OFF_MODE:
        return
    try:
        emit_session_context(build_instructions(mode))
    except Exception:
        # Silent-fail: never stall the session on hook error.
        pass


if __name__ == "__main__":
    main()
