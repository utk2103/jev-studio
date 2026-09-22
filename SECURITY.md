# Security Policy

## Supported Versions

Only the latest published release of `jev-studio` on PyPI receives security patches.

## Reporting a Vulnerability

Do **not** open a public GitHub issue for security bugs.

Report privately via [GitHub Security Advisories](https://github.com/utk2103/jev-studio/security/advisories/new) or email the maintainer at btoshine774@gmail.com.

Expect an acknowledgement within 72 hours.

## Scope

In scope:
- `jev_studio/` — MCP server (`server.py`), CLI (`cli/`), instruction builder.
- `commands/`, `hooks/` — slash commands and lifecycle hooks shipped with the plugin.
- `.claude-plugin/`, `.codex-plugin/` — plugin manifests distributed to users.
- `pyproject.toml` and release automation in `scripts/`.

Out of scope:
- Upstream LLM provider vulnerabilities — report to the provider (e.g. TypeSafe, Anthropic, OpenAI).
- MCP client vulnerabilities (Claude Code, Codex, etc.) — report to the client vendor.
- Issues that require a pre-compromised host or a hostile MCP client.

## Secrets

- API keys and provider credentials are read from environment variables at runtime.
- Never commit `.env` files, tokens, or API keys — `.env` is in `.gitignore`.
- The PyPI publish workflow (`.github/workflows/ci.yml`) uses a trusted publisher (`id-token: write`); no long-lived PyPI token is stored in the repo.
