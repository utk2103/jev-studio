"""Update-check warning shown before a command's output.

Checks PyPI at most once per day, cached on disk, so most invocations never
touch the network. Best-effort: any network or filesystem failure just skips
the warning silently.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import config_path

DEFAULT_TTL_SECONDS = 24 * 60 * 60
_PYPI_JSON_URL = "https://pypi.org/pypi/jev-studio/json"


def version_cache_path(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else dict(os.environ)
    if env.get("JEV_VERSION_CACHE"):
        return env["JEV_VERSION_CACHE"]
    return os.path.join(os.path.dirname(config_path(env)), "update-check.json")


def _read_cache(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("latest"), str) and isinstance(data.get("checked_at"), (int, float)):
        return data
    return None


def _write_cache(path: str, latest: str, checked_at: float) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"latest": latest, "checked_at": checked_at}, fh)
    except OSError:
        pass


def _fetch_latest_from_pypi(timeout: float = 3.0) -> str | None:
    try:
        with urllib.request.urlopen(_PYPI_JSON_URL, timeout=timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    latest = payload.get("info", {}).get("version")
    return latest if isinstance(latest, str) else None


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in raw.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            return tuple(parts)
        parts.append(int(digits))
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def check_for_update(
    current_version: str,
    *,
    env: dict[str, str] | None = None,
    fetch_latest: object = None,
    now: float | None = None,
    ttl_seconds: float | None = None,
) -> str | None:
    """Return the latest version if newer than current, else None.

    `fetch_latest` is only called when the cache is missing or stale; overridable
    for tests. `env`, `now`, `ttl_seconds` are also overridable for tests.
    """
    env = env if env is not None else dict(os.environ)
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS
    current_time = now if now is not None else time.time()
    path = version_cache_path(env)

    cache = _read_cache(path)
    if cache is None or (current_time - float(cache["checked_at"])) > ttl:
        fetcher = fetch_latest if callable(fetch_latest) else _fetch_latest_from_pypi
        latest = fetcher()  # type: ignore[operator]
        if not isinstance(latest, str):
            return None
        _write_cache(path, latest, current_time)
    else:
        latest = cache["latest"]

    return latest if is_newer(latest, current_version) else None
