"""calculator.invoke — Phase 3b implementation.

Shells to ``clawdog-calculator-api`` (Phase 3a REST) and forwards the
response byte-identically. Enforces the advisory boundary at the MCP egress
(CLAWDOG/110 §3.2).
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Any

from pydantic import ValidationError

from clawdog_mcp.manifest import AdvisoryBoundaryViolation, assert_advisory_present
from clawdog_mcp.rest_client import CalculatorRestClient, RestUpstreamError
from clawdog_mcp.routing import (
    RoutingBundleMalformedError,
    RoutingBundleMissingError,
    find_entry,
    load_routing_table,
)
from clawdog_mcp.schemas import InvokeInput

# Phase 3b: in-memory invocation cache for calculator.explain (size-bounded
# LRU). NOT a database. Wiped on server restart. Forensic-grade tracing
# routes through the regression-suite directly (calculator.explain returns a
# pointer when invocation is not in cache).
INVOCATION_CACHE_MAX = 256
_invocation_cache: OrderedDict[str, dict] = OrderedDict()


def _cache_put(invocation_id: str, payload: dict) -> None:
    _invocation_cache[invocation_id] = payload
    _invocation_cache.move_to_end(invocation_id)
    while len(_invocation_cache) > INVOCATION_CACHE_MAX:
        _invocation_cache.popitem(last=False)


def cache_get(invocation_id: str) -> dict | None:
    payload = _invocation_cache.get(invocation_id)
    if payload is not None:
        _invocation_cache.move_to_end(invocation_id)
    return payload


def cache_clear() -> None:
    """Test helper — clear the LRU between cases."""
    _invocation_cache.clear()


async def invoke(
    calc: str,
    version: str,
    params: dict[str, Any],
    period: str,
    jurisdiction: str,
    *,
    rest_client_factory=None,
) -> dict:
    """Forward a calculator.invoke to the REST upstream.

    :param rest_client_factory: optional callable ``(rest_base) -> CalculatorRestClient``
        for test injection. When ``None``, a default client is constructed.
    """
    # 1. Atom-boundary validation (NN#3).
    try:
        validated = InvokeInput(
            calc=calc, version=version, params=params, period=period, jurisdiction=jurisdiction
        )
    except ValidationError as e:
        return {"error": {"code": "atom_boundary_violation", "detail": e.errors()}}

    # 2. Routing-table resolution (Standing Rule #12 surface).
    try:
        table = load_routing_table()
    except (RoutingBundleMissingError, RoutingBundleMalformedError) as e:
        return {
            "error": {"code": "routing_bundle_unavailable", "detail": str(e)},
        }

    entry = find_entry(table, validated.calc, validated.version)
    if entry is None:
        return {
            "error": {
                "code": "calculator_not_routed",
                "detail": (
                    f"no routing entry for calc={validated.calc!r} version={validated.version!r}; "
                    f"call calculator.discover first"
                ),
            }
        }

    if validated.jurisdiction != entry["advisory_jurisdiction"]:
        return {
            "error": {
                "code": "jurisdiction_mismatch",
                "boundary": "route",
                "detail": "Requested jurisdiction does not match the calculator route.",
                "requested_jurisdiction": validated.jurisdiction,
                "routed_jurisdiction": entry["advisory_jurisdiction"],
            }
        }

    # 3. Translate atoms to the URI shape the REST surface expects.
    #    Phase 3b only routes FBT car operating cost; the period URI is
    #    constructed bridge-side from the bare period scalar (or accepted
    #    as a URI verbatim). This is the bridge interpretation layer
    #    (CLAWDOG/110 §3.3) — atoms remain bare.
    period_uri = _bridge_period_to_uri(validated.period, validated.calc)
    calc_uri = _bridge_calc_to_uri(validated.calc)

    rest_base = entry["rest_base"]
    path_template = entry.get("rest_invoke_path_template", "/v1/calculators/{calc_uri}/{period_uri}")

    # 4. Forward to REST (no enrichment, no transformation).
    if rest_client_factory is None:
        def _factory(base: str) -> CalculatorRestClient:
            return CalculatorRestClient(base)
        rest_client_factory = _factory

    full_url_for_error = f"{rest_base}{path_template}"
    try:
        async with rest_client_factory(rest_base) as client:
            body, full_url = await client.invoke(
                path_template=path_template,
                calc_uri=calc_uri,
                period_uri=period_uri,
                params=validated.params,
            )
    except RestUpstreamError as e:
        return {
            "error": {
                "code": "rest_upstream_error",
                "detail": str(e),
                "upstream_status_code": e.status_code,
                "upstream_endpoint": full_url_for_error,
            }
        }

    # 5. Advisory-boundary enforcement (NN#2). Structured error on omission.
    try:
        assert_advisory_present(body, full_url)
    except AdvisoryBoundaryViolation as e:
        return {
            "error": {
                "code": "advisory_boundary_violation",
                "detail": str(e),
                "upstream_endpoint": full_url,
            }
        }

    advisory = body["advisory"]
    if "jurisdiction" in advisory and advisory["jurisdiction"] != validated.jurisdiction:
        return {
            "error": {
                "code": "jurisdiction_mismatch",
                "boundary": "advisory",
                "detail": "Upstream advisory jurisdiction does not match the accepted request.",
                "requested_jurisdiction": validated.jurisdiction,
                "advisory_jurisdiction": advisory["jurisdiction"],
                "upstream_endpoint": full_url,
            }
        }

    # 6. Cache + assign invocation_id (for calculator.explain).
    invocation_id = f"inv_{uuid.uuid4().hex}"
    cached_payload = {
        "invocation_id": invocation_id,
        "calc": validated.calc,
        "version": validated.version,
        "period": validated.period,
        "jurisdiction": validated.jurisdiction,
        "regression_suite_root": entry.get("regression_suite_root"),
        "rest_response": body,
    }
    _cache_put(invocation_id, cached_payload)

    # 7. Return the byte-identical REST body, plus invocation_id at top level.
    #    The REST body's manifest/advisory/trace/taxable_value are forwarded
    #    unmodified; we only add the MCP-layer invocation_id (deliberately
    #    NOT inside `manifest` or `advisory` to preserve byte-identity of
    #    those blocks).
    return {**body, "invocation_id": invocation_id}


def _bridge_period_to_uri(period: str, calc: str) -> str:
    """Map a bare period scalar to the canonical SBRM period URI.

    If `period` is already a URI, return as-is. Otherwise construct
    ``urn:sbrm:period:<calc_short>:<period_id_lower>``.

    Phase 3b only knows how to bridge FBT periods; if the calc is not
    FBT, return the period as-is and let the REST surface handle it.
    """
    if period.startswith("urn:sbrm:period:"):
        return period
    # Bridge FY26 -> fy2026 when calc is FBT.
    if "fbt" in calc.lower():
        norm = period.lower()
        if norm.startswith("fy"):
            tail = norm[2:]
            if len(tail) == 2:
                # FY26 -> fy2026
                norm = f"fy20{tail}"
        return f"urn:sbrm:period:fbt:{norm}"
    return period


def _bridge_calc_to_uri(calc: str) -> str:
    """Map the routing-table calc atom to the REST surface's calc URI.

    Phase 3a's REST surface uses ``urn:sbrm:calculator:fbt:car-operating-cost``
    while the Phase 3b routing-table atom is ``urn:lodgeit:calculator:fbt``.
    The bridge expands one to the other (interpretation lives at the bridge,
    not in the atom).
    """
    if calc == "urn:lodgeit:calculator:fbt":
        return "urn:sbrm:calculator:fbt:car-operating-cost"
    return calc
