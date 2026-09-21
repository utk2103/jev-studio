# Security Policy

## Supported Versions

Only the latest stable release of Prompt Studio is supported with security patches.

## Reporting a Vulnerability

Do **not** open a public issue for security bugs.

Report privately via [GitHub Security Advisories](https://github.com/utk2103/jev-studio/security/advisories/new) or email the maintainer at btoshine774@gmail.com.

Expect an acknowledgement within 72 hours.

## Scope

In scope:
- FastAPI backend (`app/`)
- Alembic migrations (`alembic/`)
- Skills, hooks, commands (`skills/`, `hooks/`, `commands/`)

Out of scope:
- Upstream LLM provider vulnerabilities (report to the provider)
- Issues requiring a pre-compromised host

## Secrets

API keys are read from environment variables. Never commit `.env` files.
