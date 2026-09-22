#!/usr/bin/env python3
"""Release helper: bump version everywhere + promote CHANGELOG Unreleased.

Usage:
    scripts/release.py <new-version> [--tag] [--no-commit]

Steps:
    1. Validate semver (X.Y.Z).
    2. Bump version in pyproject.toml, jev_studio/__init__.py,
       .claude-plugin/plugin.json, .codex-plugin/plugin.json.
    3. Promote CHANGELOG.md `## [Unreleased]` block into
       `## [<version>] - <today>` and leave a fresh empty Unreleased.
    4. Optionally commit + tag. Never pushes.

Note:
    README.md uses dynamic PyPI badges (shields.io + pepy.tech), so version
    and download counts update automatically once the new release is
    published to PyPI. No manual README bump needed.

    Also: create the tag ONLY after the version-bump PR is merged to main,
    otherwise CI builds the previous version and PyPI rejects the upload
    as a duplicate. See issue #13.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "jev_studio" / "__init__.py"
CLAUDE_PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CODEX_PLUGIN = ROOT / ".codex-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


def read_current_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not m:
        sys.exit("Could not find version in pyproject.toml")
    return m.group(1)


def bump_pyproject(new: str) -> None:
    text = PYPROJECT.read_text()
    text, n = re.subn(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{new}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        sys.exit("pyproject.toml: no version line replaced")
    PYPROJECT.write_text(text)


def bump_init(new: str) -> None:
    text = INIT.read_text()
    text, n = re.subn(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{new}"',
        text,
        count=1,
    )
    if n != 1:
        sys.exit(f"{INIT}: no __version__ line replaced")
    INIT.write_text(text)


def bump_plugin_json(path: Path, new: str) -> None:
    data = json.loads(path.read_text())
    if "version" not in data:
        sys.exit(f"{path}: no 'version' key")
    data["version"] = new
    path.write_text(json.dumps(data, indent=2) + "\n")


def promote_changelog(new: str) -> None:
    text = CHANGELOG.read_text()
    today = dt.date.today().isoformat()

    header = "## [Unreleased]"
    idx = text.find(header)
    if idx == -1:
        sys.exit("CHANGELOG.md: no '## [Unreleased]' section")

    # Find start of next release section (or EOF) to isolate Unreleased body.
    next_release = re.search(r"^## \[\d", text[idx + len(header):], flags=re.MULTILINE)
    end = (idx + len(header) + next_release.start()) if next_release else len(text)

    unreleased_body = text[idx + len(header):end].strip("\n")
    if not unreleased_body.strip():
        sys.exit("CHANGELOG.md: [Unreleased] is empty; add entries before releasing")

    fresh_unreleased = "## [Unreleased]\n\n### Added\n\n### Changed\n\n### Fixed\n\n"
    promoted = f"## [{new}] - {today}\n\n{unreleased_body}\n\n"

    new_text = text[:idx] + fresh_unreleased + promoted + text[end:]
    CHANGELOG.write_text(new_text)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("version", help="New version, e.g. 0.2.0")
    ap.add_argument("--tag", action="store_true", help="Create git tag v<version> after commit")
    ap.add_argument("--no-commit", action="store_true", help="Bump files only, skip git commit")
    args = ap.parse_args()

    new = args.version
    if not SEMVER.match(new):
        sys.exit(f"Not a valid semver: {new}")

    current = read_current_version()
    if current == new:
        sys.exit(f"Version already {new}")
    print(f"Bumping {current} -> {new}")

    bump_pyproject(new)
    bump_init(new)
    bump_plugin_json(CLAUDE_PLUGIN, new)
    bump_plugin_json(CODEX_PLUGIN, new)
    promote_changelog(new)

    print("Bumped:")
    for p in (PYPROJECT, INIT, CLAUDE_PLUGIN, CODEX_PLUGIN, CHANGELOG):
        print(f"  {p.relative_to(ROOT)}")

    if args.no_commit:
        print("Skipped git commit (--no-commit).")
        return

    run(["git", "add", str(PYPROJECT.relative_to(ROOT)),
         str(INIT.relative_to(ROOT)),
         str(CLAUDE_PLUGIN.relative_to(ROOT)),
         str(CODEX_PLUGIN.relative_to(ROOT)),
         str(CHANGELOG.relative_to(ROOT))])
    run(["git", "commit", "-m", f"chore(release): v{new}"])

    if args.tag:
        run(["git", "tag", f"v{new}"])
        print(f"\nTag v{new} created locally. Push it:")
        print(f"  git push origin main && git push origin v{new}")
    else:
        print(f"\nNext: push branch, open PR, merge, then tag:")
        print(f"  git tag v{new} && git push origin v{new}")


if __name__ == "__main__":
    main()
