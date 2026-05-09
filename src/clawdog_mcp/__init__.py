"""clawdog-mcp-server — Calculator-Constellation MCP transport adapter (Phase 3b).

This package implements the **MCP surface** of the calculator constellation
defined in CLAWDOG/109, projecting the Phase 3a REST API
(``lodgeit-labs/clawdog-calculator-api``) — and through it, the Phase 2l Prolog
substrate (``lodgeit-labs/LodgeiT_FBT``) — into the Model Context Protocol.

Topology (Standing Rule #7): Egress Interface. No mutable state.

L402 boundary (META/005 §2.2 + §4, ratified 2026-05-09): the REST surface
upstream owns L402 issuance and macaroon-root-key custody; the MCP server is
a transport adapter that forwards ``Authorization`` headers untouched. Phase
3b ships with no L402 enforcement (matches Phase 3a posture).

Advisory boundary (CLAWDOG/110 §3.2): every ``calculator.invoke`` response
carries the upstream advisory block byte-identically; an upstream that omits
it triggers a structured ``advisory_boundary_violation`` error at the MCP
layer.
"""
__version__ = "0.1.0a0"
