# Makefile for clawdog-mcp-server (Phase 3b Egress Interface).
#
# Targets that subagents MAY run (pure read / static-import operations):
#   make tools-manifest        regenerate tools_manifest.json from the live FastMCP app
#   make tools-manifest-check  assert committed tools_manifest.json matches live introspection
#   make ruff                  lint
#   make install-hooks         symlink scripts/hooks/pre-push into .git/hooks/
#                              (DISCIPLINE FROM COMMIT ZERO — Lesson #39)
#   make test-hooks            binary-failure self-test of the pre-push hook
#
# Targets Andrew runs locally:
#   make test                  pytest tests/  (also runs in CI)
#   make run                   python -m clawdog_mcp  (stdio MCP server)
#
# Standing Rule #4: Cloud Run lives in australia-southeast1; HTTP transport
# deferred to Phase 3d. This server is stdio-only at Phase 3b.

PYTHON ?= python3
VENV   ?= .venv
PIP    ?= $(VENV)/bin/pip
PY     ?= $(VENV)/bin/python
PYTEST ?= $(VENV)/bin/pytest
RUFF   ?= $(VENV)/bin/ruff

.PHONY: help venv install test ruff tools-manifest tools-manifest-check \
        run install-hooks test-hooks clean

help:
	@echo "clawdog-mcp-server — Phase 3b Egress Interface"
	@echo ""
	@echo "Author-side (subagent-safe):"
	@echo "  make install-hooks         install scripts/hooks/pre-push (Standing Rule #1)"
	@echo "  make test-hooks            binary-failure self-test of the pre-push hook"
	@echo "  make tools-manifest        regenerate tools_manifest.json from live FastMCP"
	@echo "  make tools-manifest-check  assert committed tools_manifest.json matches live"
	@echo "  make ruff                  lint"
	@echo ""
	@echo "Andrew-side:"
	@echo "  make test                  pytest tests/  (5 binary-failure gates)"
	@echo "  make run                   python -m clawdog_mcp (stdio MCP server)"

venv:
	@if [ ! -x "$(PY)" ]; then $(PYTHON) -m venv $(VENV); fi

install: venv
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST) tests/

ruff:
	$(RUFF) check src tests

# `make tools-manifest` is a STATIC IMPORT operation — imports the FastMCP
# app and serialises its list_tools() output. No network, no stdio loop.
# Subagents MAY run this; CI runs it as part of the drift-gate.
tools-manifest:
	$(PY) -c "import json, asyncio; \
from clawdog_mcp.server import build_app; \
from clawdog_mcp.manifest import dump_tools_manifest; \
data = json.dumps(asyncio.run(dump_tools_manifest(build_app())), indent=2, sort_keys=True) + '\n'; \
open('tools_manifest.json', 'w').write(data)"
	@echo "tools_manifest.json regenerated."

tools-manifest-check:
	$(PY) -c "import json, asyncio, sys, pathlib; \
from clawdog_mcp.server import build_app; \
from clawdog_mcp.manifest import dump_tools_manifest; \
generated = json.dumps(asyncio.run(dump_tools_manifest(build_app())), indent=2, sort_keys=True) + '\n'; \
committed = pathlib.Path('tools_manifest.json').read_text(); \
sys.exit(0 if generated == committed else (print('Tools-manifest drift; run make tools-manifest', file=sys.stderr), 1)[1])"

# Standing Rule #1 mechanical enforcement (Lesson #39 — DISCIPLINE FROM COMMIT
# ZERO). Symlink the pre-push hook into .git/hooks/ so any push to
# refs/heads/master or refs/heads/main halts with a loud, named violation.
install-hooks:
	@if [ ! -d .git ]; then \
		echo "not a git working tree; nothing to install."; exit 1; \
	fi
	@mkdir -p .git/hooks
	@ln -sf ../../scripts/hooks/pre-push .git/hooks/pre-push
	@chmod +x scripts/hooks/pre-push
	@echo "✓ pre-push hook installed."
	@echo "  Standing Rule #1 is now mechanically enforced: pushes to master/main"
	@echo "  will halt. Bypass with 'git push --no-verify' (deliberate-override only)."

test-hooks:
	@chmod +x scripts/tests/test_pre_push_hook.sh scripts/hooks/pre-push
	@scripts/tests/test_pre_push_hook.sh

run:
	$(PY) -m clawdog_mcp

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache **/__pycache__ \
	       *.egg-info build dist
