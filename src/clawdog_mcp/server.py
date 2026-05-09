"""FastMCP application factory.

Builds a FastMCP server exposing the three meta-tools defined in CLAWDOG/109
§3 + META/005 §3.1. The factory pattern makes it possible to introspect the
tools manifest in tests + the drift gate without launching the stdio loop.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from clawdog_mcp.tools import discover as discover_module
from clawdog_mcp.tools import explain as explain_module
from clawdog_mcp.tools import invoke as invoke_module

SERVER_NAME = "clawdog-mcp-server"


def build_app() -> FastMCP:
    """Construct + return a fresh FastMCP app with the three meta-tools wired."""
    app = FastMCP(SERVER_NAME)

    @app.tool(name="calculator_discover")
    def calculator_discover(intent: str) -> dict:
        """Discover calculators matching a natural-language intent.

        Phase 3b: substring intent → routing entries (Fano semantic discovery
        is deferred to Phase 3d).

        :param intent: natural-language phrase (e.g. "FBT car operating cost").
        :returns: ``{"matches": [{"calc", "version", "summary"}...]}``
        """
        return discover_module.discover(intent)

    @app.tool(name="calculator_invoke")
    async def calculator_invoke(
        calc: str,
        version: str,
        params: dict[str, Any],
        period: str,
        jurisdiction: str,
    ) -> dict:
        """Invoke a calculator and return the byte-identical REST response.

        Forwards to the Phase 3a calculator-api REST upstream; enforces
        atom-vs-bridge (CLAWDOG/110 §3.3), advisory-boundary (CLAWDOG/110
        §3.2), and manifest passthrough (CLAWDOG/110 §3.1).

        :param calc: calculator URI (e.g. "urn:lodgeit:calculator:fbt").
        :param version: dotted-decimal version (e.g. "1.0").
        :param params: calculator-specific input params (forwarded as-is).
        :param period: bare period scalar ("FY26") or period URI.
        :param jurisdiction: ISO 3166 alpha-2 ("AU").
        """
        return await invoke_module.invoke(
            calc=calc,
            version=version,
            params=params,
            period=period,
            jurisdiction=jurisdiction,
        )

    @app.tool(name="calculator_explain")
    def calculator_explain(invocation_id: str) -> dict:
        """Resolve an invocation_id to its cached trace + manifest + advisory.

        Phase 3b: in-memory LRU populated by calculator_invoke; cache misses
        return a structured pointer to the regression-suite root. Prolog-trace
        integration is deferred to Phase 3d.

        :param invocation_id: the id returned by a prior calculator_invoke call.
        """
        return explain_module.explain(invocation_id)

    return app
