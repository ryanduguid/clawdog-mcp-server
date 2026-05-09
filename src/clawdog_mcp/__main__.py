"""Entrypoint for ``python -m clawdog_mcp`` and the ``clawdog-mcp`` console script.

Runs the FastMCP app on stdio (the Phase 3b transport).
"""
from __future__ import annotations

from clawdog_mcp.server import build_app


def main() -> None:
    app = build_app()
    # FastMCP.run() defaults to stdio when no transport is specified.
    app.run()


if __name__ == "__main__":
    main()
