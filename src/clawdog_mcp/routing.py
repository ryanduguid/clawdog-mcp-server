"""Routing-table loader + production resolver.

Standing Rule #12 (Production Resolver Shape Assertions): the resolver here
is the load-bearing surface that ``tests/test_production_bundle.py`` exercises
without hermetic env overrides. The resolver order:

1. ``CLAWDOG_MCP_ROUTING_TABLE`` env var (test/hermetic override). When set,
   the path is used as-is; if it does not exist or is malformed, the
   resolver raises a structured ``RoutingBundleMissingError`` (defence-in-depth).
2. The packaged path next to this module: ``clawdog_mcp/config/routing_table.yaml``.

The loader returns a list of ``RoutingEntry`` dicts. Structural-marker
validation is enforced (top-level ``routing_table:`` key, required per-entry
fields, https rest_base) — failures raise ``RoutingBundleMalformedError``.

CLAWDOG/110 §3.3 Atom-vs-Bridge Boundary: `calc` and `version` are atoms
carrying identity only; the interpretive routing logic (which REST endpoint,
which path template, which jurisdiction the advisory refers to) lives at
this bridge layer, not in the atom values.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_ROUTING_TABLE_PATH = PACKAGE_ROOT / "config" / "routing_table.yaml"

REQUIRED_ENTRY_KEYS = (
    "calc",
    "version",
    "summary",
    "rest_base",
    "regression_suite_root",
    "advisory_jurisdiction",
)


class RoutingEntry(TypedDict, total=False):
    calc: str
    version: str
    summary: str
    rest_base: str
    rest_invoke_path_template: str
    regression_suite_root: str
    advisory_jurisdiction: str


class RoutingBundleMissingError(RuntimeError):
    """Raised when the routing-table file cannot be located on disk.

    Phase 3b production-bundle gate (Standing Rule #12 assertion class 5):
    the route handler converts this to a structured MCP-protocol error,
    NOT an uncaught exception that becomes a stdio-stream EOF.
    """


class RoutingBundleMalformedError(RuntimeError):
    """Raised when the routing-table file exists but fails structural-marker
    validation (missing top-level key, missing required entry fields, etc.)."""


def resolve_routing_table_path() -> Path:
    """Return the path the production resolver would use, given current env.

    The path returned is NOT guaranteed to exist; callers should verify.
    """
    env_override = os.environ.get("CLAWDOG_MCP_ROUTING_TABLE")
    if env_override:
        return Path(env_override).expanduser().resolve()
    return DEFAULT_ROUTING_TABLE_PATH


def load_routing_table(path: Path | None = None) -> list[RoutingEntry]:
    """Load + structurally validate the routing table.

    :param path: optional explicit path (test injection). When ``None``,
        ``resolve_routing_table_path()`` is used (production resolver).
    :raises RoutingBundleMissingError: bundle path does not exist.
    :raises RoutingBundleMalformedError: structural-marker validation failed.
    """
    p = path if path is not None else resolve_routing_table_path()
    if not p.is_file():
        raise RoutingBundleMissingError(
            f"routing-table bundle missing at {p}; the package layout expects "
            f"clawdog_mcp/config/routing_table.yaml to be installed alongside "
            f"the package, or CLAWDOG_MCP_ROUTING_TABLE to point at a readable file."
        )
    try:
        raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise RoutingBundleMalformedError(
            f"routing-table bundle at {p} is not valid YAML: {e}"
        ) from e

    if not isinstance(raw, dict) or "routing_table" not in raw:
        raise RoutingBundleMalformedError(
            f"routing-table bundle at {p} missing top-level 'routing_table:' key"
        )
    table = raw["routing_table"]
    if not isinstance(table, list):
        raise RoutingBundleMalformedError(
            f"routing-table bundle at {p} 'routing_table' must be a list"
        )

    entries: list[RoutingEntry] = []
    for i, entry in enumerate(table):
        if not isinstance(entry, dict):
            raise RoutingBundleMalformedError(
                f"routing-table entry #{i} is not a mapping: {entry!r}"
            )
        for key in REQUIRED_ENTRY_KEYS:
            if key not in entry or entry[key] in (None, ""):
                raise RoutingBundleMalformedError(
                    f"routing-table entry #{i} missing required key {key!r}"
                )
        rest_base = entry["rest_base"]
        if not isinstance(rest_base, str) or not rest_base.startswith("https://"):
            raise RoutingBundleMalformedError(
                f"routing-table entry #{i} rest_base must be an https URL; got {rest_base!r}"
            )
        # Default the path template if not present.
        entry.setdefault(
            "rest_invoke_path_template",
            "/v1/calculators/{calc_uri}/{period_uri}",
        )
        # Normalise summary whitespace (YAML folded scalars can carry trailing newlines).
        entry["summary"] = " ".join(str(entry["summary"]).split())
        entries.append(entry)  # type: ignore[arg-type]
    return entries


def find_entry(
    table: list[RoutingEntry], calc: str, version: str
) -> RoutingEntry | None:
    """Look up the routing entry for an exact (calc, version) atom pair.

    Atom-equality only; no normalisation, no fuzzy match (CLAWDOG/110 §3.3).
    """
    for entry in table:
        if entry.get("calc") == calc and entry.get("version") == version:
            return entry
    return None
