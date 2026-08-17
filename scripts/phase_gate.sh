#!/usr/bin/env bash
# Run the full phase gate locally, exactly as CI does.
#
#   ./scripts/phase_gate.sh
#
# CI is the enforcer, but a gate you can only run in CI is a gate you find out
# about twenty minutes late. This runs the same checks in the same order.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

export PYTHONPATH=.
export PATH="$HOME/.local/bin:$PATH"

fail=0
run() {
  local name=$1; shift
  printf '\n\033[1m════ %s ════\033[0m\n' "$name"
  if "$@"; then
    printf '  \033[32m✓ pass\033[0m\n'
  else
    printf '  \033[31m✗ FAIL\033[0m\n'
    fail=1
  fi
}

# 1–2. The registry is the source of truth; if it is inconsistent or its tax
#      rules have decayed, nothing downstream is trustworthy.
run "Registry schema + invariants"  python3 scripts/gen_progress.py --check
run "Tax rule freshness gate"       python3 scripts/verify_freshness.py

# 3–4. Style, then architecture. The core-purity contract is the load-bearing
#      one: if backend/core can reach the network, a DB or an LLM, it is no
#      longer deterministic and no longer exhaustively testable.
run "Ruff lint"                     python3 -m ruff check backend/core backend/evals backend/llm backend/middleware backend/rag/embeddings.py backend/tools/calculation.py backend/tools/tests \
  backend/agents/analyst.py backend/agents/reviewer_ca.py backend/agents/review_protocol.py \
  backend/agents/pipeline.py backend/agents/reviewer_risk.py backend/agents/tests \
  backend/context.py backend/orchestrator/parallel.py backend/orchestrator/__init__.py \
  backend/tests/test_context_and_parallel.py backend/tests/test_websocket_auth.py backend/services/parsers backend/services/tests backend/evidence backend/procurement backend/security backend/middleware backend/compliance backend/observability backend/services/evidence_pack_pdf.py backend/vault scripts --output-format=text
run "Security & abuse controls"     python3 -m pytest backend/security/tests backend/middleware/tests -q
run "DPDP & log redaction"          python3 -m pytest backend/compliance backend/observability -q
run "Import boundaries"             bash -c 'lint-imports --config .importlinter > /dev/null'

# 5. Layers 1 and 2 — purity, golden cases, property invariants.
run "Core tests"                    python3 -m pytest backend/core/tests -q --no-header
run "RAG embedding contract"        python3 -m pytest backend/rag/tests -q --no-header
run "Analyst/Reviewer pipeline"     python3 -m pytest backend/agents/tests -q --no-header
run "Context & orchestration"       python3 -m pytest backend/tests/test_context_and_parallel.py -q --no-header
run "WebSocket auth"                python3 -m pytest backend/tests/test_websocket_auth.py -q --no-header
run "Document parsers"              python3 -m pytest backend/services/parsers/tests -q --no-header
run "Evidence pack rendering"       python3 -m pytest backend/services/tests -q --no-header
run "Source archive & freshness"    python3 -m pytest backend/evidence/tests -q --no-header

# The frontend suite. EVD-005 and PLN-007 sat at `tested` rather than
# `verified` purely because there was no runner; their first execution
# found a crash on a malformed source URL that review had missed twice.
run "Frontend components"           bash -c 'cd frontend && npm test --silent'
run "Document vault"                python3 -m pytest backend/vault/tests -q --no-header
run "Engine/agent boundary"         python3 -m pytest backend/tools/tests -q --no-header

# 6–7. Layer 3 — the harness tests itself, then replays the suite offline.
run "Eval harness self-tests"       python3 -m pytest backend/evals/tests -q --no-header
run "Eval suite replay"             bash -c 'python3 -m backend.evals.runner > /dev/null'

printf '\n════════════════════════════════\n'
if [ $fail -eq 0 ]; then
  printf '\033[32mPHASE GATE: GREEN\033[0m\n'
else
  printf '\033[31mPHASE GATE: RED\033[0m\n'
fi
exit $fail
