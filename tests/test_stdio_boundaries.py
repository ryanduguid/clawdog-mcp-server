"""Exercise the actual MCP transport with fabricated HTTP responses only."""
from __future__ import annotations

import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = """
import json
import httpx
from clawdog_mcp.rest_client import CalculatorRestClient
from clawdog_mcp.server import build_app
from clawdog_mcp.tools import invoke as invoke_module

def handler(request):
    params = json.loads(request.content)
    body = {"advisory": {"disclaimer": "Fabricated response",
                         "jurisdiction": params.get("country", "AU")}}
    return httpx.Response(params.get("status", 200), json=body)

def factory(base):
    client = CalculatorRestClient(base, bearer="", client=httpx.AsyncClient(
        transport=httpx.MockTransport(handler)))
    client._owns_client = True
    return client

invoke_module.CalculatorRestClient = factory
build_app().run(transport="stdio")
"""


async def test_stdio_rejects_inconsistent_results_and_preserves_matching_calls(monkeypatch):
    monkeypatch.delenv("CLAWDOG_MCP_ROUTING_TABLE", raising=False)
    server = StdioServerParameters(command=sys.executable, args=["-c", SERVER])
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        for calc in ["urn:lodgeit:calculator:fbt", "urn:lodgeit:calculator:depreciation"]:
            for jurisdiction, params, expected in [
                ("GB", {}, "jurisdiction_mismatch"),
                ("NZ", {}, "jurisdiction_mismatch"),
                ("AU", {"country": "GB"}, "jurisdiction_mismatch"),
                ("AU", {"status": 302}, "rest_upstream_error"),
                ("AU", {}, None),
            ]:
                result = await session.call_tool("calculator_invoke", {
                    "calc": calc, "version": "1.0", "period": "FY26",
                    "jurisdiction": jurisdiction, "params": params,
                })
                assert not result.isError
                body = json.loads(result.content[0].text)
                if expected:
                    assert body["error"]["code"] == expected
                    assert "invocation_id" not in body
                else:
                    explained = await session.call_tool("calculator_explain", {
                        "invocation_id": body["invocation_id"],
                    })
                    assert json.loads(explained.content[0].text)["jurisdiction"] == "AU"
                    assert body["advisory"]["jurisdiction"] == "AU"
