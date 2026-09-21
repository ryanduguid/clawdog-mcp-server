"""REST client — thin httpx wrapper around the Phase 3a calculator-api.

Topology: the MCP server shells calculator.invoke calls to
``clawdog-calculator-api`` (Phase 3a, REST, Cloud Run). No local calculation,
no enrichment, no transformation. The response body is parsed as JSON and
returned as a Python dict; the caller is responsible for byte-identity
discipline (see manifest.py / assert_manifest_byte_identity).

L402 boundary β (META/005 §2.2 + §4): the REST surface is the L402 issuer.
This client forwards a bearer token (``MCP_REST_BEARER`` env or per-call
override) on the ``Authorization`` header; it does NOT mint, parse, or
enforce L402 macaroons. Phase 3b posture: bearer is optional (matches the
unauthenticated Phase 3a Cloud Run service).
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_TIMEOUT_S = 30.0


class RestUpstreamError(RuntimeError):
    """Raised when the upstream REST surface returns a non-2xx response or
    is structurally malformed (non-JSON body, etc.)."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CalculatorRestClient:
    """Thin httpx-based forwarder.

    The client is constructed per-invocation by the MCP tool layer and accepts
    an optional pre-built ``httpx.AsyncClient`` for test-injection — that's the
    seam ``test_phase3b_e2e.py`` and the production-bundle gate use to install
    a ``httpx.MockTransport`` without monkey-patching.
    """

    def __init__(
        self,
        rest_base: str,
        *,
        bearer: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not rest_base.startswith("https://") and not rest_base.startswith("http://"):
            raise ValueError(f"rest_base must be http(s); got {rest_base!r}")
        self.rest_base = rest_base.rstrip("/")
        self.bearer = bearer if bearer is not None else os.environ.get("MCP_REST_BEARER")
        self._client = client
        self._owns_client = client is None
        self._timeout_s = timeout_s

    async def __aenter__(self) -> CalculatorRestClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
            self._owns_client = True
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.bearer:
            h["Authorization"] = f"Bearer {self.bearer}"
        return h

    async def invoke(
        self,
        *,
        path_template: str,
        calc_uri: str,
        period_uri: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        """POST a calculator.invoke to the REST surface.

        :returns: (parsed_response_body, full_request_url) — the URL is
            returned for inclusion in advisory-boundary-violation error
            details (CLAWDOG/110 §3.2).
        :raises RestUpstreamError: on non-2xx or non-JSON response.
        """
        if self._client is None:
            raise RuntimeError("CalculatorRestClient must be used as an async context manager")
        path = path_template.format(
            calc_uri=quote(calc_uri, safe=""),
            period_uri=quote(period_uri, safe=""),
        )
        url = f"{self.rest_base}{path}"
        try:
            resp = await self._client.post(url, json=params, headers=self._headers())
        except httpx.HTTPError as e:
            raise RestUpstreamError(f"transport error contacting {url}: {e}") from e
        if not 200 <= resp.status_code < 300:
            raise RestUpstreamError(
                f"upstream REST returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:1000],
            )
        try:
            body = resp.json()
        except ValueError as e:
            raise RestUpstreamError(
                f"upstream REST returned non-JSON body: {resp.text[:200]!r}",
                status_code=resp.status_code,
                body=resp.text[:1000],
            ) from e
        if not isinstance(body, dict):
            raise RestUpstreamError(
                f"upstream REST returned non-dict JSON body of type {type(body).__name__}",
                status_code=resp.status_code,
            )
        return body, url
