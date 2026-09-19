"""Input parsing (@file, -, stdin) and output rendering (text/json/jsonl/csv/tsv/md/pluck)."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .errors import CliError

FORMATS = ("text", "json", "jsonl", "csv", "tsv", "md")

_stdin_cache: str | None = None


def read_stdin(label: str = "stdin") -> str:
    global _stdin_cache
    if _stdin_cache is not None:
        return _stdin_cache
    if sys.stdin.isatty():
        raise CliError(f"Expected {label} on stdin but stdin is a terminal. Pipe data in or pass a value.")
    _stdin_cache = sys.stdin.read()
    return _stdin_cache


def _reset_stdin_cache() -> None:
    global _stdin_cache
    _stdin_cache = None


def read_file(path: str, label: str = "file") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as err:
        raise CliError(f"Cannot read {label} {path}: {err}")


def read_input(value: str, label: str = "input") -> str:
    if value == "-":
        return read_stdin(label)
    if value.startswith("@@"):
        return value[1:]
    if value.startswith("@"):
        return read_file(value[1:], label)
    return value


def is_reference(value: str) -> bool:
    return value == "-" or (value.startswith("@") and not value.startswith("@@"))


def reference_id(value: str) -> str | None:
    if value == "-":
        return "stdin"
    if is_reference(value):
        return os.path.basename(value[1:])
    return None


def parse_json(text: str, label: str = "input") -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise CliError(f"{label} is not valid JSON: {err}")


def non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"\r?\n", text) if line.strip()]


def parse_list(text: str, label: str = "list") -> list[str]:
    trimmed = text.strip()
    if trimmed.startswith("[") or trimmed.startswith("{"):
        parsed = parse_json(trimmed, label)
        if not (isinstance(parsed, list) and all(isinstance(x, str) for x in parsed)):
            raise CliError(f"{label} must be a JSON array of strings.")
        return parsed
    return non_empty_lines(trimmed)


def parse_items(text: str, label: str = "items") -> list[dict]:
    parsed = parse_json(text, label)
    if isinstance(parsed, list):
        out = []
        for i, entry in enumerate(parsed):
            if isinstance(entry, str):
                out.append({"text": entry})
            elif isinstance(entry, dict) and isinstance(entry.get("text"), str):
                item = {"text": entry["text"]}
                if entry.get("id") is not None:
                    item["id"] = str(entry["id"])
                out.append(item)
            else:
                raise CliError(f'{label}[{i}] must be a string or an object with a "text" field.')
        return out
    if isinstance(parsed, dict):
        out = []
        for key, val in parsed.items():
            if not isinstance(val, str):
                raise CliError(f"{label}.{key} must be a string.")
            out.append({"id": str(key), "text": val})
        return out
    raise CliError(f"{label} must be a JSON array or object.")


# ── output ──────────────────────────────────────────────────────────────────


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def should_color(env: dict[str, str] | None = None, is_tty: bool | None = None) -> bool:
    env = env if env is not None else dict(os.environ)
    if env.get("NO_COLOR"):
        return False
    force = env.get("FORCE_COLOR")
    if force and force != "0":
        return True
    if is_tty is None:
        is_tty = sys.stdout.isatty()
    return bool(is_tty)


_STYLE_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "cyan": "36",
}


def paint(enabled: bool, style: str, text: str) -> str:
    if not enabled or style not in _STYLE_CODES:
        return text
    return f"\x1b[{_STYLE_CODES[style]}m{text}\x1b[0m"


def format_probability(p: float | None) -> str:
    if p is None:
        return "-"
    try:
        return f"{float(p):.2f}"
    except (TypeError, ValueError):
        return "-"


def clip(text: str, max_len: int = 60) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    return one_line if len(one_line) <= max_len else f"{one_line[: max_len - 1]}…"


def visible_length(s: str) -> int:
    return len(strip_ansi(s))


def render_table(rows: list[list[str]], color: bool = False) -> str:
    if not rows:
        return ""
    widths: list[int] = []
    for row in rows:
        for i, cell in enumerate(row):
            if i >= len(widths):
                widths.append(0)
            widths[i] = max(widths[i], visible_length(cell))

    def render_row(row: list[str]) -> str:
        return "  ".join(cell + " " * (widths[i] - visible_length(cell)) for i, cell in enumerate(row)).rstrip()

    header, *body = rows
    lines = [paint(color, "bold", render_row(header))]
    lines.append("  ".join("-" * w for w in widths))
    for row in body:
        lines.append(render_row(row))
    return "\n".join(lines)


def usage_line(usage: dict, model: str, provider: str) -> str:
    if not model and not provider:
        return "no API call made"
    return f"{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out tokens · {model} via {provider}"


@dataclass
class OutputOptions:
    format: str = "text"
    color: bool = False
    quiet: bool = False
    pluck: str | None = None
    stream: Any = None


@dataclass
class View:
    head: list[str] = field(default_factory=list)
    table: dict | None = None  # {"columns": [str], "rows": [[str]]}
    tail: list[str] = field(default_factory=list)
    kv: list[tuple[str, str]] = field(default_factory=list)
    usage: dict | None = None  # {"usage": {...}, "model": str, "provider": str}


def render_text(view: View, color: bool, quiet: bool) -> str:
    parts: list[str] = []
    if view.head:
        parts.append("\n".join(view.head))
    if view.table:
        rows = [view.table["columns"]] + view.table["rows"]
        parts.append(render_table(rows, color=color))
    if view.tail:
        parts.append("\n".join(view.tail))
    body = "\n\n".join(parts)
    if view.usage and not quiet:
        footer = paint(color, "dim", usage_line(view.usage["usage"], view.usage["model"], view.usage["provider"]))
        return f"{body}\n{footer}" if body else footer
    return body


def _md_cell(s: str) -> str:
    return strip_ansi(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(view: View, quiet: bool) -> str:
    parts: list[str] = []
    if view.head:
        parts.append("  \n".join(strip_ansi(h) for h in view.head))
    tbl = view.table or (
        {"columns": ["Field", "Value"], "rows": [[k, v] for k, v in view.kv]} if view.kv else None
    )
    if tbl:
        header = "| " + " | ".join(_md_cell(c) for c in tbl["columns"]) + " |"
        sep = "| " + " | ".join("---" for _ in tbl["columns"]) + " |"
        body = [
            "| " + " | ".join(_md_cell((r[i] if i < len(r) else "")) for i in range(len(tbl["columns"]))) + " |"
            for r in tbl["rows"]
        ]
        parts.append("\n".join([header, sep, *body]))
    if view.tail:
        parts.append("  \n".join(strip_ansi(t) for t in view.tail))
    if view.usage and not quiet:
        parts.append(f"_{usage_line(view.usage['usage'], view.usage['model'], view.usage['provider'])}_")
    return "\n\n".join(parts)


def _csv_cell(s: str, sep: str) -> str:
    v = strip_ansi(s)
    if re.search(r'[",\n\r]', v) or sep in v:
        return '"' + v.replace('"', '""') + '"'
    return v


def render_delimited(view: View, sep: str) -> str:
    tbl = view.table or (
        {"columns": ["field", "value"], "rows": [[k, v] for k, v in view.kv]} if view.kv else None
    )
    if not tbl:
        raise CliError("This result has no tabular form; use --json, --md, or --pluck.")

    def line(cells: Sequence[str]) -> str:
        if sep == "\t":
            return sep.join(strip_ansi(c).replace("\t", " ").replace("\n", " ") for c in cells)
        return sep.join(_csv_cell(c, sep) for c in cells)

    lines = [line(tbl["columns"])]
    cols = tbl["columns"]
    for r in tbl["rows"]:
        lines.append(line([r[i] if i < len(r) else "" for i in range(len(cols))]))
    return "\n".join(lines)


def pluck(value: Any, path: str) -> Any:
    tokens = re.findall(r"[^.\[\]]+|\[\d*\]", path)
    if not tokens:
        raise CliError(f'Invalid --pluck path "{path}".')
    current: list[Any] = [value]
    for token in tokens:
        nxt: list[Any] = []
        for v in current:
            if token == "[]":
                if isinstance(v, list):
                    nxt.extend(v)
                elif isinstance(v, dict):
                    nxt.extend(v.values())
                else:
                    nxt.append(None)
            elif re.match(r"^\[\d+\]$", token):
                idx = int(token[1:-1])
                nxt.append(v[idx] if isinstance(v, list) and idx < len(v) else None)
            else:
                nxt.append(v.get(token) if isinstance(v, dict) else None)
        current = nxt
    return current if "[]" in path else current[0]


def _scalar_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    return json.dumps(v)


def render_pluck(value: Any, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(value, indent=2)
    if fmt == "jsonl":
        return json.dumps(value)
    if isinstance(value, list):
        return "\n".join(_scalar_text(v) for v in value)
    return _scalar_text(value)


def emit(opts: OutputOptions, payload: Any, view_fn: Callable[[], View]) -> None:
    stream = opts.stream or sys.stdout
    if opts.pluck:
        value = pluck(payload, opts.pluck)
        empty = value is None or (isinstance(value, list) and all(v is None for v in value))
        if empty:
            raise CliError(f'--pluck path "{opts.pluck}" matched nothing in this result.')
        stream.write(render_pluck(value, opts.format) + "\n")
        return
    if opts.format == "json":
        stream.write(json.dumps(payload, indent=2) + "\n")
        return
    if opts.format == "jsonl":
        stream.write(json.dumps(payload) + "\n")
        return
    view = view_fn()
    if opts.format == "md":
        stream.write(render_markdown(view, opts.quiet) + "\n")
        return
    if opts.format == "csv":
        stream.write(render_delimited(view, ",") + "\n")
        return
    if opts.format == "tsv":
        stream.write(render_delimited(view, "\t") + "\n")
        return
    stream.write(render_text(view, opts.color, opts.quiet) + "\n")
