"""Standing Rule #12 — Production Resolver Shape Assertions.

Mirrors the n=1 reference at
``lodgeit-labs/clawdog-calculator-api/tests/test_production_bundle.py``.

Five assertion classes:

  1. **Bundle existence.** The packaged routing-table YAML is present at the
     path the production resolver expects (the package layout the wheel +
     pip-install -e ship).
  2. **File presence + structural markers.** The routing-table file is
     readable and carries valid YAML with the required top-level + per-entry
     fields.
  3. **Production resolver returns existing path.** ``resolve_routing_table_path()``
     under the production env shape (no test overrides) returns a path that
     exists.
  4. **End-to-end production-path 2xx.** A ``calculator_discover`` call
     traversing the production resolver path returns a structurally-valid
     response (matches surfaced).
  5. **Missing-bundle structured error.** When the routing-table is artificially
     absent (env-override pointing at a non-existent path), tools surface a
     structured ``routing_bundle_unavailable`` error — NOT an uncaught
     exception that becomes a stdio-stream EOF.

Per Lesson #40: a hermetic green without a production-bundle green is
pre-broken. CI gates this on every PR.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from clawdog_mcp.routing import (
    DEFAULT_ROUTING_TABLE_PATH,
    REQUIRED_ENTRY_KEYS,
    load_routing_table,
    resolve_routing_table_path,
)
from clawdog_mcp.tools.discover import discover
from clawdog_mcp.tools.invoke import invoke


def test_production_routing_bundle_exists() -> None:
    """The packaged routing-table YAML must be present at the path
    ``resolve_routing_table_path()`` returns under the production env."""
    assert DEFAULT_ROUTING_TABLE_PATH.is_file(), (
        f"production routing-table bundle missing at {DEFAULT_ROUTING_TABLE_PATH}; "
        f"the package layout expects clawdog_mcp/config/routing_table.yaml"
    )


def test_production_routing_bundle_structural_markers() -> None:
    """The routing-table YAML must parse and carry the structural markers
    every Phase 3b consumer relies on: top-level ``routing_table:``, plus
    each entry's required keys + https rest_base."""
    table = load_routing_table(DEFAULT_ROUTING_TABLE_PATH)
    assert isinstance(table, list) and len(table) >= 1, (
        f"routing-table must be a non-empty list, got {table!r}"
    )
    for entry in table:
        for key in REQUIRED_ENTRY_KEYS:
            assert key in entry and entry[key], (
                f"routing-table entry {entry.get('calc', '<unknown>')!r} missing {key!r}"
            )
        assert entry["rest_base"].startswith("https://")


def test_production_resolver_returns_existing_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under the production env shape (no override), the resolver returns a
    real path."""
    monkeypatch.delenv("CLAWDOG_MCP_ROUTING_TABLE", raising=False)
    p = resolve_routing_table_path()
    assert p.is_file(), f"resolver produced non-existent path {p}"


def test_discover_e2e_against_production_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: ``calculator_discover`` traversing the production resolver
    path returns a structurally-valid match for the FBT-shaped intent."""
    monkeypatch.delenv("CLAWDOG_MCP_ROUTING_TABLE", raising=False)
    out = discover("Fringe Benefits Tax")
    assert "error" not in out, f"discover failed against production bundle: {out}"
    assert any(m["calc"] == "urn:lodgeit:calculator:fbt" for m in out["matches"])


@pytest.mark.asyncio
async def test_invoke_e2e_against_production_bundle(
    monkeypatch: pytest.MonkeyPatch, canonical_invoke_response
) -> None:
    """End-to-end calculator_invoke against the production resolver +
    a mocked REST upstream. Structurally-valid passthrough confirms the
    production resolver path is exercisable."""
    monkeypatch.delenv("CLAWDOG_MCP_ROUTING_TABLE", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/v1/calculators/" in request.url.path:
            return httpx.Response(200, json=canonical_invoke_response)
        return httpx.Response(404, json={"error": "unmocked route"})

    from clawdog_mcp.rest_client import CalculatorRestClient

    def factory(rest_base: str) -> CalculatorRestClient:
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        return CalculatorRestClient(rest_base, client=client)

    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=factory,
    )
    assert "error" not in response, f"invoke failed against production bundle: {response}"
    assert response["taxable_value"] == canonical_invoke_response["taxable_value"]


def test_missing_bundle_surfaces_structured_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Defence-in-depth: when the bundle is artificially missing, tools surface
    a structured ``routing_bundle_unavailable`` error — NOT an uncaught
    exception that becomes a stdio-stream EOF (Standing Rule #12 assertion #5)."""
    missing = tmp_path / "nonexistent_routing_table.yaml"
    monkeypatch.setenv("CLAWDOG_MCP_ROUTING_TABLE", str(missing))

    out = discover("any intent")
    err = out.get("error", {})
    assert err.get("code") == "routing_bundle_unavailable", out
    assert "routing-table bundle missing" in err["detail"]
