"""Per-command argparse setup + action functions + view renderers."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import core
from .config import (
    DEFAULTS,
    config_path,
    known_config_keys,
    read_config_file,
    set_config_value,
    unset_config_value,
    write_config_file,
)
from .context import CommandContext
from .credentials import CREDENTIAL_PROVIDERS, ENV_VAR, resolve_credentials, resolve_store
from .errors import CliError, Exit
from .io_utils import (
    OutputOptions,
    View,
    clip,
    emit,
    format_probability,
    paint,
    parse_items,
    parse_json,
    parse_list,
    read_input,
    reference_id,
)
from .provider import list_models
from .utils import parse_fail_on, parse_probability


def _dry_run_envelope(command: str, ctx: CommandContext, request: dict[str, Any]) -> dict[str, Any]:
    """Envelope printed by --dry-run: request + cwd + config provenance + bundle hash."""
    return {
        "dry_run": True,
        "command": command,
        "cwd": os.getcwd(),
        "provider": ctx.config["provider"],
        "model": ctx.config["model"],
        "request": request,
        "provenance": ctx.provenance,
    }


def _emit_dry_run(command: str, ctx: CommandContext, request: dict[str, Any]) -> int:
    emit(
        OutputOptions(format="json", color=False, quiet=False, stream=ctx.output.stream),
        _dry_run_envelope(command, ctx, request),
        lambda: View(),
    )
    return Exit.OK


# ── verify ──────────────────────────────────────────────────────────────────


def _collect_evidence(args: argparse.Namespace) -> list[dict]:
    items: list[dict] = []
    for ref in args.evidence or []:
        rid = reference_id(ref)
        text = read_input(ref, "evidence")
        items.append({"id": rid, "text": text} if rid else {"text": text})
    if args.evidence_json:
        items.extend(parse_items(read_input(args.evidence_json, "evidence JSON"), "evidence"))
    if not items:
        raise CliError("Provide evidence with --evidence <text|@file|-> or --evidence-json <ref>.")
    return items


def _collect_claims(args: argparse.Namespace) -> list[str]:
    claims = list(args.claim_args or [])
    if args.claims:
        claims.extend(parse_list(read_input(args.claims, "claims"), "claims"))
    if not claims:
        raise CliError("Provide at least one claim as an argument or with --claims <@file|->.")
    if any(not c.strip() for c in claims):
        raise CliError("A claim must not be empty.")
    return claims


def _view_verify(out: dict, color: bool) -> View:
    def verdict_style(v: str) -> str:
        return paint(color, {"verified": "green", "contradicted": "red", "unsupported": "yellow"}.get(v, "dim"), v)

    multi_source = any(r["supporting_evidence"] is not None for r in out["results"])
    columns = ["#", "Verdict", "Conf", "Action", "Claim"]
    if multi_source:
        columns.append("Source")
    rows = []
    for i, r in enumerate(out["results"]):
        row = [
            str(i + 1),
            verdict_style(r["verdict"]),
            format_probability(r["confidence"]),
            paint(color, "yellow", "review") if r["action"] == "review" else "auto",
            clip(r["claim"], 70),
        ]
        if multi_source:
            row.append(r["supporting_evidence"] or "-")
        rows.append(row)
    s = out["summary"]
    return View(
        table={"columns": columns, "rows": rows},
        tail=[
            f'{s["verified"]} verified · {s["contradicted"]} contradicted · '
            f'{s["unsupported"]} unsupported · {s["needs_review"]} need review '
            f'(auto-accept ≥ {out["auto_accept"]})'
        ],
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_verify(args: argparse.Namespace, ctx: CommandContext) -> int:
    claims = _collect_claims(args)
    evidence = _collect_evidence(args)
    auto_accept = parse_probability("--auto-accept", args.auto_accept, ctx.config["verify"]["autoAccept"])
    fail_on = parse_fail_on(args.fail_on, core.VERIFY_FAIL_CONDITIONS, ["contradicted"])
    if ctx.dry_run:
        req = core.build_verify_request(claims, evidence)
        return _emit_dry_run("verify", ctx, {"state": req["state"], "questions": req["questions"]})
    output = core.run_verify(ctx.ask(), claims, evidence, auto_accept)
    emit(ctx.output, output, lambda: _view_verify(output, ctx.output.color))
    return Exit.JUDGMENT if core.verify_failed(output, fail_on) else Exit.OK


def register_verify(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "verify",
        help="Check claims against evidence; verdict + probabilities per claim",
        description="Check claims against evidence. Each claim gets a verdict, probability distribution, and confidence.",
    )
    p.add_argument("claim_args", nargs="*", help="claims to verify (or use --claims)")
    p.add_argument("-e", "--evidence", action="append", metavar="REF", help="evidence text, @file, or - for stdin (repeatable)")
    p.add_argument("--evidence-json", metavar="REF", help="JSON evidence: array of strings, array of {id,text}, or {id: text} map")
    p.add_argument("-c", "--claims", metavar="REF", help="claims from @file or - (one per line, or a JSON array)")
    p.add_argument("--auto-accept", metavar="P", help="confidence at or above which a verdict stands (default 0.8)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 when any result matches: {",".join(core.VERIFY_FAIL_CONDITIONS)}, none (default contradicted)')
    p.set_defaults(func=_cmd_verify)


# ── screen ──────────────────────────────────────────────────────────────────


def _view_screen(out: dict, color: bool) -> View:
    p = out["probabilities"]
    rec = out["recommendation"]
    action_color = {"pass": "green", "review": "yellow", "block": "red", "skip": "dim"}[rec["action"]]
    kv = [
        ("action", paint(color, action_color, rec["action"])),
        ("reason", rec["reason"]),
        ("injection", format_probability(p["injection"])),
    ]
    if p["substance"] is not None:
        kv.append(("substance", format_probability(p["substance"])))
    if p["relevance"] is not None:
        kv.append(("relevance", format_probability(p["relevance"])))
    kv.append(("thresholds", f'block ≥ {out["thresholds"]["block_at"]} · review ≥ {out["thresholds"]["review_at"]}'))
    return View(
        kv=kv,
        table={"columns": ["Field", "Value"], "rows": [[k, v] for k, v in kv]},
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_screen(args: argparse.Namespace, ctx: CommandContext) -> int:
    if args.text:
        text = read_input(args.text, "text")
    else:
        text = read_input("-", "text")
    block_at = parse_probability("--block-at", args.block_at, ctx.config["screen"]["blockAt"])
    review_at = parse_probability("--review-at", args.review_at, ctx.config["screen"]["reviewAt"])
    fail_on = parse_fail_on(args.fail_on, core.SCREEN_FAIL_CONDITIONS, ["block"])
    if ctx.dry_run:
        req = core.build_screen_request(text, args.purpose)
        return _emit_dry_run("screen", ctx, dict(req))
    out = core.run_screen(ctx.ask(), text, args.purpose, block_at, review_at)
    emit(ctx.output, out, lambda: _view_screen(out, ctx.output.color))
    return Exit.JUDGMENT if core.screen_failed(out, fail_on) else Exit.OK


def register_screen(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "screen",
        help="Flag prompt injection, filler, and irrelevance before an agent reads text",
        description="Screen text before it reaches an agent. Detects prompt injection, empty/boilerplate content, and irrelevance.",
    )
    p.add_argument("text", nargs="?", help="text, @file, or - for stdin (defaults to stdin)")
    p.add_argument("-p", "--purpose", metavar="TEXT", help="the agent's task; enables relevance scoring")
    p.add_argument("--block-at", metavar="P", help="injection prob at/above which action=block (default 0.75)")
    p.add_argument("--review-at", metavar="P", help="injection prob at/above which action=review (default 0.25)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 when action matches: {",".join(core.SCREEN_FAIL_CONDITIONS)}, none (default block)')
    p.set_defaults(func=_cmd_screen)


# ── classify ────────────────────────────────────────────────────────────────


def _view_classify(out: dict, color: bool) -> View:
    if out["mode"] == "multi":
        rows = [[l["label"], format_probability(l["probability"]), "yes" if l["applies"] else "no"] for l in out["labels"]]
        return View(
            table={"columns": ["Label", "Prob", "Applies"], "rows": rows},
            tail=[f'applied: {", ".join(out["applied"]) or "(none)"} (threshold {out["threshold"]})'],
            usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
        )
    if out["mode"] == "taxonomy":
        rows = [[s["label"], format_probability(s["confidence"])] for s in out["steps"]]
        return View(
            table={"columns": ["Step", "Conf"], "rows": rows},
            tail=[f'path: {" > ".join(out["path"])} · action {out["action"]}'],
            usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
        )
    kv = [
        ("label", out["label"] or "-"),
        ("confidence", format_probability(out["confidence"])),
        ("action", paint(color, "yellow" if out["action"] == "review" else "green", out["action"])),
    ]
    return View(
        kv=kv,
        table={"columns": ["Field", "Value"], "rows": [[k, v] for k, v in kv]},
        tail=[f'min_confidence={out["min_confidence"]}'],
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _classify_labels(args: argparse.Namespace) -> list[dict]:
    if args.labels_json:
        return core.parse_label_json(parse_json(read_input(args.labels_json, "labels JSON"), "labels"))
    if args.labels:
        return core.parse_label_list(args.labels)
    raise CliError("Provide --labels <list> or --labels-json <ref>.")


def _cmd_classify(args: argparse.Namespace, ctx: CommandContext) -> int:
    text = read_input(args.text or "-", "text")
    fail_on = parse_fail_on(args.fail_on, core.CLASSIFY_FAIL_CONDITIONS, ["review"])
    if args.taxonomy:
        taxonomy = core.parse_taxonomy(parse_json(read_input(args.taxonomy, "taxonomy"), "taxonomy"))
        min_conf = parse_probability("--min-confidence", args.min_confidence, ctx.config["classify"]["minConfidence"])
        out = core.run_classify_taxonomy(ctx.ask(), text, taxonomy, args.instructions, args.other, min_conf)
    elif args.multi:
        labels = _classify_labels(args)
        threshold = parse_probability("--threshold", args.threshold, ctx.config["classify"]["threshold"])
        out = core.run_classify_multi(ctx.ask(), text, labels, args.instructions, threshold)
    else:
        labels = _classify_labels(args)
        min_conf = parse_probability("--min-confidence", args.min_confidence, ctx.config["classify"]["minConfidence"])
        out = core.run_classify(ctx.ask(), text, labels, args.instructions, args.other, min_conf)
    emit(ctx.output, out, lambda: _view_classify(out, ctx.output.color))
    return Exit.JUDGMENT if core.classify_failed(out, fail_on) else Exit.OK


def register_classify(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "classify",
        help="Assign one, several, or hierarchical labels with confidence",
        description="Classify text. Single-label (default), multi-label (--multi), or taxonomy (--taxonomy).",
    )
    p.add_argument("text", nargs="?", help="text, @file, or - for stdin (defaults to stdin)")
    p.add_argument("-l", "--labels", metavar="LIST", help="comma-separated labels; append :description to any")
    p.add_argument("--labels-json", metavar="REF", help="JSON labels: array of strings, {label, description}, or {label: desc}")
    p.add_argument("--taxonomy", metavar="REF", help="JSON taxonomy tree; overrides --labels")
    p.add_argument("--multi", action="store_true", help="assign every label independently (multi-label)")
    p.add_argument("--other", action="store_true", help="add an escape 'other' option (single/taxonomy)")
    p.add_argument("-i", "--instructions", metavar="TEXT", help="override the default question")
    p.add_argument("--min-confidence", metavar="P", help="auto vs review threshold (single/taxonomy)")
    p.add_argument("--threshold", metavar="P", help="prob at/above which a multi-label applies (default 0.5)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on: {",".join(core.CLASSIFY_FAIL_CONDITIONS)}, none (default review)')
    p.set_defaults(func=_cmd_classify)


# ── extract ─────────────────────────────────────────────────────────────────


def _view_extract(out: dict) -> View:
    rows = [
        [name, str(f["value"] or "-"), format_probability(f["confidence"]), f["action"], str(f["candidates"])]
        for name, f in out["fields"].items()
    ]
    return View(
        table={"columns": ["Field", "Value", "Conf", "Action", "Cands"], "rows": rows},
        tail=[f'min_confidence={out["min_confidence"]}'],
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_extract(args: argparse.Namespace, ctx: CommandContext) -> int:
    text = read_input(args.text or "-", "text")
    if not args.want:
        raise CliError("Provide at least one field with --want <spec>.")
    fields = [core.parse_field_spec(w) for w in args.want]
    min_conf = parse_probability("--min-confidence", args.min_confidence, ctx.config["extract"]["minConfidence"])
    fail_on = parse_fail_on(args.fail_on, core.EXTRACT_FAIL_CONDITIONS, ["missing"])
    if ctx.dry_run:
        req = core.build_extract_request(text, fields, args.context)
        return _emit_dry_run("extract", ctx, {"state": req["state"], "questions": req["questions"]})
    out = core.run_extract(ctx.ask(), text, fields, args.context, min_conf)
    emit(ctx.output, out, lambda: _view_extract(out))
    return Exit.JUDGMENT if core.extract_failed(out, fail_on) else Exit.OK


def register_extract(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "extract",
        help="Pull typed values out of text (regex candidates, Jev picks, code normalizes)",
        description="Extract typed values without hallucination: regex proposes, Jev picks, code normalizes.",
    )
    p.add_argument("text", nargs="?", help="text, @file, or - for stdin (defaults to stdin)")
    p.add_argument("-w", "--want", action="append", metavar="SPEC",
                   help="field spec: builtin name, name=/regex/:desc, or name=builtin:desc (repeatable)")
    p.add_argument("--context", metavar="TEXT", help="what kind of document (e.g. 'an invoice')")
    p.add_argument("--min-confidence", metavar="P", help="auto vs review threshold (default 0.6)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on: {",".join(core.EXTRACT_FAIL_CONDITIONS)}, none (default missing)')
    p.set_defaults(func=_cmd_extract)


# ── match ───────────────────────────────────────────────────────────────────


def _view_match(out: dict, color: bool) -> View:
    rows = []
    for r in out["results"]:
        style = {"same": "green", "different": "red", "unclear": "yellow"}[r["decision"]]
        rows.append([r["left"], r["right"], paint(color, style, r["decision"]), format_probability(r["confidence"])])
    s = out["summary"]
    return View(
        table={"columns": ["Left", "Right", "Decision", "Conf"], "rows": rows},
        tail=[f'{s["same"]} same · {s["unclear"]} unclear · {s["different"]} different'],
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_match(args: argparse.Namespace, ctx: CommandContext) -> int:
    if args.pairs:
        raw = parse_json(read_input(args.pairs, "pairs"), "pairs")
        if not isinstance(raw, list):
            raise CliError("Pairs JSON must be an array of {left,right} objects.")
        pairs = []
        for i, p in enumerate(raw):
            if not (isinstance(p, dict) and isinstance(p.get("left"), dict) and isinstance(p.get("right"), dict)):
                raise CliError(f"pairs[{i}] must be an object with left and right objects.")
            pairs.append(p)
    elif args.a and args.b:
        left = parse_items(read_input(args.a, "a"), "a")
        right = parse_items(read_input(args.b, "b"), "b")
        pairs = core.cross_pairs(left, right)
    elif args.items:
        items = parse_items(read_input(args.items, "items"), "items")
        pairs = core.all_pairs(items)
    else:
        raise CliError("Provide --pairs <ref>, or --items <ref>, or --a and --b.")
    fail_on = parse_fail_on(args.fail_on, core.MATCH_FAIL_CONDITIONS, [])
    out = core.run_match(ctx.ask(), pairs, args.kind)
    emit(ctx.output, out, lambda: _view_match(out, ctx.output.color))
    return Exit.JUDGMENT if core.match_failed(out, fail_on) else Exit.OK


def register_match(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "match",
        help="Decide if record pairs are the same thing: same, different, or unclear",
        description="Entity matching: decide if pairs describe the same thing. same / different / unclear.",
    )
    p.add_argument("--pairs", metavar="REF", help="JSON array of {left, right} where each side is {id?, text}")
    p.add_argument("--items", metavar="REF", help="one list; all i<j pairs are compared")
    p.add_argument("--a", metavar="REF", help="left-side list (use with --b for a cross product)")
    p.add_argument("--b", metavar="REF", help="right-side list (use with --a for a cross product)")
    p.add_argument("--kind", metavar="TEXT", help="what the records are, e.g. 'products in a catalogue'")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on any: {",".join(core.MATCH_FAIL_CONDITIONS)}, none')
    p.set_defaults(func=_cmd_match)


# ── route ───────────────────────────────────────────────────────────────────


def _view_route(out: dict, color: bool) -> View:
    kv = [
        ("handler", out["handler"] or "-"),
        ("confidence", format_probability(out["confidence"])),
        ("action", paint(color, "yellow" if out["action"] == "review" else "green", out["action"])),
    ]
    for arg, val in (out.get("args") or {}).items():
        kv.append((f"arg.{arg}", str(val.get("value") if val.get("value") is not None else "-")))
    return View(
        kv=kv,
        table={"columns": ["Field", "Value"], "rows": [[k, v] for k, v in kv]},
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_route(args: argparse.Namespace, ctx: CommandContext) -> int:
    request = read_input(args.request or "-", "request")
    try:
        state: Any = json.loads(request)
    except json.JSONDecodeError:
        state = request
    if args.handlers_json:
        handlers = core.parse_handlers(parse_json(read_input(args.handlers_json, "handlers"), "handlers"))
    elif args.handlers:
        handlers = core.parse_handler_list(args.handlers)
    else:
        raise CliError("Provide --handlers <list> or --handlers-json <ref>.")
    min_conf = parse_probability("--min-confidence", args.min_confidence, ctx.config["route"]["minConfidence"])
    fail_on = parse_fail_on(args.fail_on, core.ROUTE_FAIL_CONDITIONS, ["unrouted"])
    out = core.run_route(ctx.ask(), state, handlers, args.instructions, min_conf)
    emit(ctx.output, out, lambda: _view_route(out, ctx.output.color))
    return Exit.JUDGMENT if core.route_failed(out, fail_on) else Exit.OK


def register_route(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "route",
        help="Pick a handler for a request and fill its arguments from closed sets",
        description="Pick which handler should process a request, and fill closed-set arguments in one call.",
    )
    p.add_argument("request", nargs="?", help="request text, @file, or - (JSON parsed if valid)")
    p.add_argument("-H", "--handlers", metavar="LIST", help="comma-separated handlers; append :description")
    p.add_argument("--handlers-json", metavar="REF", help="handlers as JSON (supports args)")
    p.add_argument("-i", "--instructions", metavar="TEXT", help="override the default routing question")
    p.add_argument("--min-confidence", metavar="P", help="auto vs review threshold (default 0.6)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on: {",".join(core.ROUTE_FAIL_CONDITIONS)}, none (default unrouted)')
    p.set_defaults(func=_cmd_route)


# ── ask ─────────────────────────────────────────────────────────────────────


def _cmd_ask(args: argparse.Namespace, ctx: CommandContext) -> int:
    if args.state_json:
        state = parse_json(read_input(args.state_json, "state"), "state")
    else:
        state = read_input(args.state or "-", "state")
    if args.questions_json:
        questions = core.parse_questions(parse_json(read_input(args.questions_json, "questions"), "questions"))
    else:
        questions = core.questions_from_flags(args.noul or [], args.choice or [], args.score or [])
    if ctx.dry_run:
        return _emit_dry_run("ask", ctx, {"state": state, "questions": questions})
    out = core.run_ask(ctx.ask(), state, questions)
    emit(ctx.output, out, lambda: View(
        kv=[(k, json.dumps(v)) for k, v in out["answers"].items()],
        table={"columns": ["Question", "Answer"], "rows": [[k, json.dumps(v)] for k, v in out["answers"].items()]},
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    ))
    return Exit.OK


def register_ask(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ask",
        help="Ask raw yes/no, choice, or score questions about any state",
        description="Raw System One passthrough: any state, any typed questions, typed answers back.",
    )
    p.add_argument("state", nargs="?", help="state text, @file, or - (defaults to stdin)")
    p.add_argument("--state-json", metavar="REF", help="state as JSON")
    p.add_argument("--noul", action="append", metavar="[ID=]TEXT", help="yes/no question (repeatable)")
    p.add_argument("--choice", action="append", metavar="[ID=]TEXT|a,b:desc", help="choice question")
    p.add_argument("--score", action="append", metavar="[ID=]TEXT|lvl0,lvl1,...", help="score question")
    p.add_argument("-Q", "--questions-json", metavar="REF", help="questions as JSON")
    p.set_defaults(func=_cmd_ask)


# ── find ────────────────────────────────────────────────────────────────────


def _view_find(out: dict, color: bool) -> View:
    rows = [[str(i + 1), h["id"], format_probability(h["probability"]), clip(h["text"], 60)] for i, h in enumerate(out["top"])]
    verdict_color = {"answered": "green", "partial": "yellow", "absent": "red"}[out["exists_verdict"]]
    return View(
        table={"columns": ["#", "Id", "Prob", "Text"], "rows": rows},
        tail=[
            f'exists {format_probability(out["exists"])} → {paint(color, verdict_color, out["exists_verdict"])}',
        ],
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _load_candidates(args: argparse.Namespace) -> list[dict]:
    items: list[dict] = []
    if args.files:
        for path in args.files:
            for p in _expand_glob(path):
                items.append({"id": os.path.basename(p), "text": read_input(f"@{p}", "candidate")})
    if args.candidates_json:
        items.extend(parse_items(read_input(args.candidates_json, "candidates"), "candidates"))
    if args.candidates:
        for c in parse_list(read_input(args.candidates, "candidates"), "candidates"):
            items.append({"text": c})
    return items


def _expand_glob(pattern: str) -> list[str]:
    import glob

    if any(ch in pattern for ch in ("*", "?", "[")):
        return sorted(glob.glob(pattern, recursive=True))
    return [pattern]


def _cmd_find(args: argparse.Namespace, ctx: CommandContext) -> int:
    candidates = _load_candidates(args)
    if not candidates:
        raise CliError("Provide candidates with --files, --candidates <@file|->, or --candidates-json.")
    top_k = int(args.top_k) if args.top_k is not None else ctx.config["find"]["topK"]
    found = parse_probability("--found", args.found, ctx.config["find"]["found"])
    absent = parse_probability("--absent", args.absent, ctx.config["find"]["absent"])
    fail_on = parse_fail_on(args.fail_on, core.FIND_FAIL_CONDITIONS, [])
    out = core.run_find(ctx.ask(), args.query, candidates, top_k, found, absent)
    emit(ctx.output, out, lambda: _view_find(out, ctx.output.color))
    return Exit.JUDGMENT if core.find_failed(out, fail_on) else Exit.OK


def register_find(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "find",
        help="Rank up to 250 candidates against a plain-language query",
        description="Rank candidates against a query. Returns top-K and a document-level exists verdict.",
    )
    p.add_argument("query", help="the query in plain language")
    p.add_argument("--files", nargs="+", metavar="PATH", help="candidate files (globs OK)")
    p.add_argument("--candidates", metavar="REF", help="candidates from @file or - (one per line)")
    p.add_argument("--candidates-json", metavar="REF", help="candidates as JSON")
    p.add_argument("-k", "--top-k", type=int, metavar="N", help="how many hits to return (default 5)")
    p.add_argument("--found", metavar="P", help="exists threshold for 'answered' (default 0.7)")
    p.add_argument("--absent", metavar="P", help="exists threshold below which 'absent' (default 0.35)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on: {",".join(core.FIND_FAIL_CONDITIONS)}, none')
    p.set_defaults(func=_cmd_find)


# ── rerank ──────────────────────────────────────────────────────────────────


def _view_rerank(out: dict) -> View:
    rows = [
        [str(i + 1), h["id"], format_probability(h["relevance"]), "keep" if h["kept"] else "drop", clip(h["text"], 60)]
        for i, h in enumerate(out["ranked"])
    ]
    return View(
        table={"columns": ["#", "Id", "Rel", "Verdict", "Text"], "rows": rows},
        tail=[f'kept {len(out["kept"])} · min {out["min"]}'],
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_rerank(args: argparse.Namespace, ctx: CommandContext) -> int:
    candidates = _load_candidates(args)
    if not candidates:
        raise CliError("Provide candidates with --files, --candidates <@file|->, or --candidates-json.")
    top_k = int(args.top_k) if args.top_k is not None else ctx.config["rerank"]["topK"]
    min_rel = parse_probability("--min", args.min, ctx.config["rerank"]["min"])
    fail_on = parse_fail_on(args.fail_on, core.RERANK_FAIL_CONDITIONS, [])
    out = core.run_rerank(ctx.ask(), args.query, candidates, top_k, min_rel, args.criteria)
    emit(ctx.output, out, lambda: _view_rerank(out))
    return Exit.JUDGMENT if core.rerank_failed(out, fail_on) else Exit.OK


def register_rerank(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "rerank",
        help="Score each candidate's relevance independently and sort",
        description="Score each candidate's relevance to a query independently. Several can be relevant, or none.",
    )
    p.add_argument("query", help="the query")
    p.add_argument("--files", nargs="+", metavar="PATH", help="candidate files (globs OK)")
    p.add_argument("--candidates", metavar="REF", help="candidates from @file or -")
    p.add_argument("--candidates-json", metavar="REF", help="candidates as JSON")
    p.add_argument("-k", "--top-k", type=int, metavar="N", help="how many to return (default 10)")
    p.add_argument("--min", metavar="P", help="min relevance to keep (default 0.5)")
    p.add_argument("--criteria", metavar="TEXT", help="what counts as relevant")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on: {",".join(core.RERANK_FAIL_CONDITIONS)}, none')
    p.set_defaults(func=_cmd_rerank)


# ── compact ─────────────────────────────────────────────────────────────────


def _view_compact(out: dict) -> View:
    kv = [
        ("reduction", format_probability(out["reduction"])),
        ("worth_it", "yes" if out["worth_it"] else "no"),
        ("considered", str(out["stats"]["considered"])),
        ("dropped", str(out["stats"]["dropped"])),
        ("orig_tokens", str(out["stats"]["original_tokens"])),
        ("compact_tokens", str(out["stats"]["compacted_tokens"])),
    ]
    return View(
        kv=kv,
        table={"columns": ["Field", "Value"], "rows": [[k, v] for k, v in kv]},
        usage={"usage": out["usage"], "model": out["model"], "provider": out["provider"]},
    )


def _cmd_compact(args: argparse.Namespace, ctx: CommandContext) -> int:
    messages = parse_json(read_input(args.transcript or "-", "transcript"), "transcript")
    if not isinstance(messages, list):
        raise CliError("Transcript must be a JSON array of messages.")
    cfg = ctx.config["compact"]
    keep_threshold = parse_probability("--keep-threshold", args.keep_threshold, cfg["keepThreshold"])
    min_reduction = parse_probability("--min-reduction", args.min_reduction, cfg["minReduction"])
    fail_on = parse_fail_on(args.fail_on, core.COMPACT_FAIL_CONDITIONS, [])
    out = core.run_compact(
        ctx.ask(),
        messages,
        keep_threshold=keep_threshold,
        preserve_recent=int(args.preserve_recent) if args.preserve_recent is not None else cfg["preserveRecent"],
        max_state_tokens=int(args.max_state_tokens) if args.max_state_tokens is not None else cfg["maxStateTokens"],
        max_request_tokens=int(args.max_request_tokens) if args.max_request_tokens is not None else cfg["maxRequestTokens"],
        truncate_head=int(args.truncate_head) if args.truncate_head is not None else cfg["truncateHead"],
        min_reduction=min_reduction,
    )
    emit(ctx.output, out, lambda: _view_compact(out))
    return Exit.JUDGMENT if core.compact_failed(out, fail_on) else Exit.OK


def register_compact(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "compact",
        help="Shrink an agent transcript by dropping stale tool calls, verbatim otherwise",
        description="Verbatim transcript compaction: ask Jev which older tool calls still matter, drop the rest.",
    )
    p.add_argument("transcript", nargs="?", help="JSON transcript, @file, or - (defaults to stdin)")
    p.add_argument("--keep-threshold", metavar="P", help="keep prob at/above which a tool call stays (default 0.5)")
    p.add_argument("--preserve-recent", metavar="N", help="how many recent turns to keep verbatim (default 6)")
    p.add_argument("--max-state-tokens", metavar="N", help="soft cap on transcript state tokens (default 25000)")
    p.add_argument("--max-request-tokens", metavar="N", help="soft cap on request tokens (default 30000)")
    p.add_argument("--truncate-head", metavar="N", help="truncate each candidate to N chars (default 300)")
    p.add_argument("--min-reduction", metavar="P", help="fail-on threshold for worth-it (default 0.25)")
    p.add_argument("--fail-on", metavar="LIST", help=f'exit 2 on: {",".join(core.COMPACT_FAIL_CONDITIONS)}, none')
    p.set_defaults(func=_cmd_compact)


# ── batch ───────────────────────────────────────────────────────────────────


def _cmd_batch(args: argparse.Namespace, ctx: CommandContext) -> int:
    if not args.command_args:
        raise CliError("Batch needs a sub-command after `--`. Example: jev batch classify -i @rows.txt -- --labels a,b.")
    sub_name, *sub_argv = args.command_args
    rows = core.parse_rows(read_input(args.input, "batch input"))
    concurrency = int(args.concurrency) if args.concurrency is not None else ctx.config["batch"]["concurrency"]
    fmt = ctx.output.format
    if fmt not in ("jsonl", "json"):
        ctx.output = OutputOptions(format="jsonl", color=ctx.output.color, quiet=ctx.output.quiet, stream=ctx.output.stream)

    # Build a per-row runner by parsing the sub-command flags once.
    runner = _make_batch_runner(sub_name, sub_argv, ctx)

    def emit_row(rec: dict) -> None:
        sys.stdout.write(json.dumps(rec) + "\n")
        sys.stdout.flush()

    result = core.run_batch(rows, runner, concurrency, on_record=None if args.no_stream else emit_row)
    if args.no_stream:
        for rec in result["records"]:
            sys.stdout.write(json.dumps(rec) + "\n")
    sys.stderr.write(json.dumps({"summary": result["summary"]}) + "\n")
    return Exit.OK


def _make_batch_runner(name: str, argv: list[str], ctx: CommandContext):
    from types import SimpleNamespace

    if name == "classify":
        sub = argparse.ArgumentParser(add_help=False)
        sub.add_argument("-l", "--labels")
        sub.add_argument("--labels-json")
        sub.add_argument("--multi", action="store_true")
        sub.add_argument("--other", action="store_true")
        sub.add_argument("-i", "--instructions")
        sub.add_argument("--min-confidence")
        sub.add_argument("--threshold")
        sub.add_argument("--fail-on")
        sf = sub.parse_args(argv)
        fail_on = parse_fail_on(sf.fail_on, core.CLASSIFY_FAIL_CONDITIONS, ["review"])
        labels_ns = SimpleNamespace(labels=sf.labels, labels_json=sf.labels_json)
        labels = _classify_labels(labels_ns)
        min_conf = parse_probability("--min-confidence", sf.min_confidence, ctx.config["classify"]["minConfidence"])
        threshold = parse_probability("--threshold", sf.threshold, ctx.config["classify"]["threshold"])

        def run(row: dict) -> dict:
            if sf.multi:
                out = core.run_classify_multi(ctx.ask(), row["state"], labels, sf.instructions, threshold)
            else:
                out = core.run_classify(ctx.ask(), row["state"], labels, sf.instructions, sf.other, min_conf)
            return {"output": out, "failed": core.classify_failed(out, fail_on)}

        return run

    if name == "screen":
        sub = argparse.ArgumentParser(add_help=False)
        sub.add_argument("-p", "--purpose")
        sub.add_argument("--block-at")
        sub.add_argument("--review-at")
        sub.add_argument("--fail-on")
        sf = sub.parse_args(argv)
        block_at = parse_probability("--block-at", sf.block_at, ctx.config["screen"]["blockAt"])
        review_at = parse_probability("--review-at", sf.review_at, ctx.config["screen"]["reviewAt"])
        fail_on = parse_fail_on(sf.fail_on, core.SCREEN_FAIL_CONDITIONS, ["block"])

        def run(row: dict) -> dict:
            out = core.run_screen(ctx.ask(), row["text"], sf.purpose, block_at, review_at)
            return {"output": out, "failed": core.screen_failed(out, fail_on)}

        return run

    if name == "verify":
        sub = argparse.ArgumentParser(add_help=False)
        sub.add_argument("-e", "--evidence", action="append")
        sub.add_argument("--evidence-json")
        sub.add_argument("--auto-accept")
        sub.add_argument("--fail-on")
        sf = sub.parse_args(argv)
        evidence = _collect_evidence(SimpleNamespace(evidence=sf.evidence, evidence_json=sf.evidence_json))
        auto_accept = parse_probability("--auto-accept", sf.auto_accept, ctx.config["verify"]["autoAccept"])
        fail_on = parse_fail_on(sf.fail_on, core.VERIFY_FAIL_CONDITIONS, ["contradicted"])

        def run(row: dict) -> dict:
            out = core.run_verify(ctx.ask(), [row["text"]], evidence, auto_accept)
            return {"output": out, "failed": core.verify_failed(out, fail_on)}

        return run

    raise CliError(f'batch does not support sub-command "{name}" (try classify, screen, verify).')


def register_batch(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "batch",
        help="Run a command over many rows with a concurrency pool; emits JSONL",
        description="Run a per-row command over JSONL or newline-delimited input with a bounded worker pool.",
    )
    p.add_argument("-i", "--input", required=True, metavar="REF", help="batch input @file, - for stdin")
    p.add_argument("--concurrency", metavar="N", help="max parallel requests (default 4)")
    p.add_argument("--no-stream", action="store_true", help="buffer all records and emit at end")
    p.add_argument("command_args", nargs=argparse.REMAINDER,
                   help="the sub-command and its flags (e.g. classify --labels a,b) -- separator required")
    p.set_defaults(func=_cmd_batch)


# ── models ──────────────────────────────────────────────────────────────────


def _cmd_models(args: argparse.Namespace, ctx: CommandContext) -> int:
    if ctx.dry_run:
        return _emit_dry_run("models", ctx, {})
    models = list_models(ctx.env, ctx.config["timeoutMs"])
    def view() -> View:
        rows = [[m.get("id") or "-", m.get("description") or "-"] for m in models]
        return View(table={"columns": ["Model", "Description"], "rows": rows})
    emit(ctx.output, {"command": "models", "models": models}, view)
    return Exit.OK


def register_models(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("models", help="List the models available to your account", description="List the models available to your account.")
    p.set_defaults(func=_cmd_models)


# ── auth ────────────────────────────────────────────────────────────────────


def _cmd_auth(args: argparse.Namespace, ctx: CommandContext) -> int:
    action = args.action
    store = resolve_store(ctx.env)
    if action == "status":
        rows = []
        for c in resolve_credentials(dict(os.environ), store):
            provider = c["provider"]
            rows.append([provider, ENV_VAR[provider], c["source"], store.location if c["source"] == store.kind else "-"])
        emit(ctx.output, {"command": "auth", "action": "status", "credentials": rows},
             lambda: View(table={"columns": ["Provider", "Env Var", "Source", "Location"], "rows": rows}))
        return Exit.OK
    if action == "login":
        provider = args.provider or "typesafe"
        if provider not in CREDENTIAL_PROVIDERS:
            raise CliError(f'Unknown auth provider "{provider}". Allowed: {", ".join(CREDENTIAL_PROVIDERS)}.')
        secret = args.key or _prompt_secret(f"Paste {ENV_VAR[provider]}: ")
        if not secret:
            raise CliError("Empty key.")
        store.set(provider, secret)
        sys.stderr.write(f"Stored {provider} key in {store.location}\n")
        return Exit.OK
    if action == "logout":
        provider = args.provider or "typesafe"
        if provider not in CREDENTIAL_PROVIDERS:
            raise CliError(f'Unknown auth provider "{provider}".')
        removed = store.delete(provider)
        sys.stderr.write(f"{'Removed' if removed else 'No stored key for'} {provider} in {store.location}\n")
        return Exit.OK
    raise CliError(f'Unknown auth action "{action}".')


def _prompt_secret(prompt: str) -> str:
    import getpass

    return getpass.getpass(prompt).strip()


def register_auth(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "auth",
        help="Store, inspect, or remove API keys (keychain or 0600 file)",
        description="Manage stored API keys. Backed by the OS keychain when available, otherwise a 0600 file.",
    )
    p.add_argument("action", choices=("status", "login", "logout"), help="what to do")
    p.add_argument("provider", nargs="?", help="typesafe (default) or openrouter")
    p.add_argument("--key", metavar="SECRET", help="pass the key on the command line (skips the prompt)")
    p.set_defaults(func=_cmd_auth)


# ── config ──────────────────────────────────────────────────────────────────


def _cmd_config(args: argparse.Namespace, ctx: CommandContext) -> int:
    path = config_path(ctx.env)
    action = args.action
    if action == "path":
        sys.stdout.write(path + "\n")
        return Exit.OK
    if action == "show":
        current = read_config_file(path)
        emit(ctx.output, {"command": "config", "path": path, "config": current, "defaults": DEFAULTS},
             lambda: View(kv=[("path", path)],
                           table={"columns": ["Field", "Value"], "rows": [["path", path], ["config", json.dumps(current)]]}))
        return Exit.OK
    if action == "keys":
        keys = known_config_keys()
        sys.stdout.write("\n".join(keys) + "\n")
        return Exit.OK
    if action == "set":
        if not args.key or args.value is None:
            raise CliError("config set requires KEY VALUE.")
        current = read_config_file(path)
        updated = set_config_value(current, args.key, args.value)
        write_config_file(path, updated)
        sys.stderr.write(f"Set {args.key} = {args.value} in {path}\n")
        return Exit.OK
    if action == "unset":
        if not args.key:
            raise CliError("config unset requires KEY.")
        current = read_config_file(path)
        updated = unset_config_value(current, args.key)
        write_config_file(path, updated)
        sys.stderr.write(f"Unset {args.key} in {path}\n")
        return Exit.OK
    raise CliError(f'Unknown config action "{action}".')


def register_config(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "config",
        help="Show or edit the jev configuration file",
        description="Inspect and edit the jev configuration file. Defaults < file < env < flags.",
    )
    p.add_argument("action", choices=("show", "path", "keys", "set", "unset"))
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=_cmd_config)


# ── update ──────────────────────────────────────────────────────────────────


def _cmd_update(args: argparse.Namespace, ctx: CommandContext) -> int:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("https://pypi.org/pypi/jev-studio/json", timeout=8) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as err:
        raise CliError(f"Could not reach PyPI: {err}")
    latest = info.get("info", {}).get("version")
    from importlib.metadata import PackageNotFoundError, version as pkg_version
    try:
        current = pkg_version("jev-studio")
    except PackageNotFoundError:
        current = "0.0.0"
    up_to_date = latest == current
    sys.stdout.write(f"current: {current}\nlatest:  {latest}\n")
    if up_to_date:
        sys.stdout.write("up to date.\n")
    else:
        sys.stdout.write("run: pip install --upgrade jev-studio\n")
    return Exit.OK


def register_update(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("update", help="Check PyPI for a newer jev-studio release", description="Check PyPI for a newer jev-studio release.")
    p.set_defaults(func=_cmd_update)
