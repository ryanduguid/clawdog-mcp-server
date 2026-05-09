"""Pydantic schemas for MCP meta-tool inputs (CLAWDOG/110 §3.3 Non-Negotiable #3).

Atom-vs-Bridge Boundary: each meta-tool's input fields are atoms carrying
**identity only**; jurisdiction, currency, fiscal-year-with-jurisdiction,
and other interpretive constructs do NOT smuggle into atom values. The
catalogue of forbidden smuggling patterns below mirrors the calculator-api
catalogue (api/schemas/invocation.py) and CLAWDOG/110 §3.3.

Lesson #36 anchor: keep the deterministic atom bare in the logic layer;
isolate contextual interpretation in the bridge.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- URI shape validators ------------------------------------------------------
#
# Calculator URI: urn:lodgeit:calculator:<calc>  OR  urn:sbrm:calculator:<calc>:<method>
# Period URI:     urn:sbrm:period:<calc>:<period_id>
#
# Bare period scalars (e.g. "FY26") and bare jurisdiction scalars (e.g. "AU")
# are also accepted as separate first-class parameters.

_CALC_URI_RE = re.compile(
    r"^urn:(?:sbrm|lodgeit):calculator:[a-z0-9_-]+(?::[a-z0-9_-]+)?$"
)
_PERIOD_URI_RE = re.compile(r"^urn:sbrm:period:[a-z0-9_-]+:[a-z0-9_-]+$")
# Bare period scalar shape: FY<digits> | <digits>q<digits> | <digits>-<digits>
_BARE_PERIOD_RE = re.compile(r"^[A-Z]{0,3}\d{2,4}([-/Qq]\d{1,4})?$")
# Bare jurisdiction: 2-letter ISO 3166 alpha-2 (uppercase).
_JURISDICTION_RE = re.compile(r"^[A-Z]{2}$")
# Calculator-version: dotted decimal (1.0, 2.3.4, etc.).
_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")

# Smuggling sentinels — patterns that fuse jurisdiction or currency into an atom.
# Mirrors api/schemas/invocation.py in clawdog-calculator-api.
_SMUGGLING_SENTINELS = (
    re.compile(r"_au_", re.IGNORECASE),
    re.compile(r"_uk_", re.IGNORECASE),
    re.compile(r"_aud_", re.IGNORECASE),
    re.compile(r"_gbp_", re.IGNORECASE),
    re.compile(r"(?:^|[:_/-])au[_-]", re.IGNORECASE),  # "AU_FY26", ":au-fbt"
    re.compile(r"(?:^|[:_/-])uk[_-]", re.IGNORECASE),
    re.compile(r"[_-]au(?:$|[:_/-])", re.IGNORECASE),  # "FY26-AU", "fbt-au:"
    re.compile(r"[_-]uk(?:$|[:_/-])", re.IGNORECASE),
)


def _reject_smuggling(value: str, field_name: str) -> str:
    for pat in _SMUGGLING_SENTINELS:
        if pat.search(value):
            raise ValueError(
                f"{field_name}={value!r} appears to smuggle jurisdiction/currency "
                f"interpretation into an atom (matched {pat.pattern!r}). Pass "
                f"jurisdiction as a separate parameter; keep atoms bare. "
                f"(CLAWDOG/110 §3.3 Non-Negotiable #3 / Lesson #36)"
            )
    return value


class InvokeInput(BaseModel):
    """Input atoms for ``calculator.invoke`` (CLAWDOG/109 §3 + META/005 §3.1).

    The MCP layer validates atom shape; the upstream REST surface validates
    calculator-specific param shapes (FBT et al.). Two-layer validation is
    intentional defence-in-depth, NOT redundant — the MCP layer halts atom
    smuggling before any network egress.
    """

    model_config = ConfigDict(extra="forbid")

    calc: str = Field(..., description="Calculator URI (urn:lodgeit:calculator:<name> or urn:sbrm:calculator:<name>:<method>).")
    version: str = Field(..., description="Calculator version (dotted decimal, e.g. '1.0').")
    params: dict[str, Any] = Field(default_factory=dict, description="Calculator-specific input params; forwarded to REST as-is.")
    period: str = Field(..., description="Period scalar (e.g. 'FY26') OR period URI (urn:sbrm:period:...).")
    jurisdiction: str = Field(..., description="Bare ISO 3166 alpha-2 jurisdiction code (e.g. 'AU').")

    @field_validator("calc")
    @classmethod
    def _validate_calc(cls, v: str) -> str:
        if not _CALC_URI_RE.match(v):
            raise ValueError(
                f"calc={v!r} is not a valid calculator URI shape. "
                f"Expected urn:lodgeit:calculator:<name> or urn:sbrm:calculator:<name>:<method>."
            )
        return _reject_smuggling(v, "calc")

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not _VERSION_RE.match(v):
            raise ValueError(
                f"version={v!r} must be dotted decimal (e.g. '1.0', '2.3.4')."
            )
        return _reject_smuggling(v, "version")

    @field_validator("period")
    @classmethod
    def _validate_period(cls, v: str) -> str:
        # Period accepts either a URI or a bare scalar; both shapes are
        # checked for smuggling. Forbidden: things like "AU_FY26".
        if _PERIOD_URI_RE.match(v):
            return _reject_smuggling(v, "period")
        if _BARE_PERIOD_RE.match(v):
            return _reject_smuggling(v, "period")
        raise ValueError(
            f"period={v!r} must be a bare scalar (e.g. 'FY26', 'FY2026') "
            f"or a period URI (urn:sbrm:period:<calc>:<period_id>). "
            f"Jurisdiction does NOT belong in the period atom; pass it via the "
            f"separate `jurisdiction` parameter."
        )

    @field_validator("jurisdiction")
    @classmethod
    def _validate_jurisdiction(cls, v: str) -> str:
        if not _JURISDICTION_RE.match(v):
            raise ValueError(
                f"jurisdiction={v!r} must be a bare ISO 3166 alpha-2 code (e.g. 'AU', 'UK', 'GB')."
            )
        return v


class DiscoverInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str = Field(..., min_length=1, description="Natural-language intent string; substring-matched against summaries (Phase 3b).")


class ExplainInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invocation_id: str = Field(..., min_length=1, description="The invocation_id returned by a prior calculator.invoke call.")
