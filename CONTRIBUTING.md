# Contributing to Jev Studio

Thanks for considering a contribution. Jev Studio ships an MCP server, a
Claude Code / Codex plugin, and a PyPI package that serves the Jev ruleset
to any MCP host.

Small focused PR > big rewrite. One concern per PR.

## Quick Links

- **GitHub:** https://github.com/utk2103/jev-Studio
- **Issues:** https://github.com/utk2103/jev-Studio/issues

## Maintainers

- **Utkarsh Upadhyay** — [@utk2103](https://github.com/utk2103)

---

## How to contribute

1. **Bugs & small fixes** → open a PR.
2. **New features / architecture** → open an issue first. Large features get discussed before implementation.
3. **Refactor-only PRs** → not accepted unless a maintainer requests it as part of a concrete fix.
4. **Questions** → open a GitHub Issue with the `question` label.

## PR limits

Cap at **10 open PRs per author**. Exceed it → auto-close.

---

## Repo layout

- `jev_studio/` — Python package (MCP server + instruction builder).
  - `server.py` — FastMCP entry point (`jev-studio` console script).
  - `instructions.py` — mode resolver + ruleset builder. **Source of truth.**
- `tests/` — pytest suite.
- `.claude-plugin/` — Claude Code plugin + marketplace manifests.
- `.codex-plugin/` — Codex plugin manifest.
- `hooks/` — SessionStart / UserPromptSubmit / SubagentStart hooks. Reuse `jev_studio.instructions`; do **not** duplicate the ruleset.
- `commands/` — TOML slash commands surfaced by the Claude Code plugin.

The MCP server, hooks, and any future adapters all call
`jev_studio.instructions.build_instructions()` — one source, zero drift.

---

## Dev setup

```bash
git clone https://github.com/utk2103/jev-Studio.git
cd jev-Studio
pip install -e ".[dev]"
pytest
```

Run the MCP server locally:

```bash
jev-studio            # speaks MCP over stdio
```

## Coding standards

- Ruff clean (`ruff check .` and `ruff format .`).
- Type hints on public functions.
- No unnecessary abstractions. Three similar lines beat a premature helper.
- Validate at boundaries only; trust internal code.
- Match existing style; don't refactor adjacent unchanged code.

## Tests

- pytest under `tests/`.
- New behavior needs at least one test.
- No mocking of the MCP SDK — test the pure logic in `instructions.py`.

## Commits & PRs

- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`).
- Subject ≤ 72 chars.
- Body explains the **why**, not the what.
- PR description: summary + test plan (checkbox list).

## Release checklist

1. Bump version in **all four** places:
   - `pyproject.toml`
   - `jev_studio/__init__.py`
   - `.claude-plugin/plugin.json`
   - `.codex-plugin/plugin.json`
2. Move `[Unreleased]` entries in `CHANGELOG.md` under the new version + date.
3. Tag: `git tag vX.Y.Z && git push --tags`.
4. Build + upload:
   ```bash
   python -m build
   twine check dist/*
   twine upload dist/*
   ```

## License

Contributions are licensed under the MIT License — see [LICENSE](LICENSE).
