"""Transport for TypeSafe (default), OpenRouter Decisions, or Cloudflare Workers AI."""
from __future__ import annotations

import json
import re
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable

from .errors import CliError

USER_AGENT = "jev-studio"
REFERER = "https://github.com/utk2103/jev-Studio"
OPENROUTER_LATEST = "jev-1.13"

AskFn = Callable[[Any, dict[str, Any]], "AskResult"]


class AskResult(dict):
    """{answers, usage: {input_tokens, output_tokens}, provider, model}."""


def resolve_provider(env: dict[str, str], explicit: str = "auto") -> str:
    has_typesafe = bool((env.get("TYPESAFE_API_KEY") or "").strip())
    or_key = env.get("OPENROUTER_API_KEY") or ""
    has_openrouter = bool(re.match(r"^sk-or-", or_key))
    cf_token = env.get("JEV_CLOUDFLARE_API_TOKEN") or env.get("CLOUDFLARE_API_TOKEN")
    has_cloudflare = bool(cf_token and env.get("CLOUDFLARE_ACCOUNT_ID"))

    if explicit == "typesafe":
        if not has_typesafe:
            raise CliError(
                "Provider is typesafe but TYPESAFE_API_KEY is not set. Run `jev auth login` to store a key."
            )
        return "typesafe"
    if explicit == "openrouter":
        if not has_openrouter:
            raise CliError(
                "Provider is openrouter but OPENROUTER_API_KEY is not set or is not an sk-or- key. "
                "Run `jev auth login openrouter` to store one."
            )
        return "openrouter"
    if explicit == "cloudflare":
        if not has_cloudflare:
            raise CliError(
                "Provider is cloudflare but CLOUDFLARE_API_TOKEN (or JEV_CLOUDFLARE_API_TOKEN) "
                "and CLOUDFLARE_ACCOUNT_ID are not both set."
            )
        return "cloudflare"
    if explicit == "auto":
        if has_typesafe:
            return "typesafe"
        if has_openrouter:
            return "openrouter"
        if has_cloudflare:
            return "cloudflare"
        raise CliError(
            "No credentials found. Run `jev auth login` to store a key, or set TYPESAFE_API_KEY "
            "(https://console.typesafe.ai/settings/keys), OPENROUTER_API_KEY (sk-or-...), "
            "or CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID."
        )
    raise CliError(f"Unknown provider {explicit}")


def provider_model(provider: str, model: str) -> str:
    if provider == "openrouter":
        effective = OPENROUTER_LATEST if model == "jev-latest" else model
        return effective if effective.startswith("typesafe/") else f"typesafe/{effective}"
    if provider == "cloudflare":
        if model.startswith("typesafe/"):
            return model
        return f"typesafe/{'jev' if model == 'jev-latest' else model}"
    return model


def validate_answers(questions: dict[str, Any], answers: Any, model: str) -> dict[str, Any]:
    if not isinstance(answers, dict):
        raise CliError(f"Malformed response from {model}: no answers object. Retry, or check TYPESAFE_BASE_URL.")
    missing = [qid for qid in questions if qid not in answers]
    if missing:
        shown = ", ".join(missing[:5]) + (f", … ({len(missing)})" if len(missing) > 5 else "")
        raise CliError(f"Malformed response from {model}: no answer for {shown}.")
    for qid, q in questions.items():
        asked = q.get("type") if isinstance(q, dict) else None
        a = answers[qid]
        problem: str | None = None
        if not isinstance(a, dict):
            problem = "is not an object"
        elif asked and a.get("type") != asked:
            problem = f"has type {a.get('type')} but the question was {asked}"
        elif a.get("type") == "noul" and not isinstance(a.get("noul"), (int, float)):
            problem = "has a non-numeric noul probability"
        elif a.get("type") == "choice" and not isinstance(a.get("choice"), str):
            problem = "has no choice"
        elif a.get("type") == "score" and not isinstance(a.get("score"), (int, float)):
            problem = "has a non-numeric score"
        if problem:
            raise CliError(f'Malformed response from {model}: answer "{qid}" {problem}.')
    return answers


def _http_post(url: str, headers: dict[str, str], body: dict, timeout_ms: int) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0, context=ctx) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            payload = json.loads(err.read().decode("utf-8", errors="replace"))
        except Exception:
            payload = {}
        return err.code, payload
    except (socket.timeout, TimeoutError):
        raise CliError(f"Request timed out after {timeout_ms} ms.")
    except urllib.error.URLError as err:
        raise CliError(f"Transport error: {err.reason}")


def _http_get(url: str, headers: dict[str, str], timeout_ms: int) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0, context=ctx) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            payload = json.loads(err.read().decode("utf-8", errors="replace"))
        except Exception:
            payload = {}
        return err.code, payload
    except (socket.timeout, TimeoutError):
        raise CliError(f"Request timed out after {timeout_ms} ms.")
    except urllib.error.URLError as err:
        raise CliError(f"Transport error: {err.reason}")


def _typesafe_base(env: dict[str, str]) -> str:
    return (env.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")


def create_ask(
    provider: str,
    model: str,
    timeout_ms: int,
    env: dict[str, str],
) -> AskFn:
    resolved = resolve_provider(env, provider)
    effective_model = provider_model(resolved, model)

    def _typesafe_ask(state: Any, questions: dict[str, Any]) -> AskResult:
        url = _typesafe_base(env) + "/v1/systemone"
        headers = {
            "Authorization": f"Bearer {env['TYPESAFE_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "X-TypeSafe-SDK": USER_AGENT,
        }
        status, body = _http_post(
            url, headers, {"state": state, "questions": questions, "model": effective_model}, timeout_ms
        )
        if status >= 400:
            raise CliError(f"TypeSafe API {status}: {json.dumps(body)[:300]}")
        answers = validate_answers(questions, body.get("answers"), body.get("model") or effective_model)
        usage = body.get("usage") or {}
        return AskResult(
            answers=answers,
            usage={
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
            },
            provider=resolved,
            model=body.get("model") or effective_model,
        )

    def _openrouter_ask(state: Any, questions: dict[str, Any]) -> AskResult:
        headers = {
            "Authorization": f"Bearer {env['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
            "HTTP-Referer": REFERER,
            "X-Title": USER_AGENT,
        }
        status, body = _http_post(
            "https://openrouter.ai/api/alpha/decisions",
            headers,
            {"model": effective_model, "state": state, "questions": questions},
            timeout_ms,
        )
        if status >= 400:
            raise CliError(f"OpenRouter decisions API {status}: {json.dumps(body)[:300]}")
        answers = validate_answers(questions, body.get("answers"), body.get("model") or effective_model)
        usage = body.get("usage") or {}
        return AskResult(
            answers=answers,
            usage={
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
            },
            provider=resolved,
            model=body.get("model") or effective_model,
        )

    def _cloudflare_ask(state: Any, questions: dict[str, Any]) -> AskResult:
        token = env.get("JEV_CLOUDFLARE_API_TOKEN") or env.get("CLOUDFLARE_API_TOKEN")
        acct = env["CLOUDFLARE_ACCOUNT_ID"]
        url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        status, body = _http_post(
            url, headers, {"model": effective_model, "input": {"state": state, "questions": questions}}, timeout_ms
        )
        if status >= 400 or body.get("success") is False:
            raise CliError(f"Cloudflare AI run {status}: {json.dumps(body.get('errors') or body)[:300]}")
        outer = body.get("result") or {}
        if isinstance(outer, dict) and isinstance(outer.get("state"), str) and outer["state"] != "Completed":
            raise CliError(f"Cloudflare AI run state {outer['state']}: {json.dumps(body.get('errors') or [])[:300]}")
        payload = outer.get("result") if isinstance(outer, dict) and outer.get("result") else outer or body
        answers = validate_answers(questions, payload.get("answers"), payload.get("model") or effective_model)
        usage = payload.get("usage") or {}
        return AskResult(
            answers=answers,
            usage={
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
            },
            provider=resolved,
            model=payload.get("model") or effective_model,
        )

    if resolved == "typesafe":
        return _typesafe_ask
    if resolved == "openrouter":
        return _openrouter_ask
    return _cloudflare_ask


def list_models(env: dict[str, str], timeout_ms: int) -> list[dict]:
    if not env.get("TYPESAFE_API_KEY"):
        raise CliError(
            "Listing models requires TYPESAFE_API_KEY. Run `jev auth login` or set the variable."
        )
    url = _typesafe_base(env) + "/v1/models"
    headers = {
        "Authorization": f"Bearer {env['TYPESAFE_API_KEY']}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    status, body = _http_get(url, headers, timeout_ms)
    if status >= 400:
        raise CliError(f"TypeSafe API {status}: {json.dumps(body)[:300]}")
    models = body.get("models")
    if not isinstance(models, list):
        raise CliError("Unexpected response shape from GET /v1/models; expected { models: [...] }.")
    return models
