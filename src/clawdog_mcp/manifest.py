"""Manifest passthrough validator + tools_manifest dumper.

CLAWDOG/110 §3.1 Manifest-Fidelity Contract: at the MCP layer, the manifest
issued by the upstream REST surface is forwarded **unmodified**. The MCP
server does NOT recompute, re-serialise, or enrich the manifest.

L402 boundary β (META/005 §2.2 + §4): only the manifest-producing layer
issues; only the manifest-producing layer hashes. The MCP layer is a
transport adapter — never a manifest source.

This module exposes:

* ``assert_manifest_byte_identity`` — used by the binary-failure gate
  (``tests/test_manifest_passthrough.py``) to assert MCP and REST manifests
  are byte-identical under canonical JSON serialisation.
* ``assert_advisory_present`` — used by the ``calculator.invoke`` tool to
  enforce CLAWDOG/110 §3.2 Advisory-Boundary at the MCP egress.
* ``dump_tools_manifest`` — Makefile + CI introspection helper for NN#4
  (Tools Manifest Drift Gate).
"""
from __future__ import annotations

import inspect
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

CANONICAL_JSON_KWARGS = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
}


def canonical_dumps(obj: Any) -> str:
    """Serialise ``obj`` to a canonical JSON string (sort_keys, no whitespace).

    This is the byte-identity reference for the manifest-passthrough gate.
    Any divergence between MCP and REST serialisation that would have leaked
    differently-ordered JSON to the wire is caught by this canonicaliser.
    """
    return json.dumps(obj, **CANONICAL_JSON_KWARGS)


def assert_manifest_byte_identity(rest_response: dict, mcp_response: dict) -> None:
    """Assert the ``manifest`` block in the MCP response is byte-identical to
    the ``manifest`` block in the upstream REST response.

    Raises ``AssertionError`` on divergence (used by the binary-failure gate).
    """
    rest_manifest = rest_response.get("manifest")
    mcp_manifest = mcp_response.get("manifest")
    if rest_manifest is None and mcp_manifest is None:
        return  # Phase 3a non-manifest endpoints (e.g. /healthz) have no manifest.
    if rest_manifest is None:
        raise AssertionError(
            "manifest passthrough: REST response has no manifest, but MCP response does"
        )
    if mcp_manifest is None:
        raise AssertionError(
            "manifest passthrough: MCP response is missing the manifest the REST surface issued"
        )
    rest_canon = canonical_dumps(rest_manifest)
    mcp_canon = canonical_dumps(mcp_manifest)
    if rest_canon != mcp_canon:
        raise AssertionError(
            "manifest passthrough byte-diff (CLAWDOG/110 §3.1 violation):\n"
            f"  REST:  {rest_canon}\n"
            f"  MCP:   {mcp_canon}"
        )


def assert_advisory_present(response: dict, upstream_endpoint: str) -> None:
    """Assert the ``advisory`` block is present and structurally valid.

    Raises ``AdvisoryBoundaryViolation`` if absent or malformed. The MCP
    ``calculator.invoke`` tool catches this and returns a structured
    ``advisory_boundary_violation`` error to the agent client (CLAWDOG/110
    §3.2).
    """
    advisory = response.get("advisory")
    if advisory is None:
        raise AdvisoryBoundaryViolation(
            f"upstream REST endpoint {upstream_endpoint!r} returned a "
            f"calculator.invoke response with no `advisory` block; CLAWDOG/110 "
            f"§3.2 requires every invocation egress to carry a registered-tax-"
            f"agent advisory disclaimer."
        )
    if not isinstance(advisory, dict):
        raise AdvisoryBoundaryViolation(
            f"upstream REST endpoint {upstream_endpoint!r} returned a "
            f"non-dict `advisory` field (got {type(advisory).__name__})."
        )
    disclaimer = advisory.get("disclaimer")
    if not isinstance(disclaimer, str) or not disclaimer.strip():
        raise AdvisoryBoundaryViolation(
            f"upstream REST endpoint {upstream_endpoint!r} returned an `advisory` "
            f"block with no disclaimer text."
        )


class AdvisoryBoundaryViolation(RuntimeError):
    """Raised by ``assert_advisory_present`` when the upstream omits the advisory.

    Caught at the MCP tool boundary; converted to a structured tool-result
    error (NOT a raised exception out of the tool — see CLAWDOG/110 §3.2 +
    the binary-failure gate ``tests/test_advisory_boundary.py``).
    """


async def dump_tools_manifest(app: FastMCP) -> dict:
    """Return a JSON-serialisable dict describing all tools exposed by ``app``.

    Used by:
      * ``make tools-manifest`` (regeneration of the committed reference)
      * ``make tools-manifest-check`` (CI drift gate, NN#4)
      * ``tests/test_phase3b_e2e.py`` (defence-in-depth)
    """
    tools = await app.list_tools()
    return {
        "schema_version": 1,
        "server_name": app.name,
        "tools": [
            {
                "name": t.name,
                "description": inspect.cleandoc(t.description or ""),
                "input_schema": t.inputSchema,
            }
            for t in sorted(tools, key=lambda t: t.name)
        ],
    }
