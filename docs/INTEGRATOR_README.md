# clawdog-mcp-server — Integrator Readiness Pack (Phase 3b)

> **The contract document.** A canonical, externally-publishable description of how to wire a Model Context Protocol (MCP) client (Claude Desktop, Cursor, VS Code agents, Cline, Continue, custom MCP clients) into the LodgeiT calculator constellation through `clawdog-mcp-server`. Adapted from the structure of [`lodgeit-labs/clawdog/docs/INTEGRATOR_README.md`](https://github.com/lodgeit-labs/clawdog/blob/main/docs/INTEGRATOR_README.md) (CLAWDOG/141).

---

## §1 What this is, what it isn't

**clawdog-mcp-server** is a Python MCP server implementing the **MCP surface** of the calculator constellation defined in [CLAWDOG/109](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md). It exposes three meta-tools — `calculator_discover`, `calculator_invoke`, `calculator_explain` — over stdio. Every invocation shells to the Phase 3a [`clawdog-calculator-api`](https://github.com/lodgeit-labs/clawdog-calculator-api) REST surface, which in turn shells to a deterministic SWI-Prolog substrate (`lodgeit-labs/LodgeiT_FBT`).

**It is:**

- A **transport adapter**. Stateless. No local calculation.
- A **boundary enforcement surface** for the advisory block (CLAWDOG/110 §3.2) and atom-vs-bridge discipline (CLAWDOG/110 §3.3).
- A **forwarder of L402 macaroons** — bearer headers pass-through; the REST upstream is the issuer (META/005 §2.2 + §4).

**It is NOT:**

- A calculator engine. The Prolog substrate is the engine.
- A manifest issuer. The REST surface produces manifests; the MCP layer forwards them byte-identically.
- An L402 enforcer. Phase 3b ships with no L402 enforcement (matches Phase 3a posture); enforcement is REST-side when it lands.

## §2 Audience

Wire this into your MCP client if:

- You're an end-user running Claude Desktop / Cursor / VS Code with MCP support and you want LLM-driven natural-language access to deterministic, content-hash-anchored Australian Fringe Benefits Tax calculations.
- You're integrating an agent framework (LangGraph, AutoGen, custom) over MCP and you want a stable, low-trust transport surface to a tax/accounting calculator pool.
- You're evaluating LodgeiT's "operating system for financial truth" wedge, and you want to see what a content-hash-grounded calculator constellation feels like through an LLM client.

This pack is **not** for:

- Implementers extending the calculator pool (Phase 3c onboarding) — those work in `clawdog-calculator-api` (the REST surface) + the calculator engine repos (`LodgeiT_FBT`, `Depreciation_Transforms`, etc.).
- Implementers extending the L402 boundary — that's META/005 / `clawdog-calculator-api` / a future macaroon-mint service.

## §3 The three meta-tools

### 3.1 `calculator_discover(intent: str)`

Free tool. Returns `{"matches": [{"calc", "version", "summary"}, ...]}`.

Phase 3b: substring intent matching against routing-entry summaries. Phase 3d: Fano semantic discovery.

```python
calculator_discover(intent="FBT car operating cost")
# → {"matches": [{"calc": "urn:lodgeit:calculator:fbt", "version": "1.0", "summary": "..."}]}
```

### 3.2 `calculator_invoke(calc, version, params, period, jurisdiction)`

Paid tool **eventually** (META/005 §3.1 — all `compute_*` tools are L402-paid). Phase 3b: no L402 enforcement.

Atoms are bare. **Do not smuggle interpretation:**

- ✅ `period="FY26"`, `jurisdiction="AU"`
- ❌ `period="AU_FY26"` — fails atom-boundary validation
- ❌ `calc="urn:lodgeit:calculator:fbt-au"` — fails atom-boundary validation

The response is **byte-identical** to the upstream REST response, with one MCP-layer addition: a top-level `invocation_id` for `calculator_explain` lookup.

```python
calculator_invoke(
    calc="urn:lodgeit:calculator:fbt",
    version="1.0",
    params={
        "businessUsePercentage": 75,
        "employeeContribution": 200,
        "formOfFinance": "owned",
        "leasePayments": 0,
        "fuelRepairsServicing": 3000,
        "registrationInsurance": 1500,
        "noPrivateUseReduction": 0,
        "acquisitionDate": "2024-04-01",
        "openingDepreciatedValue": 55000,
        "daysHeldInFBTYear": 365
    },
    period="FY26",
    jurisdiction="AU",
)
# → {
#     "taxable_value": 5547.75,
#     "trace": {...},
#     "manifest": {"rate_table_uris": [3 entries with sha256 content_hashes]},
#     "advisory": {"disclaimer": "...", "registered_agent_required": true, ...},
#     "invocation_id": "inv_abc123..."
#   }
```

### 3.3 `calculator_explain(invocation_id: str)`

Free tool. Resolves an invocation_id to its cached payload (in-memory LRU, wiped on server restart). Cache misses return a structured pointer to the regression-suite root rather than fabricating a trace.

Prolog-stack-anchored step-by-step traces are deferred to Phase 3d.

## §4 Boundary enforcement (what the gates protect)

Every `calculator_invoke` response is checked at the MCP egress for:

- **Manifest-fidelity** (CLAWDOG/110 §3.1): `manifest` block byte-identical to REST.
- **Advisory-boundary** (CLAWDOG/110 §3.2): `advisory.disclaimer` is non-empty. An upstream that omits it triggers a structured `advisory_boundary_violation` error with the upstream endpoint URL named in `error.detail`.

Every `calculator_invoke` input is checked for:

- **Atom-vs-bridge** (CLAWDOG/110 §3.3): no jurisdiction/currency smuggling into `calc`, `version`, or `period` atoms.
- **Jurisdiction match**: `jurisdiction` must match the selected route's `advisory_jurisdiction`. A mismatch returns `jurisdiction_mismatch` before any upstream request or invocation-cache entry is created.

## §5 Configuration

| Env var | Purpose | Default |
|---|---|---|
| `MCP_REST_BEARER` | Bearer token forwarded on `Authorization` header to the REST upstream. | unset (REST is currently unauthenticated at Phase 3a) |
| `CLAWDOG_MCP_ROUTING_TABLE` | Override path to the routing-table YAML (test/hermetic only). | packaged path: `clawdog_mcp/config/routing_table.yaml` |

## §6 Status + roadmap

- **Phase 3b** (this release): stdio transport, FBT calculator only, no L402, no Fano discovery, no Prolog-stack traces.
- **Phase 3c**: second calculator onboarding (architecture-correctness test).
- **Phase 3d**: streamable HTTP transport, Fano semantic discovery, Prolog-stack traces, L402 enforcement.

## §7 Reporting issues

Repo: <https://github.com/lodgeit-labs/clawdog-mcp-server>. Issues + PRs welcome. The five non-negotiables (manifest-fidelity, advisory-boundary, atom-vs-bridge, tools-manifest drift, Standing Rule #1) are binary-failure CI gates; PRs that touch the boundary surfaces should keep the gates green.

— ClawDog ∮
