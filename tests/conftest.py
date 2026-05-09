"""Shared test fixtures for the binary-failure gate suite."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from clawdog_mcp.rest_client import CalculatorRestClient
from clawdog_mcp.tools import invoke as invoke_module

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_invocation_cache():
    """Each test starts with an empty invocation cache."""
    invoke_module.cache_clear()
    yield
    invoke_module.cache_clear()


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def canonical_invoke_response() -> dict:
    """The canonical Phase 3a invoke response (PR-D Case 5 deemed-dispatch)."""
    return load_fixture("sample_invoke_response.json")


def make_mock_rest_client_factory(
    handler: Any,
):
    """Return a factory that yields a ``CalculatorRestClient`` wired to a
    ``MockTransport`` driven by ``handler``.
    """
    def factory(rest_base: str) -> CalculatorRestClient:
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        return CalculatorRestClient(rest_base, client=client)
    return factory


@pytest.fixture
def mock_rest_factory_canonical(canonical_invoke_response):
    """A REST mock that returns ``canonical_invoke_response`` for any POST
    under /v1/calculators/."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/v1/calculators/" in request.url.path:
            return httpx.Response(200, json=canonical_invoke_response)
        return httpx.Response(404, json={"error": "unmocked route"})

    return make_mock_rest_client_factory(handler)
