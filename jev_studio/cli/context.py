"""Build the CommandContext (config + env + output + lazy ask factory) from global flags."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import FORMATS, PROVIDERS, resolve_config
from .credentials import with_stored_credentials
from .errors import CliError
from .io_utils import OutputOptions, should_color
from .provider import AskFn, create_ask


@dataclass
class CommandContext:
    config: dict[str, Any]
    env: dict[str, str]
    output: OutputOptions
    dry_run: bool
    _ask_factory: Callable[[dict[str, Any], dict[str, str]], AskFn]
    _cached_ask: AskFn | None = field(default=None)

    def ask(self) -> AskFn:
        if self._cached_ask is None:
            self._cached_ask = self._ask_factory(self.config, self.env)
        return self._cached_ask


def flags_to_config(flags: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if flags.get("model"):
        out["model"] = flags["model"]
    if flags.get("provider"):
        p = flags["provider"].lower()
        if p not in PROVIDERS:
            raise CliError(f'Unknown provider "{flags["provider"]}". Allowed: {", ".join(PROVIDERS)}.')
        out["provider"] = p
    if flags.get("timeout") is not None:
        try:
            n = float(flags["timeout"])
        except (TypeError, ValueError):
            raise CliError("--timeout must be a positive number of milliseconds.")
        if n <= 0:
            raise CliError("--timeout must be a positive number of milliseconds.")
        out["timeoutMs"] = int(n)
    if flags.get("json"):
        out["format"] = "json"
    elif flags.get("md"):
        out["format"] = "md"
    elif flags.get("format"):
        f = flags["format"].lower()
        if f not in FORMATS:
            raise CliError(f'Unknown format "{flags["format"]}". Allowed: {", ".join(FORMATS)}.')
        out["format"] = f
    return out


def build_context(
    flags: dict[str, Any],
    env: dict[str, str] | None = None,
    use_file: bool = True,
    ask_factory: Callable[[dict[str, Any], dict[str, str]], AskFn] | None = None,
    stream: Any = None,
) -> CommandContext:
    env = with_stored_credentials(env if env is not None else dict(os.environ))
    config = resolve_config(env=env, flags=flags_to_config(flags), use_file=use_file)
    output = OutputOptions(
        format=config["format"],
        color=False if flags.get("no_color") else should_color(env),
        quiet=bool(flags.get("quiet")),
        pluck=(flags.get("pluck") or "").strip() or None,
        stream=stream,
    )
    factory = ask_factory or (
        lambda cfg, e: create_ask(
            provider=cfg["provider"], model=cfg["model"], timeout_ms=cfg["timeoutMs"], env=e
        )
    )
    return CommandContext(
        config=config,
        env=env,
        output=output,
        dry_run=bool(flags.get("dry_run")),
        _ask_factory=factory,
    )
