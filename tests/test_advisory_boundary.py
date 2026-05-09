"""NN#2 — Advisory-Boundary Contract (CLAWDOG/110 §3.2).

Binary-failure gate, two cases:
  1. REST returns a response with an `advisory` block → MCP returns it unchanged.
  2. REST returns a response WITHOUT `advisory` → MCP returns a structured
     ``advisory_boundary_violation`` error (NOT a raised exception, NOT a 5xx).

The second gate is load-bearing: it asserts the MCP server is the ENFORCEMENT
surface even though it is not the ISSUANCE surface (CLAWDOG/109 §8.2).
"""
from __future__ import annotations

import httpx
import pytest

from clawdog_mcp.tools.invoke import invoke
from tests.conftest import make_mock_rest_client_factory


@pytest.mark.asyncio
async def test_advisory_present_passthrough(canonical_invoke_response, mock_rest_factory_canonical):
    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=mock_rest_factory_canonical,
    )
    assert "error" not in response, f"unexpected error: {response.get('error')}"
    assert response["advisory"] == canonical_invoke_response["advisory"]


@pytest.mark.asyncio
async def test_advisory_omitted_surfaces_structured_error(canonical_invoke_response):
    """REST omits the advisory block → MCP returns advisory_boundary_violation."""
    bad_body = dict(canonical_invoke_response)
    bad_body.pop("advisory", None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/v1/calculators/" in request.url.path:
            return httpx.Response(200, json=bad_body)
        return httpx.Response(404, json={"error": "unmocked route"})

    factory = make_mock_rest_client_factory(handler)

    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=factory,
    )

    assert "error" in response, f"expected structured error, got: {response}"
    err = response["error"]
    assert err["code"] == "advisory_boundary_violation"
    # Detail names the upstream REST endpoint that produced the malformed response.
    assert "https://" in err["detail"] or "https://" in str(response.get("upstream_endpoint", ""))
    assert "upstream_endpoint" in response["error"]


@pytest.mark.asyncio
async def test_advisory_disclaimer_blank_surfaces_structured_error(canonical_invoke_response):
    """An advisory present-but-empty also fails the boundary check."""
    bad_body = dict(canonical_invoke_response)
    bad_body["advisory"] = dict(bad_body["advisory"])
    bad_body["advisory"]["disclaimer"] = "  "

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/v1/calculators/" in request.url.path:
            return httpx.Response(200, json=bad_body)
        return httpx.Response(404, json={"error": "unmocked route"})

    factory = make_mock_rest_client_factory(handler)

    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="FY26",
        jurisdiction="AU",
        rest_client_factory=factory,
    )

    assert response.get("error", {}).get("code") == "advisory_boundary_violation"
