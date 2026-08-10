# FinSage AI

Tax computation and procurement intelligence for India — FY 2026-27 (AY 2027-28), under the Income-tax Act, 2025.

> **Status: under active reconstruction.** This README describes what the code
> actually does today. Anything not listed as working is not built yet, and is
> tracked in [`PROGRESS.md`](PROGRESS.md) against [`feature.json`](feature.json).
>
> The previous README claimed LangGraph orchestration, a RAG knowledge base,
> live tax-data fetching and DPDP compliance. None of those existed. Overclaiming
> in a tax product is not marketing, it is the same failure as a wrong number.

---

## The one rule everything follows

> **No rupee figure shown to a user may originate from a language model.**

Every number is computed by deterministic Python in `backend/core/` from
versioned rule packs, and carries a trace back to the rule, the section, the
financial year and the source. The LLM's only jobs are to understand the
question, extract structure from unstructured input, and explain numbers that
code produced.

This is enforced mechanically, not by convention. `backend/evals/scorers/numeric_provenance.py`
extracts every number from an agent's output and fails CI if it does not appear
in the tool results that agent received.

---

## What works today

| Area | State |
|---|---|
| **Deterministic tax engine** | ✅ Slabs, s.87A rebate with marginal relief, surcharge with marginal relief, cess, Chapter VI-A, capital gains (111A / 112A / 112), both regimes, all age bands |
| **Rule packs** | ✅ FY 2024-25, 2025-26, 2026-27 as versioned YAML. No default year, no fallback |
| **Eligibility engine** | ✅ Date-windowed rules returning `ELIGIBLE` / `INELIGIBLE` / `WINDOW_CLOSED` / `INSUFFICIENT_DATA` |
| **Calculation trace** | ✅ Every computation returns a worksheet that must replay to the same value |
| **Confidence model** | ✅ Composed from input provenance, rule freshness, completeness, assumptions and source tier |
| **Test harness** | ✅ 347 tests, 97% coverage on `backend/core`, golden corpus + Hypothesis invariants + agent eval replay |
| **Auth** | ⚠️ JWT works. Hardening (revocation, refresh rotation, httpOnly) is PRD-002, not done |
| **Agents** | 🚧 Being rebuilt as Analyst + Reviewer over the deterministic core (phase 3) |
| **RAG** | 🚧 Embeddings are still `md5 → random vector`. Real embeddings are DEM-004, not done |
| **Document parsing** | ❌ Form 16, broker P&L and AIS parsers are phase 4 |
| **Procurement advisor** | ❌ Phase 6. The existing UI shell posts to the generic chat endpoint |
| **DPDP compliance** | ❌ Phase 7. Not claimed until the controls exist |

---

## Architecture

```
frontend/          React 19 + Vite · one API client · no mock fallbacks
    │
backend/api/       FastAPI
backend/agents/    explain only — no arithmetic authority
backend/tools/     thin adapters; carry no tax knowledge
    │
backend/core/      PURE. No LLM, no network, no database. 97% covered.
    rules/         versioned FY packs + 1961→2025 section aliases
    tax_engine/    slabs · rebate · surcharge · deductions · capital gains
    eligibility/   date-windowed rule DSL
    provenance/    Money (Decimal) · Citation · Trace · Confidence
```

`backend/core` may not import `api`, `agents`, `db`, `groq`, `httpx` or
`sqlalchemy`. Enforced by an import-linter contract and an AST test, so it holds
even in a bare checkout. If the core cannot reach the network, it cannot be
non-deterministic; if it is deterministic, it can be exhaustively tested.

---

## Quick start

```bash
python3 -m venv senv && source senv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp env.example .env      # fill in GROQ_API_KEY, POSTGRES_URL, JWT_SECRET_KEY

./scripts/phase_gate.sh  # registry, lint, boundaries, all four test layers
```

The core engine needs no services — try it directly:

```python
from backend.core.provenance import rupees
from backend.core.tax_engine import TaxInput, compute_tax

r = compute_tax(TaxInput(fy="2026-27", regime="new", salary=rupees(1_275_000), age=34))
print(r.total_tax)      # ₹0
print(r.trace.render()) # the worksheet, line by line
```

Full stack:

```bash
docker-compose up -d
uvicorn backend.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

---

## Working on this

`feature.json` is the source of truth for what exists. `PROGRESS.md` is
generated from it — never hand-edit it.

```bash
python scripts/gen_progress.py            # regenerate
python scripts/gen_progress.py --check    # CI: fail if stale or invalid
python scripts/verify_freshness.py        # CI: fail if a tax rule has decayed
./scripts/phase_gate.sh                   # the full local gate
```

A feature counts as complete only at status `verified` — meaning its legal basis
was confirmed against an official source, with the date recorded. Anything below
that is work in flight.

**Tax rules are perishable.** `verify_freshness.py` fails the build when a rule
pack backing a shipped feature is more than 180 days past its last verification.
The previous version of this codebase was two years stale in seven files at once,
with nothing anywhere objecting.

### Adding a financial year

One new `backend/core/rules/fy_YYYY_YY.yaml` and one golden-test file. No Python
changes — rules are data.

---

## Testing

Four layers, each a CI gate:

| Layer | What it proves | Where |
|---|---|---|
| 1 · Golden | Specific verified numbers, every case citing where it was checked | `backend/core/tests/golden/` |
| 2 · Property | Invariants over all inputs — monotonicity, marginal relief bounds, trace replay | `backend/core/tests/properties/` |
| 3 · Evals | Agents faithfully report what the tools returned | `backend/evals/` |
| 4 · Contract | API shape, migrations, load | `tests/` (phase 7) |

Layer 2 earns its keep. The naive invariant "post-tax income is monotonic in
income" fails at ₹50L, ₹1cr and ₹2cr — not because of a bug, but because cess
applies *after* marginal relief, so the all-in marginal rate inside a relief zone
is exactly 104%. The suite asserts what relief actually guarantees.

---

## Known limitations

- Section citations for FY 2026-27 render the 1961 numbering as primary. The
  1961 → 2025 map is loaded but **unverified** against the published concordance,
  so new-Act numbers are shown as provisional rather than asserted (CORE-002).
- Presumptive taxation (44AD / 44ADA) is in the rule packs; the engine is not
  built (CORE-008).
- Agents still make blocking synchronous LLM calls (DEM-005).
- This is not tax advice. It is a computation tool with its working shown, built
  so a chartered accountant can check it.

---

## Licence

MIT — see `LICENSE`.
