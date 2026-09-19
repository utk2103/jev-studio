"""Pure helpers: id sanitization, ranking, thresholds, question constructors."""
from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

MAX_CANDIDATES = 250
MAX_CANDIDATE_CHARS = 2000

_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_ID_TRIM = re.compile(r"^_+|_+$")


def sanitize_id(raw: str) -> str:
    cleaned = _ID_TRIM.sub("", _ID_RE.sub("_", raw))
    return cleaned[:64]


def ensure_unique_ids(items: list[dict], fallback_prefix: str) -> list[dict]:
    used: set[str] = set()
    out: list[dict] = []
    for i, item in enumerate(items):
        raw = str(item.get("id") or "")
        base = sanitize_id(raw) or f"{fallback_prefix}{i}"
        candidate = base
        n = 1
        while candidate in used:
            candidate = f"{base}_{n}"
            n += 1
        used.add(candidate)
        entry = dict(item)
        entry["id"] = candidate
        entry["_original_id"] = raw or candidate
        out.append(entry)
    return out


def original_ids(items: Sequence[dict]) -> dict[str, str]:
    return {i["id"]: i["_original_id"] for i in items}


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]} […truncated]"


RELATION_TO_VERDICT = {
    "supports": "verified",
    "contradicts": "contradicted",
    "says_nothing": "unsupported",
}


def verify_action(confidence: float | None, auto_accept: float) -> str:
    if confidence is None:
        return "review"
    return "auto" if confidence >= auto_accept else "review"


def screen_recommendation(
    injection: float,
    substance: float | None,
    relevance: float | None,
    block_at: float,
    review_at: float,
    skip_below: float = 0.3,
) -> dict:
    if injection >= block_at:
        return {"action": "block", "reason": f"injection probability {injection:.2f} >= block threshold {block_at}"}
    if injection >= review_at:
        return {"action": "review", "reason": f"injection probability {injection:.2f} >= review threshold {review_at}"}
    if substance is not None and substance < skip_below:
        return {"action": "skip", "reason": f"little substantive content (substance {substance:.2f})"}
    if relevance is not None and relevance < skip_below:
        return {"action": "skip", "reason": f"not relevant to the stated purpose (relevance {relevance:.2f})"}
    return {"action": "pass", "reason": "no signals above thresholds"}


def exists_verdict(exists: float, found: float = 0.7, absent: float = 0.35) -> str:
    if exists >= found:
        return "answered"
    if exists < absent:
        return "absent"
    return "partial"


def rank_candidates(candidates: list[dict], probabilities: dict[str, float]) -> list[dict]:
    indexed = [
        (i, {**c, "probability": float(probabilities.get(c["id"], 0.0))})
        for i, c in enumerate(candidates)
    ]
    indexed.sort(key=lambda pair: (-pair[1]["probability"], pair[0]))
    return [c for _, c in indexed]


def parse_fail_on(raw: str | None, allowed: Sequence[str], fallback: list[str]) -> list[str]:
    if raw is None:
        return list(fallback)
    trimmed = raw.strip()
    if trimmed == "" or trimmed == "none":
        return []
    values = [v.strip() for v in trimmed.split(",")]
    for v in values:
        if v not in allowed:
            raise ValueError(f'Invalid --fail-on value "{v}". Allowed: {", ".join(allowed)}, none.')
    return values


def parse_probability(name: str, raw: Any, fallback: float) -> float:
    if raw is None:
        return fallback
    try:
        n = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number between 0 and 1.")
    if not (0.0 <= n <= 1.0):
        raise ValueError(f"{name} must be a number between 0 and 1.")
    return n


def chunk(items: Sequence[Any], size: int) -> list[list[Any]]:
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


# ── question constructors (mirror @typesafe-ai/sdk helpers) ─────────────────


def noul(instructions: Any = None, criteria: dict[str, Any] | None = None) -> dict:
    out: dict[str, Any] = {"type": "noul"}
    if instructions is not None:
        out["instructions"] = instructions
    if criteria is not None:
        out["criteria"] = criteria
    return out


def choice(instructions: Any, criteria: dict[str, Any]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: Any, criteria: list[Any]) -> dict:
    if len(criteria) < 2:
        raise ValueError("score criteria must be a list of at least two descriptions.")
    return {"type": "score", "instructions": instructions, "criteria": criteria}


def strip_meta(items: Iterable[dict]) -> list[dict]:
    return [{k: v for k, v in item.items() if not k.startswith("_")} for item in items]
