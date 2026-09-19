"""Shared helpers for Jev Studio plugin hooks.

Reuses `jev_studio.instructions` so the plugin and the MCP server emit
identical rules — one source of truth.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from stat import S_ISLNK, S_ISREG

# CLAUDE_PLUGIN_ROOT is set by Claude Code when running plugin hooks.
_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from jev_studio.instructions import (  # noqa: E402
    DEFAULT_MODE,
    MODES,
    build_instructions,
    resolve_mode,
)

OFF_MODE = "off"
_VALID_FLAG_VALUES = frozenset({OFF_MODE, *MODES})
_MAX_FLAG_BYTES = 64


def _state_dir() -> Path:
    for var in ("CLAUDE_STATE_DIR", "CLAUDE_CONFIG_DIR"):
        v = os.environ.get(var)
        if v:
            return Path(v)
    return Path.home() / ".claude"


def _normalize_project(v: str) -> str:
    try:
        return os.path.realpath(v).rstrip(os.sep)
    except OSError:
        return v.rstrip(os.sep)


def _project_scope() -> str:
    for var in ("CLAUDE_PROJECT_DIR", "PWD"):
        v = os.environ.get(var)
        if v:
            return "-" + hashlib.sha1(_normalize_project(v).encode("utf-8")).hexdigest()[:8]
    return ""


_STATE_FILE = _state_dir() / f".jev-active{_project_scope()}"
_GLOBAL_STATE_FILE = _state_dir() / ".jev-active"


def is_codex() -> bool:
    return any(k in os.environ for k in ("CODEX_HOME", "CODEX_CLI", "CODEX_SESSION_ID"))


def _default_mode() -> str:
    env = os.environ.get("JEV_DEFAULT_MODE", "").strip().lower()
    if env in _VALID_FLAG_VALUES:
        return env
    return DEFAULT_MODE


def _read_flag_file(path: Path) -> str | None:
    try:
        st = path.lstat()
    except OSError:
        return None
    if S_ISLNK(st.st_mode) or not S_ISREG(st.st_mode) or st.st_size > _MAX_FLAG_BYTES:
        return None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags)
        try:
            raw = os.read(fd, _MAX_FLAG_BYTES).decode("utf-8", "replace").strip().lower()
        finally:
            os.close(fd)
    except OSError:
        return None
    if raw not in _VALID_FLAG_VALUES:
        return None
    return OFF_MODE if raw == OFF_MODE else resolve_mode(raw)


def read_mode() -> str:
    for p in (_STATE_FILE, _GLOBAL_STATE_FILE):
        v = _read_flag_file(p)
        if v is not None:
            return v
    return _default_mode()


def has_persisted_mode() -> bool:
    return any(_read_flag_file(p) is not None for p in (_STATE_FILE, _GLOBAL_STATE_FILE))


def write_mode(mode: str) -> None:
    m = OFF_MODE if mode == OFF_MODE else resolve_mode(mode)
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            if S_ISLNK(_STATE_FILE.lstat().st_mode):
                return
        except FileNotFoundError:
            pass
        tmp = _STATE_FILE.with_name(f".jev-active.{os.getpid()}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(str(tmp), flags, 0o600)
            try:
                os.write(fd, m.encode("utf-8"))
            finally:
                os.close(fd)
            os.replace(str(tmp), str(_STATE_FILE))
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
    except OSError:
        pass


def clear_mode() -> None:
    write_mode(OFF_MODE)


def read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def emit_session_context(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def emit_prompt_submit(system_message: str = "", additional_context: str = "") -> None:
    if is_codex() and system_message:
        additional_context = (system_message + "\n\n" + additional_context).strip()
        system_message = ""
    out: dict = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}
    if system_message:
        out["hookSpecificOutput"]["systemMessage"] = system_message
    if additional_context:
        out["hookSpecificOutput"]["additionalContext"] = additional_context
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


__all__ = [
    "MODES",
    "OFF_MODE",
    "build_instructions",
    "resolve_mode",
    "read_mode",
    "has_persisted_mode",
    "write_mode",
    "clear_mode",
    "read_stdin_json",
    "emit_session_context",
    "emit_prompt_submit",
    "is_codex",
]
