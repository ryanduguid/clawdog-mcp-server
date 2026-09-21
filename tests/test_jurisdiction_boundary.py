"""Jurisdiction checks must run before dispatch and before caching."""
import json
from copy import deepcopy
from datetime import timedelta

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from clawdog_mcp.server import build_app
from clawdog_mcp.tools import invoke as invoke_module
from tests.conftest import make_mock_rest_client_factory

CALCS = ["urn:lodgeit:calculator:fbt", "urn:lodgeit:calculator:depreciation"]


@pytest.mark.parametrize("calc", CALCS)
@pytest.mark.parametrize("jurisdiction", ["GB", "NZ"])
async def test_route_mismatch_does_not_construct_client(calc, jurisdiction):
    def unexpected_client(base):
        pytest.fail("A mismatched request must not reach the REST client")

    result = await invoke_module.invoke(
        calc, "1.0", {}, "FY26", jurisdiction, rest_client_factory=unexpected_client
    )
    assert result["error"]["code"] == "jurisdiction_mismatch"
    assert result["error"]["boundary"] == "route"
    assert not invoke_module._invocation_cache


@pytest.mark.parametrize("calc", CALCS)
@pytest.mark.parametrize("advisory_jurisdiction", ["AU", "GB", "NZ", None, "absent"])
async def test_advisory_jurisdiction_before_cache(calc, advisory_jurisdiction, canonical_invoke_response):
    upstream = deepcopy(canonical_invoke_response)
    if advisory_jurisdiction == "absent":
        del upstream["advisory"]["jurisdiction"]
    else:
        upstream["advisory"]["jurisdiction"] = advisory_jurisdiction
    original = deepcopy(upstream)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=upstream)

    result = await invoke_module.invoke(
        calc, "1.0", {"fabricated": True}, "FY26", "AU",
        rest_client_factory=make_mock_rest_client_factory(handler),
    )
    assert len(requests) == 1
    assert upstream == original
    if advisory_jurisdiction in ("AU", "absent"):
        invocation_id = result.pop("invocation_id")
        assert result == original
        cached = invoke_module.cache_get(invocation_id)
        assert cached["jurisdiction"] == "AU"
        assert cached["rest_response"] == original
    else:
        assert result["error"]["code"] == "jurisdiction_mismatch"
        assert result["error"]["boundary"] == "advisory"
        assert not invoke_module._invocation_cache


@pytest.mark.parametrize("status", [101, 301, 302, 307, 308, 400, 500])
async def test_non_success_response_is_never_cached(status, canonical_invoke_response):
    def handler(request):
        return httpx.Response(status, json=canonical_invoke_response)

    result = await invoke_module.invoke(
        CALCS[0], "1.0", {}, "FY26", "AU",
        rest_client_factory=make_mock_rest_client_factory(handler),
    )
    assert result["error"]["code"] == "rest_upstream_error"
    assert result["error"]["upstream_status_code"] == status
    assert not invoke_module._invocation_cache


async def test_jurisdiction_boundary_through_sdk(monkeypatch, canonical_invoke_response):
    upstream = deepcopy(canonical_invoke_response)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=upstream)

    monkeypatch.setattr(
        invoke_module, "CalculatorRestClient", make_mock_rest_client_factory(handler)
    )
    async with create_connected_server_and_client_session(
        build_app(), read_timeout_seconds=timedelta(seconds=10)
    ) as session:
        for calc in CALCS:
            arguments = dict(calc=calc, version="1.0", params={}, period="FY26", jurisdiction="GB")
            result = await session.call_tool("calculator_invoke", arguments)
            assert not result.isError
            assert json.loads(result.content[0].text)["error"]["boundary"] == "route"
            assert not requests
        arguments["jurisdiction"] = "AU"
        upstream["advisory"]["jurisdiction"] = "GB"
        result = await session.call_tool("calculator_invoke", arguments)
        assert not result.isError
        assert json.loads(result.content[0].text)["error"]["boundary"] == "advisory"
        assert len(requests) == 1
        assert not invoke_module._invocation_cache
        upstream["advisory"]["jurisdiction"] = "AU"
        result = await session.call_tool("calculator_invoke", arguments)
        assert not result.isError
        invocation_id = json.loads(result.content[0].text)["invocation_id"]
        explained = await session.call_tool("calculator_explain", {"invocation_id": invocation_id})
        assert json.loads(explained.content[0].text)["jurisdiction"] == "AU"
