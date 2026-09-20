"""Config file, env overrides, flag merging."""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import CliError

PROVIDERS = ("auto", "typesafe", "openrouter", "cloudflare")
FORMATS = ("text", "json", "jsonl", "csv", "tsv", "md")


DEFAULTS: dict[str, Any] = {
    "provider": "auto",
    "model": "jev-latest",
    "timeoutMs": 30_000,
    "format": "text",
    "verify": {"autoAccept": 0.8},
    "screen": {"blockAt": 0.75, "reviewAt": 0.25},
    "find": {"topK": 5, "found": 0.7, "absent": 0.35},
    "classify": {"minConfidence": 0.6, "threshold": 0.5},
    "extract": {"minConfidence": 0.6},
    "batch": {"concurrency": 4},
    "rerank": {"topK": 10, "min": 0.5},
    "route": {"minConfidence": 0.6},
    "compact": {
        "keepThreshold": 0.5,
        "preserveRecent": 6,
        "maxStateTokens": 25_000,
        "maxRequestTokens": 30_000,
        "truncateHead": 300,
        "minReduction": 0.25,
    },
}


# For value coercion + validation on `jev config set`.
_KEY_TYPES: dict[str, str] = {
    "provider": "provider",
    "model": "str",
    "timeoutMs": "pos_int",
    "format": "format",
    "verify.autoAccept": "prob",
    "screen.blockAt": "prob",
    "screen.reviewAt": "prob",
    "find.topK": "pos_int",
    "find.found": "prob",
    "find.absent": "prob",
    "classify.minConfidence": "prob",
    "classify.threshold": "prob",
    "extract.minConfidence": "prob",
    "batch.concurrency": "pos_int",
    "rerank.topK": "pos_int",
    "rerank.min": "prob",
    "route.minConfidence": "prob",
    "compact.keepThreshold": "prob",
    "compact.preserveRecent": "nonneg_int",
    "compact.maxStateTokens": "pos_int",
    "compact.maxRequestTokens": "pos_int",
    "compact.truncateHead": "nonneg_int",
    "compact.minReduction": "prob",
}


def known_config_keys() -> list[str]:
    return sorted(_KEY_TYPES)


def config_path(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    if env.get("JEV_CONFIG"):
        return env["JEV_CONFIG"]
    base = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME") or str(Path.home()), ".config")
    return os.path.join(base, "jev", "config.json")


def read_config_file(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            parsed = json.load(f)
    except json.JSONDecodeError as err:
        raise CliError(f"Config file {path} is not valid JSON: {err}")
    if not isinstance(parsed, dict):
        raise CliError(f"Config file {path} must be a JSON object.")
    return parsed


def write_config_file(path: str, config: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def config_from_env(env: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if env.get("JEV_PROVIDER"):
        out["provider"] = env["JEV_PROVIDER"].lower()
    if env.get("JEV_MODEL"):
        out["model"] = env["JEV_MODEL"]
    if env.get("JEV_TIMEOUT_MS"):
        try:
            n = float(env["JEV_TIMEOUT_MS"])
        except ValueError:
            raise CliError("JEV_TIMEOUT_MS must be a positive number.")
        if n <= 0:
            raise CliError("JEV_TIMEOUT_MS must be a positive number.")
        out["timeoutMs"] = int(n)
    if env.get("JEV_FORMAT"):
        out["format"] = env["JEV_FORMAT"]
    return out


def merge_config(*layers: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for layer in layers:
        for k, v in layer.items():
            if v is None:
                continue
            existing = out.get(k)
            if isinstance(v, dict) and isinstance(existing, dict):
                out[k] = {**existing, **v}
            else:
                out[k] = v
    return out


def resolve_config(
    env: dict[str, str] | None = None,
    flags: dict[str, Any] | None = None,
    use_file: bool = True,
) -> dict[str, Any]:
    return resolve_config_with_provenance(env=env, flags=flags, use_file=use_file)[0]


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def resolve_config_with_provenance(
    env: dict[str, str] | None = None,
    flags: dict[str, Any] | None = None,
    use_file: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (config, provenance). provenance has per-dotted-key source + file meta + bundle sha256."""
    env = env if env is not None else dict(os.environ)
    path = config_path(env)
    file = read_config_file(path) if use_file else {}
    env_layer = config_from_env(env)
    flag_layer = flags or {}

    merged = merge_config(deepcopy(DEFAULTS), file, env_layer, flag_layer)
    _validate(merged)

    sources = {"default": DEFAULTS, "file": file, "env": env_layer, "flag": flag_layer}
    source_by_key: dict[str, str] = {}
    for name, layer in sources.items():
        for k in _flatten(layer):
            source_by_key[k] = name

    canonical = json.dumps(merged, sort_keys=True, separators=(",", ":")).encode()
    provenance = {
        "config_file": {
            "path": path,
            "exists": os.path.exists(path) if use_file else False,
            "mtime": _iso_mtime(path) if use_file and os.path.exists(path) else None,
            "used": bool(use_file),
        },
        "sources": source_by_key,
        "resolved_bundle_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    return merged, provenance


def _iso_mtime(path: str) -> str:
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()


def _validate(cfg: dict[str, Any]) -> None:
    if cfg.get("provider") not in PROVIDERS:
        raise CliError(f'Unknown provider "{cfg.get("provider")}". Allowed: {", ".join(PROVIDERS)}.')
    if cfg.get("format") not in FORMATS:
        raise CliError(f'Unknown format "{cfg.get("format")}". Allowed: {", ".join(FORMATS)}.')


def _coerce(dotted: str, raw: str) -> Any:
    kind = _KEY_TYPES.get(dotted)
    if kind is None:
        raise CliError(f'Unknown config key "{dotted}". Known keys: {", ".join(known_config_keys())}.')
    if kind == "str":
        return raw
    if kind == "provider":
        if raw not in PROVIDERS:
            raise CliError(f'provider must be one of {", ".join(PROVIDERS)}.')
        return raw
    if kind == "format":
        if raw not in FORMATS:
            raise CliError(f'format must be one of {", ".join(FORMATS)}.')
        return raw
    if kind == "prob":
        try:
            n = float(raw)
        except ValueError:
            raise CliError(f"{dotted} must be a number between 0 and 1.")
        if not (0.0 <= n <= 1.0):
            raise CliError(f"{dotted} must be a number between 0 and 1.")
        return n
    if kind == "pos_int":
        try:
            n = int(raw)
        except ValueError:
            raise CliError(f"{dotted} must be a positive integer.")
        if n <= 0:
            raise CliError(f"{dotted} must be a positive integer.")
        return n
    if kind == "nonneg_int":
        try:
            n = int(raw)
        except ValueError:
            raise CliError(f"{dotted} must be a non-negative integer.")
        if n < 0:
            raise CliError(f"{dotted} must be a non-negative integer.")
        return n
    raise CliError(f"Unknown coercion for {dotted}.")


def set_config_value(current: dict[str, Any], dotted: str, raw: str) -> dict[str, Any]:
    value = _coerce(dotted, raw)
    parts = dotted.split(".")
    out = deepcopy(current)
    cursor = out
    for segment in parts[:-1]:
        if not isinstance(cursor.get(segment), dict):
            cursor[segment] = {}
        cursor = cursor[segment]
    cursor[parts[-1]] = value
    return out


def unset_config_value(current: dict[str, Any], dotted: str) -> dict[str, Any]:
    parts = dotted.split(".")
    out = deepcopy(current)
    cursor = out
    for segment in parts[:-1]:
        if not isinstance(cursor.get(segment), dict):
            return out
        cursor = cursor[segment]
    cursor.pop(parts[-1], None)
    return out
