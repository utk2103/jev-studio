<div align= "center">
<p align="center">
  <img width="180" height="180" src="public/logo.svg" alt="Jev Studio logo" style="margin-right:20px;">
</p>
<h1>Jev Studio</h1>
<br>

MCP server + CLI plugin for Jev Studio. Serves the Jev ruleset over stdio to any MCP host.

<div>
  <img src="https://badgen.net/badge/status/Under%20Development/red?icon=lgtm" alt="status">
  <img src="https://img.shields.io/badge/Version-0.1.0-brightgreen.svg" alt="version">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="license">
  <img src="https://img.shields.io/github/commit-activity/m/utk2103/jev-Studio" alt="commits">
  <img src="https://img.shields.io/github/repo-size/utk2103/jev-Studio" alt="repo size">
  <img src="https://img.shields.io/badge/code%20style-ruff-000000.svg" alt="code style">
</div>

</div>


## Install (PyPI)

```bash
pip install jev-studio
jev-studio            # speaks MCP over stdio
```

Point an MCP host at that command:

```json
{
  "mcpServers": {
    "jev": { "command": "jev-studio" }
  }
}
```

## What it exposes

- **Prompt `jev`** — returns the Jev ruleset as a user message. Optional `mode`: `lite`, `full`, `ultra`. Omit for `full`.
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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License — see [LICENSE](LICENSE).
