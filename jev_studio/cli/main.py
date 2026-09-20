"""jev CLI entry point: TypeSafe's Jev model at the command line."""
from __future__ import annotations

import argparse
import os
import sys

from .commands import (
    register_ask,
    register_auth,
    register_batch,
    register_classify,
    register_compact,
    register_config,
    register_extract,
    register_find,
    register_match,
    register_models,
    register_rerank,
    register_route,
    register_screen,
    register_update,
    register_verify,
)
from .context import build_context
from .errors import CliError, Exit, describe_error

HELP_FOOTER = """
Examples:
  jev verify "Helmets are optional for adults" --evidence @ordinance.txt
  curl -s https://example.com | jev screen --purpose "extract pricing" --fail-on block,review
  jev classify "The invoice total is wrong" --labels billing,bug,feature --json
  jev find "how do I rotate API keys" --files 'docs/*.md' -k 3
  jev batch -i @tickets.txt -- classify --labels billing,technical,sales

Exit codes:
  0  success
  1  usage, configuration, input, or transport error
  2  a --fail-on judgment condition matched (e.g. a contradicted claim)

Credentials (first found wins; environment first, then `jev auth login` store):
  TYPESAFE_API_KEY                                https://console.typesafe.ai/settings/keys
  OPENROUTER_API_KEY (sk-or-...)                  OpenRouter Decisions API
  CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID    Cloudflare Workers AI

Docs: https://docs.typesafe.ai  ·  Per-command help: jev <command> --help
"""


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("jev-studio")
    except PackageNotFoundError:
        return "0.0.0"


def _global_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    out = p.add_argument_group("Output")
    out.add_argument("--json", action="store_true", help="print results as JSON (same as --format json)")
    out.add_argument("--md", action="store_true", help="Markdown output (same as --format md)")
    out.add_argument("--format", metavar="FMT", help="text, json, jsonl, csv, tsv, or md")
    out.add_argument("--pluck", metavar="PATH", help="print one value from the JSON result, e.g. label or results[].verdict")
    out.add_argument("-q", "--quiet", action="store_true", help="omit the usage/model footer in text output")
    out.add_argument("--no-color", dest="no_color", action="store_true", help="disable colored output")
    net = p.add_argument_group("Model and transport")
    net.add_argument("-m", "--model", metavar="NAME", help="Jev model, e.g. jev-latest or jev-1.13.0")
    net.add_argument("-P", "--provider", metavar="NAME", help="auto, typesafe, openrouter, or cloudflare")
    net.add_argument("--timeout", metavar="MS", help="per-request timeout in milliseconds")
    net.add_argument("--dry-run", dest="dry_run", action="store_true", help="print the request, cwd, config sources, and resolved-bundle sha256, then exit")
    return p


def build_parser() -> argparse.ArgumentParser:
    globals_parser = _global_parser()
    parser = argparse.ArgumentParser(
        prog="jev",
        description="TypeSafe's Jev model at the command line (jev-studio).",
        epilog=HELP_FOOTER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[globals_parser],
    )
    parser.add_argument("-V", "--version", action="version", version=f"jev-studio {_version()}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True, parser_class=argparse.ArgumentParser)
    # Monkey-patch so each add_parser() attaches the global flags too.
    orig_add_parser = sub.add_parser

    def add_parser(name, **kwargs):
        kwargs.setdefault("parents", [])
        kwargs["parents"] = [*kwargs["parents"], globals_parser]
        return orig_add_parser(name, **kwargs)

    sub.add_parser = add_parser  # type: ignore[assignment]

    # Registration order = order shown in --help.
    register_verify(sub)
    register_screen(sub)
    register_classify(sub)
    register_extract(sub)
    register_match(sub)
    register_route(sub)
    register_ask(sub)
    register_find(sub)
    register_rerank(sub)
    register_compact(sub)
    register_batch(sub)
    register_models(sub)
    register_auth(sub)
    register_config(sub)
    register_update(sub)
    return parser


def _global_flags(ns: argparse.Namespace) -> dict:
    return {
        "json": getattr(ns, "json", False),
        "md": getattr(ns, "md", False),
        "format": getattr(ns, "format", None),
        "pluck": getattr(ns, "pluck", None),
        "quiet": getattr(ns, "quiet", False),
        "no_color": getattr(ns, "no_color", False),
        "model": getattr(ns, "model", None),
        "provider": getattr(ns, "provider", None),
        "timeout": getattr(ns, "timeout", None),
        "dry_run": getattr(ns, "dry_run", False),
    }


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        ctx = build_context(_global_flags(args), env=dict(os.environ))
        code = args.func(args, ctx)
        if code and code != Exit.OK:
            sys.exit(code)
    except CliError as err:
        sys.stderr.write(f"jev: {err}\n")
        sys.exit(err.exit_code)
    except KeyboardInterrupt:
        sys.stderr.write("jev: interrupted\n")
        sys.exit(130)
    except Exception as err:
        sys.stderr.write(f"jev: {describe_error(err)}\n")
        if os.environ.get("JEV_DEBUG") == "1":
            import traceback

            traceback.print_exc()
        sys.exit(Exit.ERROR)


if __name__ == "__main__":
    main()
