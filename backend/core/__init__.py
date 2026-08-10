"""
FinSage AI — deterministic core.

This package is PURE. It contains every rule, rate, threshold and calculation
that produces a rupee figure, and nothing else.

The contract
------------
`backend.core` must not import:

    backend.api, backend.agents, backend.db, backend.services, backend.rag,
    backend.tools, groq, httpx, requests, aiohttp, sqlalchemy, redis, qdrant_client

Enforced two ways, so it holds even in a bare environment:
  1. import-linter contract in `.importlinter` (CI)
  2. `backend/core/tests/test_purity.py`, which walks the AST (always)

Why
---
If the core cannot reach the network, a database or a language model, then it
cannot be non-deterministic. If it is deterministic, it can be exhaustively
tested — which is the only way a tax engine earns trust.

The governing rule of the whole project follows from this:

    No rupee figure shown to a user may originate from a language model.

Everything user-facing that is a number comes from here.

Layout
------
    rules/        versioned FY rule packs (YAML) + loader + section aliases
    tax_engine/   slabs, rebate, surcharge, cess, deductions, capital gains,
                  advance tax, regime comparison, presumptive
    eligibility/  date-windowed rule DSL and evaluator
    costing/      landed cost, GST, stamp duty, depreciation
    provenance/   Money, Citation, Provenance, CalculationTrace, Confidence

Conventions
-----------
* Every public function takes `fy: str` explicitly and NEVER defaults to
  "current". Revised returns and ITR-U (a 48-month window) require prior years.
* Money is `Decimal`. Floats are banned in money paths.
* Every public function returns `(value, trace)`. The trace is not optional and
  not logging — it is the worksheet the user is shown, and it must replay to
  the same value.
"""

__all__ = ["costing", "eligibility", "provenance", "rules", "tax_engine"]
