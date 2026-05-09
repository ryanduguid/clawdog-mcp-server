"""calculator.discover — Phase 3b implementation.

Free tool; substring-matches the intent string against entry summaries.
Returns a list of ``{calc, version, summary}`` dicts.

Fano-backed semantic discovery is deferred to Phase 3d (CLAWDOG/109 §8.4).
"""
from __future__ import annotations

from clawdog_mcp.routing import (
    RoutingBundleMalformedError,
    RoutingBundleMissingError,
    load_routing_table,
)
from clawdog_mcp.schemas import DiscoverInput


def discover(intent: str) -> dict:
    """Return ``{"matches": [...]}`` or a structured error dict.

    The dict-shape (rather than raising) matches the CLAWDOG/110 §3.2 pattern:
    structured tool errors are dicts the agent client receives as tool
    output, not exceptions that become stdio-stream EOFs.
    """
    try:
        validated = DiscoverInput(intent=intent)
    except Exception as e:  # pydantic.ValidationError or similar
        return {
            "error": {"code": "atom_boundary_violation", "detail": str(e)},
            "matches": [],
        }

    try:
        table = load_routing_table()
    except (RoutingBundleMissingError, RoutingBundleMalformedError) as e:
        return {
            "error": {"code": "routing_bundle_unavailable", "detail": str(e)},
            "matches": [],
        }

    # Phase 3b: token-AND substring match (case-insensitive). Every whitespace-
    # separated token in the intent must appear somewhere in the entry summary.
    # Stopwords are not stripped — Phase 3b is deliberately dumb; Fano semantic
    # discovery is Phase 3d.
    needle_tokens = [t for t in validated.intent.lower().split() if t]
    matches = []
    for entry in table:
        haystack = (entry.get("summary") or "").lower()
        if needle_tokens and all(t in haystack for t in needle_tokens):
            matches.append(
                {
                    "calc": entry["calc"],
                    "version": entry["version"],
                    "summary": entry["summary"],
                }
            )
    return {"matches": matches}
