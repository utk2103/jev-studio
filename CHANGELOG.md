# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions in `pyproject.toml`, `jev_studio/__init__.py`, `.claude-plugin/plugin.json`,
and `.codex-plugin/plugin.json` are kept in lockstep — every release bumps all of them together.

## [Unreleased]

### Changed
- Repositioned repo as a "one-stop kit for playing with TypeSafe's Jev". Updated
  description across `README.md`, `pyproject.toml`, `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, and `.codex-plugin/plugin.json`.
- Codex plugin manifest: `license` corrected to MIT (matches `LICENSE`);
  `shortDescription`, `longDescription`, `keywords`, `capabilities`, and
  `defaultPrompt` rewritten around Choice/Noul/Score judgments.

### Added

## [0.1.0] - 2026-09-20

### Added
- Initial PyPI package skeleton adapted from `prompt-studio/lean-mcp`.
- `jev_studio/server.py` — FastMCP server exposing prompt `jev` and tool `jev_instructions`.
- `jev_studio/instructions.py` — self-contained mode resolver (`lite`, `full`, `ultra`) + builder.
- `pyproject.toml` (hatchling, MIT, `jev-studio` CLI entry point).
- `tests/test_instructions.py`.
- `.claude-plugin/` and `.codex-plugin/` marketplace + plugin manifests.
- `commands/jev.toml`, `commands/jev-help.toml` — Claude Code slash commands.
- `hooks/` — SessionStart + UserPromptSubmit + SubagentStart hooks that inject the Jev ruleset.
