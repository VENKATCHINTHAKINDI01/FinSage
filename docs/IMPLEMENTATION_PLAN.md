# FinSage AI — End-to-End Implementation Plan

**Version** 1.0 · **Created** 9 August 2026 · **Target** FY 2026-27 (AY 2027-28), production deployment for real Indian taxpayers

---

## 0. Decisions locked

| Decision | Choice | Consequence |
|---|---|---|
| Agent architecture | **Hybrid** — deterministic core + thin agents | All math moves to a pure, tested `tax_engine` package. The 12 agents survive as parallel explanation wrappers with zero arithmetic authority. |
| Intended use | **Real users, will deploy** | Full DPDP build-out, encrypted document storage, secrets management, rate limiting, observability, revocation-checked auth. |
| Features in scope | **All Tier-1 + Purchase Advisor** | Form 16 parser, regime comparison, advance tax, capital gains + harvesting, AIS/TIS reconciliation, and a new Procurement Intelligence engine. |
| Legacy code | **Delete freely** | Demo auth, mockData fallbacks, fake embeddings, duplicate engines, dead API client, unused celery/rq all removed. Git history is the safety net. |

---

## 1. The governing principle

> **No rupee figure shown to a user may originate from a language model.**

Every number is computed by deterministic Python from a versioned rule pack, and carries a provenance record back to `(rule_id, section, financial_year, source_url, computed_at)`. The LLM's only jobs are: (a) understand what the user asked, (b) extract structured facts from unstructured input, (c) explain numbers that code produced.

This single rule resolves most of what's wrong with the current build, and it's the difference between a demo and something a person can hand to their CA.

**Enforcement is mechanical, not cultural.** The agent harness includes a *numeric provenance check*: it extracts every number from an agent's user-facing output and fails the test if that number does not appear in the tool-result payload the agent received. You cannot merge a hallucinated rupee amount.

---

## 2. Target architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  React 19 + Vite  ·  single API client  ·  no mock fallbacks     │
└───────────────────────────┬──────────────────────────────────────┘
                            │ REST (relative /api) + WS
┌───────────────────────────▼──────────────────────────────────────┐
│  FastAPI  ·  RequestContext(db, user, fy, tools)  — no globals   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────▼───────────────────┐
        │   Orchestrator (asyncio.gather)       │
        │   intent → N thin agents in parallel  │
        └───────────────────┬───────────────────┘
                            │  agents may only EXPLAIN
        ┌───────────────────▼───────────────────┐
        │   ToolExecutor  (~45 tools)           │
        └───────────────────┬───────────────────┘
                            │  every tool delegates to:
┌───────────────────────────▼──────────────────────────────────────┐
│  backend/core/   ← PURE. No LLM. No network. No DB. 100% tested. │
│                                                                   │
│  rules/        fy_2024_25.yaml … fy_2026_27.yaml, aliases.yaml   │
│  tax_engine/   slabs · rebate · surcharge+relief · cess ·        │
│                deductions · capital_gains · advance_tax ·         │
│                regime_compare · presumptive                       │
│  eligibility/  date-windowed rule DSL (fixes the 80EEB trap)     │
│  costing/      landed_cost · gst · stamp_duty · depreciation     │
│  provenance/   Money, Citation, Provenance value objects          │
└───────────────────────────────────────────────────────────────────┘
```

**`backend/core/` has no imports from `backend/api`, `backend/agents`, `backend/db`, `groq`, or `httpx`.** This is enforced by an import-linter rule in CI. If the core can't reach the network, it can't be non-deterministic, and if it's deterministic it can be exhaustively tested.

### 2.1 Rule packs

```yaml
# backend/core/rules/fy_2026_27.yaml
meta:
  financial_year: "2026-27"
  assessment_year: "2027-28"
  effective_from: "2026-04-01"
  effective_to:   "2027-03-31"
  governing_act:  "Income-tax Act, 2025"
  verified_on:    "2026-08-09"
  sources:
    - https://www.incometax.gov.in/

regimes:
  new:
    slabs:
      - {upto: 400000,  rate: 0.00}
      - {upto: 800000,  rate: 0.05}
      - {upto: 1200000, rate: 0.10}
      - {upto: 1600000, rate: 0.15}
      - {upto: 2000000, rate: 0.20}
      - {upto: 2400000, rate: 0.25}
      - {upto: null,    rate: 0.30}
    rebate_87a: {max_taxable: 1200000, max_rebate: 60000, marginal_relief: true,
                 excludes: [111A, 112A]}
    standard_deduction_salary: 75000
    surcharge_cap: 0.25
    allowed_deductions: [80CCD_2, 80JJAA, 57_iia, standard_deduction_salary]
  old:
    slabs: [{upto: 250000, rate: 0.0}, {upto: 500000, rate: 0.05},
            {upto: 1000000, rate: 0.20}, {upto: null, rate: 0.30}]
    slabs_senior:       # 60–79
      - {upto: 300000, rate: 0.0} …
    slabs_super_senior: # 80+
      - {upto: 500000, rate: 0.0} …
    rebate_87a: {max_taxable: 500000, max_rebate: 12500, marginal_relief: true}
    standard_deduction_salary: 50000
    surcharge_cap: 0.37
```

Rules are **data, not code**. Adding FY 2027-28 after the next Budget is one new YAML file plus one golden-test file — no Python changes. Every engine function takes `fy: str` explicitly and **never** defaults to "current", because revised returns and ITR-U (now a 48-month window) require computing prior years correctly.

### 2.2 The eligibility DSL — why this exists

The current code would happily tell a user buying an EV today that they can claim ₹1.5 lakh under 80EEB. They cannot: **80EEB requires the loan to have been sanctioned between 1 Jan 2019 and 31 Mar 2023.** The window closed three years ago.

This class of bug — a benefit that exists in the statute but is closed to this user on this date — is the most common and most damaging error in Indian tax software. It gets its own subsystem:

```yaml
- id: 80EEB
  name: Interest on electric vehicle loan
  max_deduction: 150000
  regimes: [old]
  windows:
    - field: loan_sanction_date
      from: "2019-01-01"
      to:   "2023-03-31"
  conditions:
    - {field: asset_type, equals: electric_vehicle}
    - {field: taxpayer_type, in: [individual]}
  once_per: lifetime_per_vehicle
  citation: {act: "Income-tax Act, 2025", legacy_section: "80EEB"}
```

The evaluator returns one of `ELIGIBLE` / `INELIGIBLE(reason)` / `WINDOW_CLOSED(closed_on)` / `INSUFFICIENT_DATA(missing_fields)`. **`WINDOW_CLOSED` is surfaced to the user as an explicit line**, not hidden — "80EEB would have given you ₹1.5L, but the sanction window closed 31 Mar 2023" is more trustworthy than silence, and it's the kind of thing that makes people believe the rest of your output.

Same machinery covers 80EEA, 80EE, PM E-DRIVE deadlines, state EV policy windows, SGB availability, and every scheme in `schemes_search.py`.

---

## 3. The agent harness

Four layers, each with a CI gate.

### Layer 1 — Golden tax tests (deterministic, no LLM, no network)

```
backend/core/tests/golden/
  fy_2026_27/
    salaried_basic.yaml        # 40+ cases
    capital_gains.yaml
    surcharge_marginal_relief.yaml
    regime_comparison.yaml
  fy_2025_26/ …
```

```yaml
- id: NR-2026-REBATE-BOUNDARY
  fy: "2026-27"
  regime: new
  input: {salary: 1275000, age: 34}
  expect:
    standard_deduction: 75000
    taxable_income: 1200000
    tax_before_rebate: 60000
    rebate_87a: 60000
    total_tax: 0
  verified_against: "incometax.gov.in tax calculator, 2026-08-09"
```

Every case cites where the expected value was verified. Boundary cases are mandatory: ₹12,00,000 and ₹12,00,001 (marginal relief), ₹50,00,000 and ₹50,00,001 (surcharge relief), ₹1,25,000 LTCG exemption edge, age 59/60/79/80.

**Gate: 100% pass. No exceptions, no skips.**

### Layer 2 — Property tests

Invariants that must hold for *all* inputs, via Hypothesis:

- Tax is monotonically non-decreasing in income.
- Post-tax income is monotonically non-decreasing in income (**this is what marginal relief guarantees** — it's how you catch cliff bugs automatically).
- Adding a valid deduction never increases tax.
- `old_regime_tax(x, no deductions) ≥ new_regime_tax(x, no deductions)` above the crossover.
- Tax on ₹0 is ₹0; no negative tax anywhere.

### Layer 3 — Agent evaluation harness

```
backend/evals/
  scenarios/          # YAML: user query + profile + expected behaviour
  runner.py           # executes against live or recorded LLM
  scorers/
    numeric_provenance.py   # ← every number traceable to a tool result
    citation_validity.py    # cited sections exist in the FY rule pack
    window_awareness.py     # closed windows are stated, not silently dropped
    refusal.py              # out-of-scope → declines, no SEBI advice
    latency_cost.py
  fixtures/           # recorded LLM responses for deterministic replay
  baseline.json       # last accepted scores; CI fails on regression
```

Example scenario:

```yaml
id: EV-80EEB-CLOSED-WINDOW
query: "I'm buying an electric car next month with a loan. What tax benefit do I get?"
profile: {fy: "2026-27", regime: new, salary: 1800000}
must_state:
  - window_closed: 80EEB
  - gst_rate_ev: 0.05
must_not_claim:
  - deduction: 80EEB
  - any_rupee_figure_absent_from_tool_output: true
max_latency_ms: 4000
```

`fixtures/` means the whole suite replays offline and deterministically in CI. A nightly job runs it live against Groq to catch model drift.

**Gate: no regression vs `baseline.json`; zero `numeric_provenance` failures.**

### Layer 4 — Contract & integration tests

Schemathesis against the OpenAPI spec, Alembic up/down round-trip on a scratch DB, Testcontainers for Postgres/Redis/Qdrant, k6 smoke load test asserting p95 latency (this is what catches the sync-Groq event-loop block).

---

## 4. `feature.json` and `PROGRESS.md`

`feature.json` at repo root is the **single machine-readable source of truth** for what exists, what it depends on, what proves it works, and when its legal basis was last verified. `PROGRESS.md` is generated from it by `scripts/gen_progress.py` — never hand-edited.

Key fields per feature: `id`, `phase`, `tier`, `status`, `depends_on`, `acceptance_criteria`, `deterministic`, `llm_involved`, `rules_refs`, `legal_refs`, `sources`, `endpoints`, `files`, `tests`, `risk`, `last_verified`.

Two fields carry unusual weight for a tax product:

- **`last_verified`** — the date a human confirmed the feature's legal basis against an official source. A `verify_freshness.py` CI job **fails the build** when any tax-rule feature has `last_verified` older than 180 days. Stale tax rules are the failure mode that killed the current build; this makes staleness impossible to ignore.
- **`deterministic` / `llm_involved`** — a CI check asserts no feature is simultaneously `"deterministic": true` and `"llm_involved": true` in its calculation path.

Status vocabulary: `not_started` → `in_progress` → `blocked` → `implemented` → `tested` → **`verified`** (legal basis confirmed against an official source). Only `verified` counts toward the completion percentage. Nothing user-facing ships below `verified`.

---

## 5. Procurement Intelligence (the Purchase Advisor)

You asked for something that researches what a user wants to buy across the internet and official sources, surfaces every cost lever and policy, and advises on timing. Here's how it gets built honestly.

### 5.1 What exists today

`SmartSavings.tsx` + `PurchaseAdvisorChat.tsx` are a frontend-only question flow (category detection, scripted questions, verdict card) that posts to the generic `/chat/query`. There is no backend engine. `price_intelligence.py` has a CII table and hardcoded yield assumptions — and it currently **recommends buying Sovereign Gold Bonds, which the government stopped issuing in February 2024.** The UX shell is decent and worth keeping; everything behind it gets built new.

### 5.2 Five-stage pipeline

```
① RESOLVE   free text → structured Item(category, subcategory, specs, HSN,
                        state, use_case, financing, budget)
② GATHER    tiered source fan-out → normalised evidence, each with URL+date
③ COST      deterministic landed-cost model (pure, tested, no LLM)
④ ELIGIBLE  date-windowed eligibility engine → benefits, subsidies, deductions
⑤ TIME      dated policy/seasonal signal analysis → not a prediction
```

### 5.3 Source tiering — the trust rule

| Tier | Sources | May drive a number? |
|---|---|---|
| **1 — Official** | cbic.gov.in (GST/HSN, customs), incometax.gov.in, parivahan.gov.in & state transport (road tax/registration), heavyindustries.gov.in (PM E-DRIVE), state EV/industrial policy portals, state IGR/stamp-duty & circle-rate portals, state RERA, RBI, IBJA (gold rates), BIS | ✅ Yes |
| **2 — Primary commercial** | OEM official price lists, manufacturer spec sheets, official dealer quote uploaded by the user, bank/NBFC published rate cards | ✅ Yes, labelled "manufacturer-stated" |
| **3 — Aggregator/editorial** | Marketplaces, review sites, news | ❌ Indicative only, must render with a visible "unverified" badge |

**A Tier-3 source can never produce a figure in the cost breakdown.** It can only add context. This is the same discipline as §1, applied to procurement.

### 5.4 Honest constraints — read this before expecting otherwise

Three things I will not pretend to deliver:

1. **Live retail price scraping is out.** Amazon/Flipkart/dealer sites are JS-rendered, anti-bot, and scraping them generally violates their terms. What we do instead: official OEM price lists, government price portals where they exist, IBJA gold rates, and **user-uploaded quotes** — the user pastes or photographs a dealer quotation and we tear it apart line by line. That last one is more valuable anyway, because it's *their actual price*, and dealer quotations are where the padding hides.

2. **"When to buy" is not a forecast.** Nobody can predict gold or property prices, and a product that implies it can is doing harm. What we deliver is a **dated signal ledger** — every signal is a fact with a date and a source:
   - Policy cliffs: *PM E-DRIVE e-2W demand incentive terminates 31 Jul 2026* — that's ₹5,000 that disappears on a known date.
   - GST rate-change effective dates.
   - Financial-year boundaries (31 March) for depreciation — buying a business asset on 31 Mar vs 1 Apr shifts a full year of depreciation, and if used <180 days you get half rate. Purely deterministic, genuinely worth thousands.
   - Model-year and festive cycles, stated as observed patterns with the years observed.
   - Budget dates for duty changes.

   The output is *"here are the dated facts that change your cost, and by how much"* — never *"prices will rise."*

3. **Property gets extra restraint.** We compute stamp duty, registration, circle-rate/guidance-value floor, GST on under-construction, RERA registration status, home-loan interest deductibility, and women-buyer concessions. We do **not** opine on whether a locality will appreciate. That's SEBI/RERA-adjacent advice and outside what this product should say.

### 5.5 The landed-cost model (deterministic, `backend/core/costing/`)

```
ex_showroom / base_price
  + GST            (correct 2.0 slab by HSN: 0 / 5 / 18 / 40)
  + compensation cess          (where applicable)
  + customs duty               (imports)
  + road tax & registration    (state-specific, vehicle)
  + stamp duty & registration  (state-specific, property)
  + insurance, logistics, installation, extended warranty
  − central subsidy            (eligibility-gated, date-windowed)
  − state subsidy              (eligibility-gated, date-windowed)
  − manufacturer/dealer discount, exchange bonus
  − GST input tax credit       (if GST-registered and business use)
  − income-tax effect          (depreciation / 44AD / 44ADA / deduction)
  ─────────────────────────────────────────────
  = TRUE LANDED COST  +  effective post-tax cost
  +  finance cost     (if loan: total interest, APR, prepayment position)
```

Worked example the engine must get right — EV car, ₹18L ex-showroom, Maharashtra, salaried, new regime, loan today:

- GST **5%** (not 18%, not 28% — EVs are 5% under GST 2.0)
- PM E-DRIVE: **not applicable** — the scheme does not cover electric cars
- 80EEB: **WINDOW_CLOSED** — sanction window ended 31 Mar 2023
- New regime: 80EEB wouldn't be available anyway (old regime only)
- State EV policy: evaluated against Maharashtra's current window
- Road tax: state EV concession if within its notified period

Today's code would get at least three of those wrong and would quietly invent a ₹1.5L deduction. That gap is the whole reason for this subsystem.

### 5.6 Caching and cost control

Tier-1 policy facts are slow-moving: cache in Postgres with a `verified_on` stamp and a per-source TTL (GST rates 30d, state EV policy 7d, gold rates 1h, circle rates 90d). A research run for a common item should hit cache and cost nothing. Every cached fact renders in the UI with its own "as of" date — no undated numbers anywhere.

---

## 6. Evidence & trust layer

The user must be able to see *why* to believe any answer. Four artefacts, all built on the same substrate.

### 6.1 Confidence must be computed, never authored

The current app hardcodes `confidence=0.80` in `deduction_hunter.py` and `confidence=0.88` in `price_intelligence.py`, then renders them as a `quality_score` percentage. `ValidationReport` separately subtracts a flat 0.1 per warning regardless of what the warning was. These are invented numbers presented as measurement, which is worse than showing nothing.

The honest framing: **for a deterministic engine, the arithmetic is certain.** All the uncertainty lives in the inputs. So confidence is composed from five measurable signals:

| Signal | Measures | Example degradation |
|---|---|---|
| Input provenance | official document > parsed > user-stated > system-assumed | Salary typed by hand rather than read from Form 16 |
| Rule freshness | age of `last_verified` on every rule used | Rule pack verified 200 days ago |
| Completeness | which relevant fields are absent | Rent paid not provided → HRA exemption excluded |
| Assumption count | defaults substituted for real data | Age assumed 35; metro status assumed |
| Source tier | Tier-1 official vs Tier-3 aggregator (procurement) | Price from an aggregator, not an OEM list |

**A deterministic computation on complete official inputs from fresh rules reports `CERTAIN`, not 87%.** Fake precision is itself a trust leak. And every score expands into the specific signals that reduced it, each phrased as something the user can act on: *"Provide your rent receipts to raise this from Partial to High."*

### 6.2 Show the math — a real trace, not a re-narration

Every engine function returns `(value, trace)`. A trace step is `(label, operands, operation, result, rule_ref, citation)`, and steps compose into a tree mirroring the computation. Crucially the trace **replays** — re-executing the recorded steps must reproduce the value exactly, which is asserted in the golden tests.

This matters because the alternative — asking an LLM to explain how a number was reached — produces plausible arithmetic that may not be the arithmetic that actually ran. The worksheet the user sees *is* the computation.

```
Taxable income                                    ₹12,00,000
├─ Gross salary                                   ₹12,75,000   [input: Form 16 Part B]
└─ Less: standard deduction                        ₹  75,000   [Act 2025 · s.16(ia) legacy · FY 2026-27]

Tax before rebate                                 ₹  60,000
├─ ₹0 – ₹4,00,000        @  0%                    ₹       0
├─ ₹4,00,001 – ₹8,00,000 @  5%                    ₹  20,000
└─ ₹8,00,001 – ₹12,00,000 @ 10%                   ₹  40,000   [new regime slabs · verified 2026-08-09]

Less: rebate u/s 87A                              ₹  60,000    [≤ ₹12,00,000 · max ₹60,000]
                                                  ──────────
TOTAL TAX                                         ₹       0
```

### 6.3 Evidence panel

An expandable drawer on every result, four tabs: **Working** (the trace above), **Sources** (citations with tier, URL, access date), **Inputs** (each value and where it came from, assumptions flagged and editable in place), **Confidence** (the signal breakdown and what would raise it).

Sources are archived, not just linked — URL, tier, `retrieved_at`, HTTP status, content hash, and a stored snapshot of the cited extract. Government pages move; a citation that 404s during an assessment is worthless.

### 6.4 Downloadable Evidence Pack

One click produces a PDF the user can hand to a CA: inputs with provenance, assumptions, full step-by-step math, every citation with **both** Act numberings, source URLs with access dates, rule-pack version and per-rule verification dates, confidence breakdown, closed-window notices, and a machine-readable JSON appendix.

Two properties make it defensible rather than decorative:

- **It contains zero LLM-generated figures** — assertable by running the `numeric_provenance` scorer over the finished pack.
- **It is reproducible.** The pack pins the rule-pack version and an input snapshot hash. Regenerating from the same pinned inputs yields a byte-identical computation section. Recomputing under a *newer* rule pack shows a clearly marked diff rather than silently changing the answer.

Packs are generated into the encrypted vault and delivered by signed short-lived URL — never written to local disk, which is how v1 ended up with 40+ unencrypted financial PDFs in `exports/`.

---

## 7. Phase plan

Each phase has an **exit gate**. No phase starts before the previous gate is green.

### Phase 0 — Foundation *(scaffolding, no behaviour change)*
Repo hygiene (delete `.DS_Store`, `__pycache__`, `.pytest_cache`, `senv/`; purge `exports/` and gitignore it). `feature.json` + `PROGRESS.md` + generator script. Harness skeleton with all four layers wired but empty. GitHub Actions CI. Import-linter boundary rule for `backend/core`. Dependency upgrade and audit (`pip-audit`); drop `celery`, `rq`, `python-jose`.
**Gate:** CI green on an empty suite; boundary rule enforced.

### Phase 1 — Deterministic tax core ⭐ *the bedrock*
`backend/core/` created. Rule packs for FY 2024-25 / 2025-26 / 2026-27 + the 1961→2025 section alias map. Engine: slabs, 87A rebate **with marginal relief**, surcharge **with marginal relief**, cess, standard deduction, Chapter VI-A with correct 80D/80DDB/80CCD structures, capital gains (111A @ 20%, 112A @ 12.5% with ₹1.25L exemption, 112 @ 12.5%, pre-2018 grandfathering, pre-23-Jul-2024 property option), presumptive 44AD/44ADA. Eligibility DSL + evaluator. `Money`/`Provenance` value objects. **120+ golden tests, property tests, 100% branch coverage on the engine.**
**Gate:** every golden test passes; coverage ≥ 95%; zero tax constants remain outside `core/rules/`.

### Phase 2 — Demolition & de-faking
Delete: frontend demo-auth fallback, all `mockData` page fallbacks, `services/api.ts` (keep one client, relative URLs), `agents/tax_strategy.py` duplicate engine, `_estimate_tax_bracket`, hardcoded slabs in five files, `main.py` lifespan DDL. Replace: fake embeddings → `BAAI/bge-small-en-v1.5` with Qdrant re-ingest; sync `Groq` → `AsyncGroq` with lazy per-request clients; `IndiaTaxDataFetcher` → renamed `RuleSetProvider` reading real rule packs. Fix error leakage (correlation IDs). Honest README rewrite.
**Gate:** no `grep` hit for a hardcoded slab outside `core/rules`; retrieval returns semantically relevant docs on a 20-query spot-check; k6 shows p95 < 3s at 20 concurrent users.

### Phase 3 — Thin agents & real orchestration
Agents lose all arithmetic — they receive tool outputs and explain them. Parallel execution via `asyncio.gather`. `RequestContext` replaces `AsyncSessionProxy`/ContextVar/global tools, so scheduler jobs work. WebSocket streams real per-agent progress. Agent eval harness populated: 60+ scenarios, all four scorers, recorded fixtures, `baseline.json`.
**Gate:** zero `numeric_provenance` failures; p95 multi-agent latency < 4s; scheduler jobs execute against a real DB session.

### Phase 4 — Document intelligence
Form 16 Part A/B parser → profile autofill. Broker P&L parsers (Zerodha, Groww, CAMS/KFintech) → capital gains ledger. AIS/TIS parser → reconciliation engine with mismatch severity. Encrypted document vault (S3/MinIO, SSE, signed short-lived URLs, TTL). All parsers are format-fuzzed and fail *loudly* rather than guessing.
**Gate:** parsers handle real samples + malformed input without silent wrong values; reconciliation flags a seeded mismatch set with zero false negatives.

### Phase 5 — Planning features
Regime comparison with exact breakeven deduction. Advance tax planner with 234B/234C projection and the 44AD/44ADA special case. Capital gains optimiser + tax-loss harvesting (Feb–March prompts, wash-sale-adjacent cautions). Deterministic ITR form selector (replacing the wrong table). Profile-derived deadline calendar. Salary structuring optimiser.
**Gate:** each feature has golden tests; every output line carries a citation.

### Phase 6 — Procurement Intelligence
Item resolver, tiered source gatherer with cache + `verified_on`, landed-cost model, eligibility integration, dated signal ledger, quote teardown (upload a dealer quotation → line-by-line analysis), category packs (vehicle/EV, property, electronics, gold, appliance, business asset). Rebuild `SmartSavings` + `PurchaseAdvisorChat` on the real backend.
**Gate:** the EV worked example in §5.5 is correct end-to-end; no Tier-3 source appears in any cost line; every figure carries an "as of" date.

### Phase 7 — Production readiness
DPDP: consent records with versioned notice, purpose limitation, retention policy, erasure endpoint, breach-notification runbook, grievance officer, data-processing register. Security: httpOnly cookie + CSRF or hardened token handling, refresh rotation, revocation check in `get_current_user`, rate limiting, secrets manager, security headers, PII-redacting logs. Observability: OpenTelemetry traces, Prometheus metrics, Sentry, LLM cost/token dashboards. Deploy: multi-stage Docker, health/readiness probes, backups, staging environment, runbook.
**Gate:** external security review checklist passed; DPDP obligations mapped to implemented controls in a published table; load test at target concurrency.

---

## 8. Deletion list

| Path | Reason |
|---|---|
| `useAuthStore` demo fallback + `finsage_demo_users` | Plaintext passwords in localStorage; silently fakes auth on any backend error |
| `utils/mockData.ts` + all page fallbacks | Shows fabricated financial figures as if real |
| `frontend/src/services/api.ts` | Dead second API client, different port and token key |
| `agents/tax_strategy.py` regime calculators | Duplicate, divergent, FY 2024-25, cliff bug |
| `deduction_hunter._estimate_tax_bracket` | Fifth copy of the slabs, FY 2020-21 values |
| `rag/embeddings._generate_embedding` | `md5 → np.random.seed` is not an embedding |
| `TAX_SLABS`/`DEDUCTION_LIMITS` in `tools/calculation.py` | Superseded by rule packs |
| `main.py` lifespan `ALTER TABLE` | Races across replicas; Alembic owns schema |
| `celery`, `rq`, `python-jose`, `sentence-transformers==2.2.2` | Unused or broken |
| `exports/*.pdf` (40+ files) | Unencrypted user financial data on disk |
| `.DS_Store`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `senv/` | Should never have been in the tree |

`price_intelligence.py` is **rewritten, not deleted** — the CII table is still needed for grandfathered pre-23-Jul-2024 property, but the yield comparisons and the SGB recommendation go.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| **Tax rules go stale again** — the failure that defined v1 | `last_verified` + CI freshness gate failing at 180 days; rules as data, one file per FY |
| **1961 → 2025 Act citation confusion** during transition | Alias map; display both numbering schemes; `legal_refs` carries `act` + `legacy_section` |
| **LLM reintroduces invented numbers** | `numeric_provenance` scorer as a hard CI gate, not a guideline |
| **Document parsers silently mis-read a value** | Fail loudly on low confidence; always show the user the extracted value against the source page for confirmation before it enters any calculation |
| **Official sources change URL/format** | Tier-1 fetchers are individually tested with a nightly canary; cached facts keep serving with a visible staleness badge rather than breaking |
| **Scope is large** | Phase gates. Phase gates. Phases 0–2 alone produce a correct, honest, deployable product. |
| **Cost of live LLM eval runs** | Recorded fixtures for CI; live runs nightly only |

---

## 10. What "done" means

A user in India can: sign up securely, upload their Form 16 and AIS, have their profile populated accurately, see their FY 2026-27 tax computed correctly under both regimes with the exact breakeven, see every deduction they qualify for **and every one whose window has closed**, get an advance-tax schedule with interest projection, reconcile against AIS before the department does, plan a major purchase with a true landed cost and dated policy signals — and for **every single number**, click through to the rule, the section, the source URL, and the date it was verified.

No fabricated figures. No stale rules. No claims in the README that the code doesn't honour.

---

**Next:** on approval, Phase 0 begins — repo hygiene, CI, harness skeleton, and the boundary rule. `feature.json` and `PROGRESS.md` are already in place at repo root and become the working tracker from that point on.
