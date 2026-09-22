"""Credential store: OS keychain where available, else a 0600 file."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import config_path
from .errors import CliError

CREDENTIAL_PROVIDERS = ("typesafe", "openrouter")

ENV_VAR: dict[str, str] = {
    "typesafe": "TYPESAFE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

SERVICE = "jev-studio"


@dataclass
class CredentialStore:
    kind: str  # "keychain" | "file"
    location: str
    get: Callable[[str], str | None]
    set: Callable[[str, str], None]
    delete: Callable[[str], bool]


def credentials_path(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    if env.get("JEV_CREDENTIALS"):
        return env["JEV_CREDENTIALS"]
    return os.path.join(os.path.dirname(config_path(env)), "credentials.json")


def _file_store(env: dict[str, str]) -> CredentialStore:
    path = credentials_path(env)

    def _read() -> dict[str, str]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            raise CliError(f"Credentials file {path} is not valid JSON. Fix or delete it.")
        return data if isinstance(data, dict) else {}

    def _write(data: dict[str, str]) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    def _get(p: str) -> str | None:
        return _read().get(p) or None

    def _set(p: str, secret: str) -> None:
        data = _read()
        data[p] = secret
        _write(data)

    def _delete(p: str) -> bool:
        data = _read()
        if p not in data:
            return False
        del data[p]
        if not data:
            os.unlink(path)
        else:
            _write(data)
        return True

    return CredentialStore("file", path, _get, _set, _delete)


def _run(cmd: list[str], input_: str | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            input=input_.encode() if input_ is not None else None,
            capture_output=True,
            check=True,
        )
        return True, result.stdout.decode(errors="replace").rstrip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False, ""


def _has_command(name: str) -> bool:
    return shutil.which(name) is not None


def _mac_keychain() -> CredentialStore:
    account = lambda p: f"{p}-api-key"  # noqa: E731

    def _get(p: str) -> str | None:
        ok, out = _run(["security", "find-generic-password", "-s", SERVICE, "-a", account(p), "-w"])
        return out if ok and out else None

    def _set(p: str, secret: str) -> None:
        ok, _ = _run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", account(p), "-w", secret])
        if not ok:
            raise CliError("Could not write to the macOS Keychain.")

    def _delete(p: str) -> bool:
        ok, _ = _run(["security", "delete-generic-password", "-s", SERVICE, "-a", account(p)])
        return ok

    return CredentialStore("keychain", f'macOS Keychain (service "{SERVICE}")', _get, _set, _delete)


def _linux_secret_tool() -> CredentialStore:
    attrs = lambda p: ["service", SERVICE, "account", f"{p}-api-key"]  # noqa: E731

    def _get(p: str) -> str | None:
        ok, out = _run(["secret-tool", "lookup", *attrs(p)])
        return out if ok and out else None

    def _set(p: str, secret: str) -> None:
        ok, _ = _run(["secret-tool", "store", "--label", f"jev {p} API key", *attrs(p)], input_=secret)
        if not ok:
            raise CliError("Could not store the key with secret-tool (is a Secret Service daemon running?).")

    def _delete(p: str) -> bool:
        ok, _ = _run(["secret-tool", "clear", *attrs(p)])
        return ok

    return CredentialStore(
        "keychain", f'Secret Service via secret-tool (service "{SERVICE}")', _get, _set, _delete
    )


def resolve_store(env: dict[str, str] | None = None) -> CredentialStore:
    env = env if env is not None else dict(os.environ)
    forced = (env.get("JEV_CREDENTIAL_STORE") or "").lower()
    if forced == "file":
        return _file_store(env)
    if forced and forced not in ("keychain", "auto"):
        raise CliError(
            f'JEV_CREDENTIAL_STORE must be auto, keychain, or file (got "{env.get("JEV_CREDENTIAL_STORE")}").'
        )
    if sys.platform == "darwin" and _has_command("security"):
        return _mac_keychain()
    if sys.platform.startswith("linux") and _has_command("secret-tool"):
        return _linux_secret_tool()
    if forced == "keychain":
        raise CliError(
            "No supported keychain tool found on this system (macOS `security` or Linux `secret-tool`)."
        )
    return _file_store(env)


def resolve_credentials(env: dict[str, str], store: CredentialStore | None = None) -> list[dict]:
    lazy = [store]

    def get_store() -> CredentialStore:
        if lazy[0] is None:
            lazy[0] = resolve_store(env)
        return lazy[0]

    out = []
    for provider in CREDENTIAL_PROVIDERS:
        env_val = (env.get(ENV_VAR[provider]) or "").strip()
        if env_val:
            out.append({"provider": provider, "source": "env"})
            continue
        try:
            value = get_store().get(provider)
        except Exception:
            value = None
        if value:
            out.append({"provider": provider, "source": get_store().kind, "value": value})
        else:
            out.append({"provider": provider, "source": "none"})
    return out


def with_stored_credentials(env: dict[str, str], store: CredentialStore | None = None) -> dict[str, str]:
    if env.get("JEV_NO_STORED_CREDENTIALS") == "1":
        return dict(env)
    out = dict(env)
    for c in resolve_credentials(env, store):
        if c.get("value"):
            out[ENV_VAR[c["provider"]]] = c["value"]
    return out
