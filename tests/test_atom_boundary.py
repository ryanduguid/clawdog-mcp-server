"""NN#3 — Atom-vs-Bridge Boundary (CLAWDOG/110 §3.3).

Binary-failure gate: smuggling jurisdiction/currency interpretation into atom
fields fails pydantic validation with a structured error. Each parametrised
case asserts a known smuggling shape from the CLAWDOG/110 §3.3 catalogue.
"""
from __future__ import annotations

import pytest

from clawdog_mcp.schemas import InvokeInput
from clawdog_mcp.tools.invoke import invoke

# Each case: (field, value, why_forbidden)
SMUGGLING_CASES_PERIOD = [
    ("AU_FY26", "fuses jurisdiction prefix into period atom"),
    ("FY26-AU", "fuses jurisdiction suffix into period atom"),
    ("FY26_UK", "fuses jurisdiction suffix into period atom"),
    ("uk_fy26", "fuses jurisdiction prefix into period atom"),
    ("fy_aud_2026", "fuses currency into period atom"),
    ("FY26-GBP", "fuses currency into period atom"),
]
SMUGGLING_CASES_CALC = [
    ("urn:lodgeit:calculator:fbt-au", "fuses jurisdiction into calc URI"),
    ("urn:lodgeit:calculator:au-fbt", "fuses jurisdiction into calc URI"),
]


@pytest.mark.parametrize("bad_period,reason", SMUGGLING_CASES_PERIOD)
def test_period_smuggling_rejected(bad_period: str, reason: str):
    """Pydantic schema rejects period atoms that smuggle interpretation."""
    with pytest.raises(Exception) as exc_info:
        InvokeInput(
            calc="urn:lodgeit:calculator:fbt",
            version="1.0",
            params={},
            period=bad_period,
            jurisdiction="AU",
        )
    msg = str(exc_info.value).lower()
    assert "period" in msg or "smuggle" in msg, f"error must name the violation: {exc_info.value}"


@pytest.mark.parametrize("bad_calc,reason", SMUGGLING_CASES_CALC)
def test_calc_smuggling_rejected(bad_calc: str, reason: str):
    """Calculator URI atoms must not encode jurisdiction."""
    with pytest.raises(Exception):
        InvokeInput(
            calc=bad_calc,
            version="1.0",
            params={},
            period="FY26",
            jurisdiction="AU",
        )


def test_jurisdiction_must_be_iso_alpha2():
    """jurisdiction is a bare ISO 3166 alpha-2 code; long-form is rejected."""
    with pytest.raises(Exception):
        InvokeInput(
            calc="urn:lodgeit:calculator:fbt",
            version="1.0",
            params={},
            period="FY26",
            jurisdiction="Australia",
        )


def test_version_dotted_decimal_required():
    with pytest.raises(Exception):
        InvokeInput(
            calc="urn:lodgeit:calculator:fbt",
            version="v1",
            params={},
            period="FY26",
            jurisdiction="AU",
        )


def test_extra_fields_forbidden():
    """`extra="forbid"` keeps atoms strictly typed."""
    with pytest.raises(Exception):
        InvokeInput(
            calc="urn:lodgeit:calculator:fbt",
            version="1.0",
            params={},
            period="FY26",
            jurisdiction="AU",
            year_with_juris="AU_FY26",  # type: ignore[call-arg]
        )


@pytest.mark.asyncio
async def test_invoke_tool_returns_atom_boundary_violation_for_smuggled_period(mock_rest_factory_canonical):
    """At the tool layer (not the schema), smuggled atoms return a structured error."""
    response = await invoke(
        calc="urn:lodgeit:calculator:fbt",
        version="1.0",
        params={"businessUsePercentage": 75},
        period="AU_FY26",
        jurisdiction="AU",
        rest_client_factory=mock_rest_factory_canonical,
    )
    assert response.get("error", {}).get("code") == "atom_boundary_violation"
