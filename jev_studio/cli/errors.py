"""Exit codes and CLI errors."""
from __future__ import annotations


class Exit:
    OK = 0
    ERROR = 1
    JUDGMENT = 2


class CliError(Exception):
    def __init__(self, message: str, exit_code: int = Exit.ERROR):
        super().__init__(message)
        self.exit_code = exit_code


def describe_error(err: BaseException) -> str:
    status = getattr(err, "status", None)
    extra = f" (HTTP {status})" if status else ""
    return f"{err}{extra}"
