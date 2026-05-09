"""NN#1 — Manifest-Fidelity Contract (CLAWDOG/110 §3.1).

Binary-failure gate: for any ``calculator.invoke`` call, the ``manifest``
block in the MCP response MUST be byte-identical (under canonical JSON
serialisation) to the ``manifest`` block in the upstream REST response.
"""
from __future__ import annotations

import pytest

from clawdog_mcp.manifest import assert_manifest_byte_identity, canonical_dumps
from clawdog_mcp.tools.invoke import invoke


@pytest.mark.asyncio
async def test_manifest_passthrough_byte_identity(canonical_invoke_response, mock_rest_factory_canonical):
    """Mock REST returns a known manifest; MCP forwards it byte-identically."""
    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=mock_rest_factory_canonical,
    )

    assert "manifest" in response, f"MCP response missing manifest block: {response}"
    assert_manifest_byte_identity(canonical_invoke_response, response)


@pytest.mark.asyncio
async def test_manifest_passthrough_no_field_reordering(canonical_invoke_response, mock_rest_factory_canonical):
    """Defence-in-depth: each manifest entry's keys are forwarded as-is."""
    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=mock_rest_factory_canonical,
    )

    rest_entries = canonical_invoke_response["manifest"]["rate_table_uris"]
    mcp_entries = response["manifest"]["rate_table_uris"]
    assert len(rest_entries) == len(mcp_entries)
    for rest_e, mcp_e in zip(rest_entries, mcp_entries, strict=True):
        assert canonical_dumps(rest_e) == canonical_dumps(mcp_e)


def test_assert_manifest_byte_identity_detects_drift():
    """The asserter itself flags drift (no false-green from the gate logic)."""
    rest = {"manifest": {"rate_table_uris": [{"uri": "a", "content_hash": "x" * 64, "hash_algorithm": "sha256"}]}}
    mcp = {"manifest": {"rate_table_uris": [{"uri": "a", "content_hash": "y" * 64, "hash_algorithm": "sha256"}]}}
    with pytest.raises(AssertionError):
        assert_manifest_byte_identity(rest, mcp)


def test_assert_manifest_byte_identity_detects_missing_manifest():
    """An MCP response missing the manifest is a violation, not silently ok."""
    rest = {"manifest": {"rate_table_uris": []}}
    mcp = {}
    with pytest.raises(AssertionError):
        assert_manifest_byte_identity(rest, mcp)
