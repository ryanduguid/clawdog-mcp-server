#!/bin/sh
# Binary-failure verification of scripts/hooks/pre-push (Standing Rule #1
# mechanical enforcement). Each case asserts the documented exit-code contract:
#
#   0  🟢 CLEAN
#   1  🔴 RULE #1 VIOLATION
#   2  🟡 INFRA BROKEN
#
# Per Lesson #35: the discipline lives in the tool, and the tool itself needs
# a binary-failure test that proves each exit code fires in reality. This is
# that test. Wired into Makefile::test-hooks.
#
# Run from anywhere inside the repo (uses git rev-parse to find root).

set -u

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    echo "test-hooks: not inside a git working tree" >&2
    exit 2
fi

HOOK="$REPO_ROOT/scripts/hooks/pre-push"

if [ ! -x "$HOOK" ]; then
    echo "test-hooks: hook missing or not executable: $HOOK" >&2
    exit 2
fi

# Each case feeds canned stdin (the git pre-push protocol) and asserts exit code.
fail_count=0
pass_count=0

check () {
    expected="$1"
    label="$2"
    stdin="$3"
    env_overrides="$4"

    if [ -n "$env_overrides" ]; then
        # shellcheck disable=SC2086
        actual=$(env $env_overrides "$HOOK" <<EOF 2>/dev/null
$stdin
EOF
)
        actual_rc=$?
    else
        actual=$("$HOOK" <<EOF 2>/dev/null
$stdin
EOF
)
        actual_rc=$?
    fi
    : "$actual"  # quiet shellcheck about unused capture; we only care about rc

    if [ "$actual_rc" = "$expected" ]; then
        printf '  PASS  [exit=%s]  %s\n' "$actual_rc" "$label"
        pass_count=$((pass_count + 1))
    else
        printf '  FAIL  [expected=%s actual=%s]  %s\n' "$expected" "$actual_rc" "$label"
        fail_count=$((fail_count + 1))
    fi
}

echo "==========================================================================="
echo "PRE-PUSH HOOK BINARY-FAILURE TEST (Standing Rule #1 mechanical boundary)"
echo "==========================================================================="
echo

# Case 1: feature branch push — exit 0.
check 0 "feature branch push (refs/heads/feature/foo) → 0" \
    "refs/heads/feature/foo abc123 refs/heads/feature/foo def456" \
    ""

# Case 2: master push — exit 1.
check 1 "master push (refs/heads/master) → 1" \
    "refs/heads/master abc123 refs/heads/master def456" \
    ""

# Case 3: main push — exit 1.
check 1 "main push (refs/heads/main) → 1" \
    "refs/heads/main abc123 refs/heads/main def456" \
    ""

# Case 4: empty stdin (no refs being pushed) — exit 0.
check 0 "empty stdin (no refs being pushed) → 0" \
    "" \
    ""

# Case 5: configurable protected refs honoured (refs/heads/release blocked).
check 1 "configurable protected ref (refs/heads/release with override) → 1" \
    "refs/heads/release abc123 refs/heads/release def456" \
    "CLAWDOG_PRE_PUSH_PROTECTED_REFS=refs/heads/release"

# Case 6: configurable protected refs honoured (master allowed when override drops it).
check 0 "configurable override drops master (only release blocked) → 0 for master" \
    "refs/heads/master abc123 refs/heads/master def456" \
    "CLAWDOG_PRE_PUSH_PROTECTED_REFS=refs/heads/release"

# Case 7: mixed batch (one feature + one master in the same push) — exit 1
# (any protected violation in a batch halts the push).
check 1 "mixed-batch push (feature + master in same stdin) → 1" \
    "refs/heads/feature/foo abc123 refs/heads/feature/foo def456
refs/heads/master abc123 refs/heads/master def456" \
    ""

echo
echo "---------------------------------------------------------------------------"
printf 'Results: %d pass, %d fail\n' "$pass_count" "$fail_count"
echo "---------------------------------------------------------------------------"

if [ "$fail_count" -ne 0 ]; then
    exit 1
fi

exit 0
