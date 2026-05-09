"""Phase 3b end-to-end binary-failure gate.

Exercises the full meta-tool round-trip with a mocked REST upstream:
  * calculator_discover  → routing-table substring match returns FBT entry.
  * calculator_invoke    → atom→bridge translation, REST forward, byte-identical
                            passthrough, advisory enforcement.
  * calculator_explain   → invocation_id resolves the cached payload.
  * Tools-manifest drift → committed reference matches live introspection
                            (defence-in-depth — the same gate is run pre-pytest
                            via ``make tools-manifest-check``).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from clawdog_mcp.manifest import dump_tools_manifest
from clawdog_mcp.server import build_app
from clawdog_mcp.tools.discover import discover
from clawdog_mcp.tools.explain import explain
from clawdog_mcp.tools.invoke import invoke

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_discover_finds_fbt_by_substring():
    result = discover("FBT car operating cost")
    assert "error" not in result
    matches = result["matches"]
    assert len(matches) == 1
    assert matches[0]["calc"] == "urn:lodgeit:calculator:fbt"
    assert matches[0]["version"] == "1.0"


def test_discover_returns_empty_for_unmatched_intent():
    result = discover("compute UK corporation tax")
    assert result == {"matches": []}


@pytest.mark.asyncio
async def test_invoke_then_explain_round_trip(canonical_invoke_response, mock_rest_factory_canonical):
    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75, "employeeContribution": 200},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=mock_rest_factory_canonical,
    )
    assert "error" not in response
    invocation_id = response["invocation_id"]
    assert invocation_id.startswith("inv_")
    assert response["taxable_value"] == canonical_invoke_response["taxable_value"]

    # explain resolves it.
    explained = explain(invocation_id)
    assert "error" not in explained
    assert explained["invocation_id"] == invocation_id
    assert explained["calc"] == "urn:lodgeit:calculator:fbt"
    assert explained["jurisdiction"] == "AU"
    assert explained["regression_suite_root"] == "lodgeit-labs/LodgeiT_FBT/regression_suite/"


def test_explain_unknown_invocation_returns_pointer():
    out = explain("inv_does_not_exist")
    assert out.get("error", {}).get("code") == "invocation_not_found"
    assert "regression-suite" in out["error"]["detail"]


def test_committed_tools_manifest_matches_live_introspection():
    """NN#4 — defence-in-depth pytest mirror of ``make tools-manifest-check``."""
    committed_path = REPO_ROOT / "tools_manifest.json"
    committed = committed_path.read_text(encoding="utf-8")
    generated = json.dumps(asyncio.run(dump_tools_manifest(build_app())), indent=2, sort_keys=True) + "\n"
    assert committed == generated, (
        "tools_manifest.json drift detected vs. live introspection. "
        "Run `make tools-manifest` and commit the regenerated artefact."
    )
