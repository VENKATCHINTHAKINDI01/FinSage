<!-- GENERATED FILE — do not edit. Source: feature.json -->
<!-- Regenerate: python scripts/gen_progress.py -->

# FinSage AI — Progress

**Generated** 2026-08-20 · **Plan** [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) · **Review** [CODE_REVIEW_2026-08.md](CODE_REVIEW_2026-08.md)

`█████████████████████░░░` **86%** — 65/76 features verified

P0 (release-blocking): **42/47** verified

> Only `verified` — legal basis confirmed against an official source — counts
> toward completion. Nothing user-facing ships below `verified`.

## Phases

| # | Phase | Progress | Features | Gate |
|---|---|---|---|---|
| 0 | **Foundation & guardrails** | `██████████████` 100% | 6/6 | CI green on empty suite; core boundary rule enforced |
| 1 | **Deterministic tax core** | `█████████████░` 93% | 13/14 | All golden tests pass; engine coverage >= 95%; zero tax constants outside core/rules |
| 2 | **Demolition & de-faking** | `█████████████░` 90% | 9/10 | No hardcoded slabs outside core/rules; semantic retrieval verified; p95 < 3s @ 20 concurrent |
| 3 | **Thin agents & orchestration** | `██████████░░░░` 69% | 9/13 | Zero numeric_provenance failures; reviewer catches all seeded omissions; p95 < 4s single-pass informational and < 9s full three-pass review; scheduler jobs run with a real DB session |
| 4 | **Document intelligence** | `██████████████` 100% | 4/4 | Parsers fail loudly on malformed input; reconciliation zero false negatives on seeded set |
| 5 | **Planning features** | `█████████████░` 90% | 9/10 | Golden tests per feature; every output line carries a citation |
| 6 | **Procurement Intelligence** | `██████████████` 100% | 12/12 | EV worked example correct end-to-end; no Tier-3 source in any cost line; all figures dated |
| 7 | **Production readiness** | `██████░░░░░░░░` 43% | 3/7 | Security checklist passed; DPDP controls table published; load test at target concurrency |

## Status

| Status | Count | | Tier | Count |
|---|---|---|---|---|
| ○ `not_started` | 0 | | `P0` | 47 |
| ◐ `in_progress` | 2 | | `P1` | 25 |
| ⊘ `blocked` | 0 | | `P2` | 4 |
| ◑ `implemented` | 4 | |  |  |
| ◕ `tested` | 5 | |  |  |
| ● `verified` | 65 | |  |  |

## Features

### Phase 0 — Foundation & guardrails  ·  6/6

**Gate:** CI green on empty suite; core boundary rule enforced

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ● | `FND-001` | Repository hygiene | P0 | — | 2026-08-09 |
| ● | `FND-002` | feature.json registry + PROGRESS.md generator | P0 | — | 2026-08-09 |
| ● | `FND-003` | CI pipeline | P0 | FND-002 | 2026-08-09 |
| ● | `FND-004` | Core purity boundary rule | P0 | FND-003 | 2026-08-09 |
| ● | `FND-005` | Dependency upgrade and audit | P0 | FND-003 | 2026-08-09 |
| ● | `FND-006` | Agent harness skeleton | P0 | FND-003 | 2026-08-09 |

### Phase 1 — Deterministic tax core  ·  13/14

**Gate:** All golden tests pass; engine coverage >= 95%; zero tax constants outside core/rules

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ● | `CORE-001` | Versioned tax rule packs | P0 | FND-004 | 2026-08-09 |
| ◑ | `CORE-002` | Section alias map (1961 to 2025 Act) | P0 | CORE-001 | — |
| ● | `CORE-003` | Slab engine | P0 | CORE-001 | 2026-08-09 |
| ● | `CORE-004` | Section 87A rebate with marginal relief | P0 | CORE-003 | 2026-08-09 |
| ● | `CORE-005` | Surcharge with marginal relief | P0 | CORE-003 | 2026-08-09 |
| ● | `CORE-006` | Chapter VI-A deductions with correct structures | P0 | CORE-001 | 2026-08-09 |
| ● | `CORE-007` | Capital gains engine | P0 | CORE-003 | 2026-08-09 |
| ● | `CORE-009` | Date-windowed eligibility DSL | P0 | CORE-001 | 2026-08-09 |
| ● | `CORE-010` | Money and Provenance value objects | P0 | CORE-001 | 2026-08-09 |
| ● | `CORE-011` | Golden test corpus | P0 | CORE-003, CORE-004, CORE-005, CORE-006, CORE-007 | 2026-08-09 |
| ● | `CORE-012` | Property-based invariant tests | P0 | CORE-011 | 2026-08-09 |
| ● | `EVD-001` | Calculation trace | P0 | CORE-010 | 2026-08-09 |
| ● | `EVD-002` | Composed confidence model | P0 | EVD-001, CORE-009 | 2026-08-09 |
| ● | `CORE-008` | Presumptive taxation (44AD / 44ADA / 44AE) | P1 | CORE-003 | 2026-08-12 |

### Phase 2 — Demolition & de-faking  ·  9/10

**Gate:** No hardcoded slabs outside core/rules; semantic retrieval verified; p95 < 3s @ 20 concurrent

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ● | `DEM-001` | Remove frontend demo-auth fallback | P0 | — | 2026-08-09 |
| ● | `DEM-002` | Remove mockData page fallbacks | P0 | DEM-001 | 2026-08-09 |
| ● | `DEM-003` | Unify the API client | P0 | — | 2026-08-09 |
| ● | `DEM-004` | Real embeddings and Qdrant re-ingest | P0 | FND-005 | 2026-08-17 |
| ◑ | `DEM-005` | Async LLM client | P0 | — | — |
| ● | `DEM-006` | Delete duplicate tax engines | P0 | CORE-011 | 2026-08-09 |
| ● | `DEM-007` | Remove lifespan DDL; Alembic owns schema | P0 | — | 2026-08-09 |
| ● | `DEM-008` | Stop leaking internal errors | P0 | — | 2026-08-09 |
| ● | `DEM-009` | Honest README | P0 | — | 2026-08-09 |
| ● | `EVD-003` | Purge fabricated confidence scores | P0 | EVD-002, DEM-004 | 2026-08-09 |

### Phase 3 — Thin agents & orchestration  ·  9/13

**Gate:** Zero numeric_provenance failures; reviewer catches all seeded omissions; p95 < 4s single-pass informational and < 9s full three-pass review; scheduler jobs run with a real DB session

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ◐ | `AGT-001` | Thin-agent refactor | P0 | CORE-011, DEM-006 | — |
| ● | `AGT-003` | RequestContext replaces global state | P0 | AGT-001 | 2026-08-09 |
| ● | `AGT-004` | Numeric provenance scorer | P0 | FND-006, AGT-001 | 2026-08-09 |
| ◐ | `AGT-005` | Eval scenario corpus | P0 | AGT-004 | — |
| ● | `AGT-006` | Scope-refusal guardrail | P0 | AGT-005 | 2026-08-09 |
| ● | `AGT-008` | Analyst agent (CA standard) | P0 | AGT-001, AGT-003, CORE-011 | 2026-08-09 |
| ● | `AGT-009` | Reviewer agent — CA file-review pass | P0 | AGT-008, AGT-004 | 2026-08-09 |
| ● | `AGT-011` | Graded review verdicts (block / amend / flag) | P0 | AGT-009 | 2026-08-09 |
| ◕ | `AGT-002` | Parallel orchestration | P1 | AGT-001, DEM-005 | — |
| ● | `AGT-010` | Reviewer agent — assessment risk pass | P1 | AGT-009 | 2026-08-09 |
| ● | `AGT-012` | Answer-time source freshness check | P1 | AGT-009, EVD-004 | 2026-08-12 |
| ● | `EVD-004` | Source archival and access dating | P1 | EVD-002 | 2026-08-12 |
| ◑ | `AGT-007` | Real WebSocket agent streaming | P2 | AGT-002 | — |

### Phase 4 — Document intelligence  ·  4/4

**Gate:** Parsers fail loudly on malformed input; reconciliation zero false negatives on seeded set

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ● | `DOC-004` | Encrypted document vault | P0 | FND-001 | 2026-08-09 |
| ● | `DOC-001` | Form 16 parser and profile autofill | P1 | CORE-011 | 2026-08-17 |
| ● | `DOC-002` | Broker P&L parsers | P1 | CORE-007 | 2026-08-17 |
| ● | `DOC-003` | AIS / TIS reconciliation | P1 | DOC-001, DOC-002 | 2026-08-17 |

### Phase 5 — Planning features  ·  9/10

**Gate:** Golden tests per feature; every output line carries a citation

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ● | `EVD-005` | Evidence and working panel | P1 | EVD-001, EVD-002, EVD-004, PLN-007 | 2026-08-12 |
| ● | `EVD-006` | Downloadable Evidence Pack | P1 | EVD-005, DOC-004 | 2026-08-12 |
| ● | `PLN-001` | Regime comparison with exact breakeven | P1 | CORE-011 | 2026-08-11 |
| ● | `PLN-002` | Advance tax planner with 234B/234C | P1 | CORE-008 | 2026-08-11 |
| ● | `PLN-003` | Capital gains optimiser and tax-loss harvesting | P1 | CORE-007, DOC-002 | 2026-08-11 |
| ● | `PLN-004` | Deterministic ITR form selector | P1 | CORE-008 | 2026-08-11 |
| ● | `PLN-007` | Citation ledger UI | P1 | CORE-010, CORE-002, EVD-001 | 2026-08-12 |
| ● | `EVD-007` | Reproducibility and integrity | P2 | EVD-006 | 2026-08-12 |
| ◕ | `PLN-005` | Profile-derived deadline calendar | P2 | AGT-003 | — |
| ● | `PLN-006` | Salary structuring optimiser | P2 | CORE-006, PLN-001 | 2026-08-11 |

### Phase 6 — Procurement Intelligence  ·  12/12

**Gate:** EV worked example correct end-to-end; no Tier-3 source in any cost line; all figures dated

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ● | `PRC-002` | Tiered source gatherer | P0 | PRC-001 | 2026-08-12 |
| ● | `PRC-004` | Purchase eligibility and subsidy engine | P0 | CORE-009, PRC-002 | 2026-08-13 |
| ● | `PRC-010` | Search admission gate | P0 | PRC-002 | 2026-08-13 |
| ● | `PRC-011` | Cache-first gathering, background sweep | P0 | PRC-010 | 2026-08-13 |
| ● | `PRC-012` | Deterministic page extractors | P0 | PRC-010 | 2026-08-13 |
| ● | `PRC-001` | Item resolver | P1 | AGT-001 | 2026-08-13 |
| ● | `PRC-003` | Landed cost model | P1 | PRC-002, CORE-009 | 2026-08-13 |
| ● | `PRC-005` | Dated signal ledger (timing) | P1 | PRC-003, PRC-004 | 2026-08-13 |
| ● | `PRC-006` | Dealer quote teardown | P1 | PRC-003 | 2026-08-13 |
| ● | `PRC-007` | Property purchase pack | P1 | PRC-003, PRC-004, PRC-011 | 2026-08-13 |
| ● | `PRC-008` | Rewrite price_intelligence agent | P1 | CORE-007, PRC-004 | 2026-08-13 |
| ● | `PRC-009` | SmartSavings and PurchaseAdvisor rebuild | P1 | PRC-003, PRC-004, PRC-005, PRC-006 | 2026-08-13 |

### Phase 7 — Production readiness  ·  3/7

**Gate:** Security checklist passed; DPDP controls table published; load test at target concurrency

| | ID | Feature | Tier | Deps | Verified |
|---|---|---|---|---|---|
| ◕ | `PRD-001` | DPDP Act 2023 compliance | P0 | DOC-004 | 2026-08-13 |
| ● | `PRD-002` | Auth hardening | P0 | DEM-001 | 2026-08-17 |
| ● | `PRD-003` | Rate limiting and abuse controls | P0 | PRD-002 | 2026-08-17 |
| ● | `PRD-005` | Secrets management | P0 | — | 2026-08-13 |
| ◕ | `PRD-004` | Observability | P1 | AGT-003 | 2026-08-13 |
| ◑ | `PRD-006` | Deployment and operations | P1 | PRD-004, PRD-005 | 2026-08-13 |
| ◕ | `PRD-007` | Load and resilience testing | P1 | PRD-006 | 2026-08-17 |

## Ready to start

Not started, with every dependency already verified:

- _None — every unstarted feature is still blocked by a dependency._

---

_FYs supported: 2024-25, 2025-26, 2026-27 · Income-tax Act, 2025 (in force 2026-04-01); Income-tax Act, 1961 for FY <= 2025-26_
