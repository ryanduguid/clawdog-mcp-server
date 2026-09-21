"""Jurisdiction checks belong at the routing boundary, before REST invocation."""
from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from clawdog_mcp.rest_client import CalculatorRestClient
from clawdog_mcp.routing import DEFAULT_ROUTING_TABLE_PATH, load_routing_table
from clawdog_mcp.tools import invoke as invoke_module
from clawdog_mcp.tools.explain import explain

CALCULATORS = ["urn:lodgeit:calculator:fbt", "urn:lodgeit:calculator:depreciation"]


@pytest.mark.asyncio
@pytest.mark.parametrize("calc", CALCULATORS)
@pytest.mark.parametrize("jurisdiction", ["GB", "US"])
async def test_mismatch_stops_before_client_creation(monkeypatch, calc, jurisdiction):
    monkeypatch.delenv("CLAWDOG_MCP_ROUTING_TABLE", raising=False)
    factory = Mock(side_effect=AssertionError("REST client must not be constructed"))

    response = await invoke_module.invoke(
        calc=calc, version="1.0", params={}, period="FY26",
        jurisdiction=jurisdiction, rest_client_factory=factory,
    )

    assert response["error"]["code"] == "jurisdiction_mismatch"
    assert jurisdiction in response["error"]["detail"]
    assert "AU" in response["error"]["detail"]
    assert "invocation_id" not in response
    factory.assert_not_called()
    assert not invoke_module._invocation_cache


@pytest.mark.asyncio
@pytest.mark.parametrize("calc", CALCULATORS)
async def test_matching_jurisdiction_preserves_response_and_explanation(
    monkeypatch, calc, canonical_invoke_response,
):
    monkeypatch.delenv("CLAWDOG_MCP_ROUTING_TABLE", raising=False)
    body = canonical_invoke_response
    if calc.endswith(":depreciation"):
        body = {"audited_standard_assets": [], "advisory": body["advisory"]}
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        def factory(base):
            return CalculatorRestClient(base, bearer="", client=http)

        response = await invoke_module.invoke(
            calc=calc, version="1.0", params={}, period="FY26",
            jurisdiction="AU", rest_client_factory=factory,
        )

    assert len(requests) == 1
    invocation_id = response.pop("invocation_id")
    assert response == body
    assert explain(invocation_id)["jurisdiction"] == "AU"


@pytest.mark.asyncio
@pytest.mark.parametrize("jurisdiction", ["AU", "GB"])
async def test_jurisdiction_is_taken_from_route_metadata(monkeypatch, jurisdiction):
    entry = load_routing_table(DEFAULT_ROUTING_TABLE_PATH)[0].copy()
    entry["advisory_jurisdiction"] = "GB"
    monkeypatch.setattr(invoke_module, "load_routing_table", lambda: [entry])
    body = {"advisory": {"disclaimer": "Synthetic test response", "jurisdiction": "GB"}}
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        def factory(base):
            return CalculatorRestClient(base, bearer="", client=http)

        response = await invoke_module.invoke(
            calc=entry["calc"], version=entry["version"], params={}, period="FY26",
            jurisdiction=jurisdiction, rest_client_factory=factory,
        )

    if jurisdiction == "GB":
        assert len(requests) == 1
        assert explain(response["invocation_id"])["jurisdiction"] == "GB"
    else:
        assert response["error"]["code"] == "jurisdiction_mismatch"
        assert not requests
        assert not invoke_module._invocation_cache
