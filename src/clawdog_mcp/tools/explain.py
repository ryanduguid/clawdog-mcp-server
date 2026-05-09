"""calculator.explain — Phase 3b implementation.

Looks up an invocation_id in the in-memory LRU populated by calculator.invoke.
Cache miss returns a structured pointer to the regression-suite root rather
than fabricating a trace.

Prolog-trace integration (``library(prolog_stack)``) is deferred to Phase 3d
per CLAWDOG/109 §8.2.
"""
from __future__ import annotations

from clawdog_mcp.schemas import ExplainInput
from clawdog_mcp.tools.invoke import cache_get


def explain(invocation_id: str) -> dict:
    try:
        validated = ExplainInput(invocation_id=invocation_id)
    except Exception as e:
        return {"error": {"code": "atom_boundary_violation", "detail": str(e)}}

    payload = cache_get(validated.invocation_id)
    if payload is None:
        return {
            "error": {
                "code": "invocation_not_found",
                "detail": (
                    "calculator.explain only resolves invocations from the current "
                    "MCP server session; for forensic-grade tracing, query the "
                    "calculator engine's regression-suite directly."
                ),
            }
        }

    rest = payload["rest_response"]
    return {
        "invocation_id": payload["invocation_id"],
        "calc": payload["calc"],
        "version": payload["version"],
        "period": payload["period"],
        "jurisdiction": payload["jurisdiction"],
        "regression_suite_root": payload.get("regression_suite_root"),
        "trace": rest.get("trace"),
        "manifest": rest.get("manifest"),
        "advisory": rest.get("advisory"),
        "phase_3b_note": (
            "Phase 3b explain returns the cached REST trace. Prolog-stack-anchored "
            "step-by-step traces are deferred to Phase 3d (CLAWDOG/109 §8.2)."
        ),
    }
