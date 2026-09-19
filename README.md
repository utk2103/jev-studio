<div align= "center">
<p align="center">
  <img width="180" height="180" src="public/logo.png" alt="Jev Studio logo" style="margin-right:20px;">
</p>
<h1>Jev Studio</h1>
<br>

One-stop kit for playing with TypeSafe's Jev: MCP tools for Choice/Noul/Score, ready-made prompt libraries, and slash commands for every cookbook.

<div>
  <img src="https://badgen.net/badge/status/Under%20Development/red?icon=lgtm" alt="status">
  <img src="https://img.shields.io/badge/Version-0.1.0-brightgreen.svg" alt="version">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="license">
  <img src="https://img.shields.io/github/commit-activity/m/utk2103/jev-Studio" alt="commits">
  <img src="https://img.shields.io/github/repo-size/utk2103/jev-Studio" alt="repo size">
  <img src="https://img.shields.io/badge/code%20style-ruff-000000.svg" alt="code style">
</div>

</div>


## Install

```bash
pip install jev-studio
```

Two commands are installed:

- `jev` — the CLI for TypeSafe's Jev decisions (verify, screen, classify, extract, match, route, ask, find, rerank, compact, batch).
- `jev-studio` — the MCP server that serves the Jev ruleset over stdio.

## The CLI: `jev`

Jev turns natural-language state and a set of typed questions into typed answers (yes/no, choice, or score) with probabilities. The CLI wraps it in one-command judgments over text you pipe in.

### Authenticate

Any one of these is enough (first found wins):

```bash
jev auth login               # store TYPESAFE_API_KEY in the OS keychain (or 0600 file)
export TYPESAFE_API_KEY=...  # from https://console.typesafe.ai/settings/keys
export OPENROUTER_API_KEY=sk-or-...
export CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=...
```

Inspect what's live: `jev auth status`.

### Commands

Every command speaks JSON (`--json`), Markdown (`--md`), JSONL, CSV, TSV, or a colored text table. Use `--pluck` to lift one field. Use `--fail-on <list>` to make the process exit 2 when a judgment condition trips (great for CI gates).

**Judgments**

- `jev verify` — check claims against evidence. Verdict + probabilities per claim, with a `supporting_evidence` back-reference when there is more than one evidence item.
- `jev screen` — flag prompt injection, empty/boilerplate content, and irrelevance before an agent reads text. Recommends `pass` / `review` / `block` / `skip`.
- `jev classify` — one label (single), several (`--multi`), or a hierarchy (`--taxonomy`). Confidence-gated `auto` vs `review`.
- `jev extract` — pull typed values out of text. Regex proposes candidates, Jev picks, code normalizes. Builtins: `email`, `phone`, `url`, `amount`, `date`, `percent`, `number`. Custom regexes via `name=/regex/:description`.
- `jev match` — decide if record pairs are the `same`, `different`, or `unclear`. Feed pairs, one list, or two lists (cross product).
- `jev route` — pick a handler for a request and fill its closed-set arguments in one call.
- `jev ask` — raw System One passthrough for any state and any questions (repeated `--noul`, `--choice`, `--score`, or `--questions-json`).

**Ranking**

- `jev find` — rank up to 250 candidates against a plain-language query. Returns top-K and a document-level `answered` / `partial` / `absent` verdict.
- `jev rerank` — score each candidate independently and sort. Several can be relevant, or none.

**Pipelines**

- `jev compact` — shrink an agent transcript by dropping stale tool calls verbatim; recent turns are always kept.
- `jev batch` — run a per-row command (`classify`, `screen`, `verify`) over JSONL or newline-delimited input with a bounded worker pool. Emits JSONL, one line per row.

**Account**

- `jev models` — list the models available to your account.
- `jev auth` — `login`, `logout`, `status`. Keychain-first, file fallback.
- `jev config` — `show`, `path`, `keys`, `set`, `unset`. Defaults `< file < env < flags`.
- `jev update` — check PyPI for a newer release.

### Examples

```bash
# Verify a claim against a file
jev verify "Helmets are optional for adults" --evidence @ordinance.txt

# Screen scraped HTML for prompt injection before letting an agent see it
curl -s https://example.com | jev screen --purpose "extract pricing" --fail-on block,review

# Classify a ticket in three labels, JSON output
jev classify "The invoice total is wrong" --labels billing,bug,feature --json

# Extract an email and a date from an invoice
jev extract @invoice.txt --want email --want date --context "an invoice"

# Rank documentation files for a question
jev find "how do I rotate API keys" --files 'docs/*.md' -k 3

# Batch-classify tickets with concurrency 8
jev batch -i @tickets.txt --concurrency 8 -- classify --labels billing,technical,sales

# Route a support request to a handler
echo "cancel my subscription" | jev route --handlers "cancel:cancel plan,upgrade,help"

# Inspect and edit configuration
jev config set verify.autoAccept 0.9
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Command completed and no `--fail-on` condition matched. |
| 1 | Usage, configuration, input, or transport error. |
| 2 | Judgment condition matched (e.g. a contradicted claim, injection blocked). |

### Input references

Anywhere the CLI takes a value it accepts `text`, `@path/to/file`, or `-` (stdin). Escape a literal leading `@` as `@@`.

### Global flags

```
-m, --model NAME       Jev model, e.g. jev-latest or jev-1.13.0
-P, --provider NAME    auto | typesafe | openrouter | cloudflare
--timeout MS           per-request timeout
--dry-run              print the request that would be sent; don't call the API
--json, --md, --format text|json|jsonl|csv|tsv|md
--pluck PATH           print one field (e.g. label, results[].verdict)
-q, --quiet            omit the usage/model footer in text output
--no-color             disable ANSI colors
```

### Configuration

Config file: `$XDG_CONFIG_HOME/jev/config.json` (or `~/.config/jev/config.json`). Env overrides file, flags override env. See `jev config keys` for every settable path.

Environment overrides:
```
JEV_PROVIDER   JEV_MODEL   JEV_TIMEOUT_MS   JEV_FORMAT
JEV_CONFIG     JEV_CREDENTIALS   JEV_CREDENTIAL_STORE   JEV_NO_STORED_CREDENTIALS
JEV_DEBUG=1    # include stack traces on error
```

## The MCP server: `jev-studio`

```bash
jev-studio            # speaks MCP over stdio
```

Point an MCP host at it:

```json
{
  "mcpServers": {
    "jev": { "command": "jev-studio" }
  }
}
```

Exposes:

- **Prompt `jev`** — the Jev ruleset as a user message. Optional `mode`: `lite`, `full`, `ultra`. Omit for `full`.
- **Tool `jev_instructions`** — same text plus structured output (`{mode, instructions}`) for hosts that pull context via tools. Read-only.

## Develop

```bash
pip install -e ".[dev]"
pytest
```

Ship to PyPI:

```bash
python -m build
twine upload dist/*
```

### Claude Code

```
/plugin marketplace add utk2103/jev-Studio
/plugin install prompt-studio@jev-studio
```

Two separate prompts. Start a new session; the ruleset lands in system context on `SessionStart`.

Local clone:
```
/plugin marketplace add /path/to/jev-Studio
/plugin install prompt-studio@jev-studio
```

### Codex

```bash
codex plugin marketplace add utk2103/jev-Studio
codex plugin add prompt-studio@jev-studio
```

## Try something fun

A curated collection of **726 Jev use cases** plus **50 runnable evals** — every build linked to its project and source post. Search it, copy a brief, hand it to your agent.

Browse: [jev-directory.netlify.app](https://jev-directory.netlify.app/#)

## Credits

The CLI is a Python port of the TypeScript [`jev-cli`](https://github.com/Nasrallah-AL/jev-cli), rebuilt on the standard library with the same command surface and question shapes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License — see [LICENSE](LICENSE).
