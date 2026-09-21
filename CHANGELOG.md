# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions in `pyproject.toml`, `jev_studio/__init__.py`, `.claude-plugin/plugin.json`,
and `.codex-plugin/plugin.json` are kept in lockstep — every release bumps all of them together.

## [Unreleased]

### Added

### Changed

## [0.2.0] - 2026-09-21

### Added
- `jev` CLI ported from `jev-cli`: `verify`, `screen`, `extract`, `ask`
  subcommands with a shared `--dry-run` mode.
- Dry-run envelope emits `cwd`, `command`, `provider`, `model`, `request`,
  and a `provenance` block with per-key config source, config-file
  `path`/`exists`/`mtime`, and `resolved_bundle_sha256`.
- `_emit_dry_run()` in `jev_studio/cli/commands.py` consolidates the four
  previously duplicated dry-run branches (verify/screen/extract/ask).
- `resolve_config_with_provenance()` in `jev_studio/cli/config.py` builds
  the provenance block used by the envelope.
- `.github/ISSUE_TEMPLATE/bug_report.yml` and `feature_request.yml`
  rewritten for jev-studio's MCP/CLI/hooks surface.
- `.github/pull_request_template.md` (markdown, correct path — the prior
  `ISSUE_TEMPLATE/pull_request.yml` was ignored by GitHub).
- `SECURITY.md` — vulnerability reporting policy.

### Changed
- CI workflow (`.github/workflows/ci.yml`): removed non-existent
  `frontend` job and `requirements.txt` install; single Python test job
  using `pip install -e .[dev]`; `build`/`publish` jobs gated on
  `v*` tags with PyPI trusted publisher.
- Bumped `pydantic-core` from 2.46.5 to 2.49.0.
- Raised plugin-scanner score to clear `min_score` 80.
- `.gitignore`: added `.DS_Store`.

## [0.1.0] - 2026-09-20

### Changed
- Repositioned repo as a "one-stop kit for playing with TypeSafe's Jev".
  Updated description across `README.md`, `pyproject.toml`,
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and
  `.codex-plugin/plugin.json`.
- Codex plugin manifest: `license` corrected to MIT (matches `LICENSE`);
  `shortDescription`, `longDescription`, `keywords`, `capabilities`, and
  `defaultPrompt` rewritten around Choice/Noul/Score judgments.

### Added
- Initial PyPI package skeleton adapted from `prompt-studio/lean-mcp`.
- `jev_studio/server.py` — FastMCP server exposing prompt `jev` and tool `jev_instructions`.
- `jev_studio/instructions.py` — self-contained mode resolver (`lite`, `full`, `ultra`) + builder.
- `pyproject.toml` (hatchling, MIT, `jev-studio` CLI entry point).
- `tests/test_instructions.py`.
- `.claude-plugin/` and `.codex-plugin/` marketplace + plugin manifests.
- `commands/jev.toml`, `commands/jev-help.toml` — Claude Code slash commands.
- `hooks/` — SessionStart + UserPromptSubmit + SubagentStart hooks that inject the Jev ruleset.
