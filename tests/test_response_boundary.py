"""F-020: refuse inconsistent advisories and unsuccessful HTTP responses."""
from __future__ import annotations

import httpx
import pytest

from clawdog_mcp.rest_client import CalculatorRestClient
from clawdog_mcp.tools import invoke as invoke_module
from clawdog_mcp.tools.explain import explain


async def invoke_response(body, status=200):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=body, headers={"Location": "https://example.invalid/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        def factory(base):
            return CalculatorRestClient(base, bearer="", client=http)

        result = await invoke_module.invoke(
            calc="urn:lodgeit:calculator:fbt", version="1.0", params={},
            period="FY26", jurisdiction="AU", rest_client_factory=factory,
        )
    assert len(requests) == 1
    return result


@pytest.mark.parametrize("jurisdiction", ["GB", "NZ", "au", "", None, ["AU"], {"country": "AU"}])
async def test_conflicting_or_malformed_advisory_refuses_before_cache(jurisdiction):
    body = {"advisory": {"disclaimer": "Fabricated response", "jurisdiction": jurisdiction}}
    result = await invoke_response(body)
    assert result["error"]["code"] == "jurisdiction_mismatch"
    assert "invocation_id" not in result
    assert not invoke_module._invocation_cache


@pytest.mark.parametrize("status", [101, 199, 301, 302, 307, 308, 400, 500])
async def test_non_success_status_refuses_before_cache(status, canonical_invoke_response):
    result = await invoke_response(canonical_invoke_response, status)
    assert result["error"]["code"] == "rest_upstream_error"
    assert result["error"]["upstream_status_code"] == status
    assert "invocation_id" not in result
    assert not invoke_module._invocation_cache


@pytest.mark.parametrize("status", [200, 201, 299])
@pytest.mark.parametrize("declares_jurisdiction", [False, True])
async def test_successful_advisories_remain_unchanged(status, declares_jurisdiction):
    body = {"advisory": {"disclaimer": "Fabricated response"}, "result": "unchanged"}
    if declares_jurisdiction:
        body["advisory"]["jurisdiction"] = "AU"
    result = await invoke_response(body, status)
    invocation_id = result.pop("invocation_id")
    assert result == body
    assert explain(invocation_id)["jurisdiction"] == "AU"
