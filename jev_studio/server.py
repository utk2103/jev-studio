"""Jev Studio MCP server: serves the Jev ruleset over stdio.

Exposes a prompt (user-invoked) and a tool (for hosts that pull context via
tools).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from jev_studio.instructions import build_instructions, resolve_mode

mcp = FastMCP("jev")


@mcp.prompt(name="jev", description="Jev Studio instructions ruleset.")
def jev_prompt(mode: str | None = None) -> str:
    """Return the Jev ruleset for the given intensity (lite, full, or ultra)."""
    return build_instructions(mode)


@mcp.tool(name="jev_instructions", description="Return the Jev ruleset for the given intensity (lite, full, or ultra).")
def jev_instructions(mode: str | None = None) -> dict:
    resolved = resolve_mode(mode)
    return {"mode": resolved, "instructions": build_instructions(resolved)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
