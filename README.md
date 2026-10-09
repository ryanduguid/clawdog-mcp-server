# clawdog-mcp-server

**Fork status**

[![Fork code quality](https://app.codacy.com/project/badge/Grade/6f68ee0e138d4d7097ef854679f1f95b?branch=main)](https://app.codacy.com/gh/ryanduguid/clawdog-mcp-server/dashboard)

**Calculator-Constellation MCP Server — stdio transport adapter for the LodgeiT calculator pool (Phase 3b).**

This repository implements the **MCP surface** of the calculator constellation defined in [CLAWDOG/109 — Calculator Constellation](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md). The server exposes three meta-tools (`calculator_discover`, `calculator_invoke`, `calculator_explain`) over stdio, shelling every invocation to the Phase 3a [`clawdog-calculator-api`](https://github.com/lodgeit-labs/clawdog-calculator-api) REST surface — which in turn shells to the Phase 2l Prolog substrate (`lodgeit-labs/LodgeiT_FBT`).

The server is **a transport adapter**, not a calculator engine. No local calculation. No enrichment. The REST response is forwarded byte-identically to the agent client.

> **Topology** (Standing Rule #7): Egress Interface. No mutable state.
>
> **L402 boundary β** (META/005 §2.2 + §4): the REST surface upstream is the L402 issuer; the MCP server forwards `Authorization` headers untouched and never mints, parses, or hashes macaroons. Phase 3b ships with no L402 enforcement (matches Phase 3a posture).
>
> **Advisory boundary** (CLAWDOG/110 §3.2): every `calculator_invoke` response carries the upstream advisory block byte-identically; an upstream that omits it triggers a structured `advisory_boundary_violation` error at the MCP egress.

## Quick start (integrator install)

```bash
# Install from PyPI (or the GitHub repo while pre-release).
pip install clawdog-mcp-server

# Run the stdio MCP server.
clawdog-mcp
# or:
python -m clawdog_mcp
```

### Wire into Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "clawdog": {
      "command": "clawdog-mcp"
    }
  }
}
```

Restart Claude Desktop. The three meta-tools — `calculator_discover`, `calculator_invoke`, `calculator_explain` — appear in the tool palette.

A natural-language query like *"compute FBT car operating cost for a $55,000 vehicle, 75% business use, $200 employee contribution, owned, FY26"* exercises the full round-trip: Claude Desktop → MCP server → REST → Prolog → REST → MCP → Claude Desktop, with the advisory block + content-hash-anchored manifest intact.

## Architectural surfaces

### MCP meta-tools (Phase 3b)

| Tool | Pricing | Implementation |
|---|---|---|
| `calculator_discover` | free | Hardcoded routing table; substring intent → entries. Fano semantic discovery is Phase 3d. |
| `calculator_invoke`   | paid (eventually) | Shells to `clawdog-calculator-api` REST. Response forwarded byte-identically. L402 is REST-side, not MCP-side. |
| `calculator_explain`  | free | In-memory LRU populated by `calculator_invoke`. Cache misses return a structured pointer to the regression-suite root. Prolog-stack traces are Phase 3d. |

### Single supported calculator at Phase 3b

| Calc URI | Version | Surface |
|---|---|---|
| `urn:lodgeit:calculator:fbt` | `1.0` | Fringe Benefits Tax — AU. Statutory Formula and Operating Cost methods (Phase 2l). |

Phase 3c onboards a second calculator. The architecture-correctness test (CLAWDOG/109 §8.3): if onboarding the second calculator requires changing the MCP server, the abstraction has leaked.

### The five binary-failure gates (CI-enforced)

CLAWDOG/110 §3 codifies five non-negotiables; Standing Rule #12 adds a sixth (production-bundle). All five gates ship at commit zero — not retrofit.

| # | Gate | Test file | Anchor lesson |
|---|---|---|---|
| 1 | **Manifest-Fidelity Contract** | `tests/test_manifest_passthrough.py` | Lesson #38 |
| 2 | **Advisory-Boundary Contract** | `tests/test_advisory_boundary.py` | Lesson #34 |
| 3 | **Atom-vs-Bridge Boundary** | `tests/test_atom_boundary.py` | Lesson #36 |
| 4 | **Tools-Manifest Drift Gate** | `make tools-manifest-check` + `tests/test_phase3b_e2e.py` | Lesson #35 |
| 5 | **Standing Rule #1 Inheritance** | `scripts/hooks/pre-push` + `scripts/tests/test_pre_push_hook.sh` | Lesson #39 |
| 6 | **Production Resolver Shape Assertions** | `tests/test_production_bundle.py` | Lesson #40 (Standing Rule #12) |

All gates run on every push to `clawdog/*` and every PR to `main` via [`.github/workflows/ci.yml`](./.github/workflows/ci.yml).

## Local dev

```bash
# One-time: install client-side mechanical enforcement of Standing Rule #1.
make install-hooks

# Install Python deps + dev extras.
pip install -e ".[dev]"

# Lint + run all binary-failure gates locally (CI runs the same).
make ruff
make tools-manifest-check
make test-hooks
make test
```

## What lives where (Phase 3b topology)

```
clawdog-mcp-server/                  ← THIS repo (Egress Interface)
├── src/clawdog_mcp/
│   ├── server.py                    ← FastMCP app factory
│   ├── routing.py                   ← routing-table loader + production resolver
│   ├── rest_client.py               ← httpx forwarder; bearer pass-through
│   ├── schemas.py                   ← pydantic atom-validation (NN#3)
│   ├── manifest.py                  ← passthrough validator + tools-manifest dumper
│   ├── tools/
│   │   ├── discover.py              ← calculator_discover
│   │   ├── invoke.py                ← calculator_invoke (REST-shell + advisory enforcement)
│   │   └── explain.py               ← calculator_explain (LRU lookup)
│   └── config/routing_table.yaml    ← hardcoded routing (1 entry at Phase 3b)
├── tests/                           ← five binary-failure gates + fixtures
├── scripts/hooks/pre-push           ← Standing Rule #1 mechanical enforcement
├── scripts/tests/test_pre_push_hook.sh
├── docs/INTEGRATOR_README.md        ← integrator-onboarding contract
├── tools_manifest.json              ← committed live tools manifest; drift-checked
└── .github/workflows/ci.yml         ← all gates wired
```

## What's deferred (Phase 3c+)

- L402 wiring (REST surface owns issuance per META/005 §4).
- Streamable HTTP transport (stdio is sufficient for Claude Desktop / Cursor / VS Code).
- Fano-backed semantic `calculator_discover`.
- Prolog-stack traces in `calculator_explain`.
- Onboarding the second calculator (the architecture-correctness test).
- Cloud Run deployment of the MCP server.

## Status

Phase 3b commit-zero skeleton. Phase exit captured in [`docs/phase-3b-exit-demonstration.md`](./docs/phase-3b-exit-demonstration.md) once Claude Desktop round-trips an FBT calculation.

— ClawDog ∮
