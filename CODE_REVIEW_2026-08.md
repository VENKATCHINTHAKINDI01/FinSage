# FinSage AI — Deep Review

**Reviewed:** 9 August 2026 · FY 2026-27 (AY 2027-28) · ~28,600 LOC

---

## 1. What the project actually is

A FastAPI + React platform for Indian personal tax optimisation. Groq Llama 3.3 70B behind 12 "agents", Postgres/Redis/Qdrant, JWT auth, PDF reports, APScheduler jobs.

**Layering is genuinely good.** `api/ → orchestrator/ → agents/ → tools/ → services/` with a clean `ToolExecutor` registry (~35 tools), a `BaseAgent`/`AgentOutput` contract, a `ValidationReport` that travels with every result, alembic migrations, structured logging, Docker Compose. That is real architectural thinking and it is well above the average project of this size.

**But the depth doesn't match the surface.** The parts that make a tax product trustworthy — correct rules, real retrieval, deterministic math — are the parts that are stubbed. The parts that are complete are the easy ones: routing, DTOs, PDF styling, page shells.

The README describes a product that does not exist in the code:

| README claim | Reality |
|---|---|
| "12-agent **LangGraph** orchestration" | `graph.py` is a `for` loop over a dict. LangGraph is in requirements, essentially unused. |
| "**RAG** knowledge base, Qdrant" | Embeddings are `md5 → np.random.seed → random vector`. Not semantic. At all. |
| "**India Tax Data Fetcher** — fetches real-time data from incometax.gov.in" | A hardcoded Python dict. `requests` is imported and never called. |
| "**DPDP Act 2023 & GDPR** compliance design" | No consent record, no retention policy, no erasure endpoint, no encryption at rest. |
| "Real-time streaming of agent reasoning" | WebSocket transport exists; agents don't emit token-level reasoning into it. |

Claiming compliance you haven't built is worse than not claiming it. Fix the README first — it's a five-minute change that removes the biggest credibility risk in the repo.

---

## 2. The Indian tax landscape you're building into (as of Aug 2026)

This matters because **your rules are ~2 years stale and were partly wrong even for the year they claim.**

### 2.1 The Income-tax Act, 2025 replaced the 1961 Act on 1 April 2026

819 sections → 536. Every section renumbered. Income Tax Rules, 2026 replaced the 1962 Rules on the same date. Policy is largely unchanged; the *citations* are not.

**Impact on you:** your entire product speaks 1961-Act language — "Section 80C", "115BAC", "Section 54EC", "Schedule FA", "Section 6(1)". For FY 2026-27, ITR utilities and departmental correspondence use the new numbering. Every user-facing citation in agents, `schemes_search.py`, and PDF reports is now a reference to a repealed statute. You need a **section alias map** (old ↔ new) and should display both during the transition years.

### 2.2 Slabs — new regime, FY 2026-27 (unchanged from FY 2025-26)

| Taxable income | Rate |
|---|---|
| Up to ₹4,00,000 | Nil |
| ₹4,00,001 – ₹8,00,000 | 5% |
| ₹8,00,001 – ₹12,00,000 | 10% |
| ₹12,00,001 – ₹16,00,000 | 15% |
| ₹16,00,001 – ₹20,00,000 | 20% |
| ₹20,00,001 – ₹24,00,000 | 25% |
| Above ₹24,00,000 | 30% |

- **Rebate 87A: ₹60,000** → zero tax up to ₹12,00,000 taxable (with marginal relief just above).
- **Standard deduction ₹75,000** → ₹12.75L gross salary effectively tax-free.
- Rebate does **not** apply to special-rate income (111A/112A capital gains).
- No senior-citizen slab distinction under the new regime.

**Old regime unchanged:** ₹2.5L / ₹5L / ₹10L at 5/20/30%, 87A rebate ₹12,500 up to ₹5L, standard deduction ₹50,000, senior ₹3L and super-senior ₹5L exemption.

### 2.3 Capital gains — post 23 July 2024 regime

- **STCG s.111A** (listed equity/EOF/business trust): **20%** flat — *not* slab rate.
- **LTCG s.112A**: **12.5%**, exemption **₹1,25,000** per year.
- **Other LTCG s.112**: **12.5% without indexation**. Indexation abolished for transfers on/after 23 Jul 2024, with a grandfathering option (20% + indexation) for resident individuals/HUFs on immovable property acquired before that date.
- Equity holding period 12 months; most other assets 24 months.
- Surcharge on capital gains capped at 15%.

### 2.4 GST 2.0 — effective 22 September 2025

12% and 28% slabs abolished. Structure is now **0 / 5 / 18 / 40%** (40% for sin & luxury). **Registration thresholds unchanged**: ₹40L goods / ₹20L services (₹20L / ₹10L in special category states).

### 2.5 TDS thresholds revised 1 April 2025

Interest (non-senior) ₹40,000 → **₹50,000**; senior citizens → **₹1,00,000**. Rent ₹2.4L → **₹6,00,000 p.a.** Commission/brokerage ₹15,000 → ₹20,000.

### 2.6 Other live facts worth encoding

- ITR-U window extended to **48 months** from end of relevant AY (Budget 2025).
- Advance tax: 15% / 45% / 75% / 100% by 15 Jun, 15 Sep, 15 Dec, 15 Mar. Presumptive (44AD/44ADA) taxpayers: 100% by 15 Mar.
- Interest on refunds under s.244A: **0.5% per month**, not 1% p.a.
- 80CCD(2) employer NPS: **14% of salary** under the new regime (10% old) — one of the very few deductions that survives in the new regime, and your product doesn't model it.

---

## 3. Correctness defects in the tax engine

These are ordered by how much money they'd get wrong.

### 🔴 CRITICAL

**3.1 No Section 87A rebate anywhere in `TaxCalculationEngine`.**
A user with ₹11,00,000 taxable income owes **₹0**. Your engine returns roughly ₹75,000 + cess. Every salaried user under ₹12L gets a materially wrong answer. This is the single worst bug in the repo.

**3.2 Slabs are FY 2023-24 vintage.**
`tools/calculation.py::TAX_SLABS["individual"]` = 3L/6L/9L/12L with 30% above ₹12L. Correct for FY 2023-24 and 2024-25; wrong for FY 2026-27 (7 slabs, 30% starts at ₹24L). Someone at ₹20L is being charged 30% on income that's actually taxed at 20–25%.

**3.3 `senior_citizen` slabs are old-regime slabs inside a new-regime table.**
`{5L: 0%, 10L: 5%, ∞: 20%}` — and `calculate_income_tax` silently switches to it when `age >= 60`. Under the new regime there is no senior slab. A 62-year-old with ₹30L income gets taxed at 20% top rate instead of 30%. Not staleness — a logic error.

**3.4 LTCG hardcoded at 20% flat, indexation "ignored".**
Should be 12.5% with a ₹1.25L exemption for 112A. You overstate equity LTCG tax by ~60% and don't apply the exemption at all.

**3.5 STCG taxed at slab rates.**
`CapitalGainsTaxCalculator.calculate_stcg_tax` adds STCG to total income and applies slabs. For listed equity (s.111A) it's a flat 20%. Wrong in both directions depending on the user's bracket.

**3.6 No standard deduction in the core engine.**
`data_validator.py` knows it's ₹75,000, `india_tax_data_fetcher.py` says ₹50,000, `pdf_parser.py` says ₹50,000, `calculation.py` doesn't apply it at all. Three values, three files, zero agreement.

### 🟠 HIGH

**3.7 No marginal relief on surcharge.**
At ₹50,00,001 taxable income your engine creates a ~₹1.4 lakh cliff. Marginal relief caps the surcharge so additional tax never exceeds additional income. Same problem at the 87A ₹12L boundary once you implement the rebate.

**3.8 Deduction limits are wrong.**

| Section | Your value | Correct |
|---|---|---|
| 80D | ₹1,50,000 flat | ₹25,000 self (₹50,000 if senior) + ₹25,000/₹50,000 parents; max ₹1,00,000 |
| 80DDB | ₹1,00,000 | ₹40,000; ₹1,00,000 only for senior citizens |
| 80CCD | ₹1,50,000 lump | 80CCD(1) is *inside* the 80C ₹1.5L ceiling; (1B) is +₹50,000; (2) employer is separate at 14% of salary |
| 80TTA/TTB | ok | ok |

`schemes_search.py` separately claims 80D "self_spouse_children: 75000" — a fourth inconsistent number.

**3.9 ITR form guidance is factually wrong.**
`india_tax_data_fetcher.py` says *"ITR-5: High income individuals (> ₹50 lakh)"*. ITR-5 is for **firms, LLPs, AOPs and BOIs** — never individuals. **ITR-3** (individuals with business/professional income) is missing entirely. ITR-4 Sugam is described as "turnover < ₹5 crore"; it's total income ≤ ₹50L under 44AD/44ADA (44AD turnover cap ₹2cr, ₹3cr with ≥95% digital receipts; 44ADA ₹50L, ₹75L digital). Users following this file file the wrong form.

**3.10 Two divergent tax engines.**
`agents/tax_strategy.py` reimplements old/new regime slabs by hand (FY 2024-25 values) instead of calling `TaxCalculationEngine`. Its 87A logic has a hard cliff at ₹7,00,001 with no marginal relief. Two implementations that already disagree — this will keep drifting.

**3.11 Refund interest at 1% p.a.**
s.244A is 0.5% **per month** (6% p.a.). Off by 6×.

**3.12 GST data stale.**
`gst_rates: [0, 0.05, 0.12, 0.18, 0.28]` — 12% and 28% no longer exist; 40% missing. Registration threshold hardcoded ₹40L with no services (₹20L) or special-category branch.

### 🟡 MEDIUM

**3.13 `deduction_hunter._estimate_tax_bracket`** carries a *fifth* private copy of the slabs (2.5L/5L/7.5L/10L/12.5L) — those are FY 2020-21 new-regime slabs. Dead-ish code that will eventually get called.

**3.14 `data_validator.INDIA_TAX_GROUND_TRUTH.rebate_87a_limit = 700000`** — should be 12,00,000 with a ₹60,000 rebate amount. The thing named "ground truth" is not ground truth.

---

## 4. Architectural issues

### 4.1 🔴 No single source of truth for tax rules

Slabs and limits are hardcoded in **at least seven** files: `tools/calculation.py`, `tools/data_validator.py`, `tools/schemes_search.py`, `tools/pdf_parser.py`, `services/india_tax_data_fetcher.py`, `agents/tax_strategy.py`, `agents/deduction_hunter.py`. They disagree with each other today. Every future Budget means a seven-file scavenger hunt, and you will miss one.

**Fix — do this before anything else:**

```
backend/rules/
  fy_2024_25.yaml
  fy_2025_26.yaml
  fy_2026_27.yaml
  aliases_1961_to_2025.yaml     # section renumbering map
  __init__.py                    # load_ruleset(fy) -> TaxRuleset
```

Every calculation function takes `fy: str` explicitly — never defaults to "current". Data outlives code; a tax engine that can't compute a prior year is useless for revised returns and ITR-U (now a 48-month window).

Then add **golden tests**: 30–40 `(inputs → expected tax)` cases per FY, cross-checked against the Income Tax Department's own calculator. Right now you have ~50 tests and **not one** asserts a tax figure. For a tax engine, that is the inverse of where tests belong.

### 4.2 🔴 RAG is decorative

`rag/embeddings.py::_generate_embedding`:

```python
hash_val = hashlib.md5(text.encode()).hexdigest()
np.random.seed(int(hash_val, 16) % (2**32))
embedding = np.random.randn(self.dim)
```

Deterministic, yes. Semantic, no. "80C deduction limit" and "Section 80C limit" produce orthogonal vectors. With `similarity_threshold=0.7`, retrieval returns nothing or noise — and either way `ValidationReport` still reports `sources_verified`, so the confidence scores in the UI are measuring nothing.

`sentence-transformers` is already in `requirements.txt` and unused. Swap in `all-MiniLM-L6-v2` (384-dim) or `BAAI/bge-small-en-v1.5`, set the Qdrant collection dim to match, and re-ingest. Half a day's work; it turns a fake subsystem into a real one.

### 4.3 🔴 Sync Groq calls inside async handlers

Every agent does `client.chat.completions.create(...)` — the **synchronous** Groq client — inside `async def`. This blocks the event loop for the full duration of the LLM call. With agents chained sequentially and 2+ LLM calls each, five concurrent users will serialise into a queue. Use `AsyncGroq`, or at minimum `await asyncio.to_thread(...)`. Also: module-level `client = Groq(...)` in ~10 files is an import-time side effect that makes the modules unmockable and crashes on a missing key.

### 4.4 🟠 The multi-agent architecture isn't earning its cost

12 agents, 16 intents, and `_get_agents_for_intent` maps most intents to exactly one agent. The agents never collaborate, never share intermediate state, never revise each other. It's one function per topic with an LLM wrapper and a `for` loop calling it.

You're paying for this: sequential execution, N× LLM latency, N× cost, N× hallucination surface, 12 files to keep in sync with the tax rules.

Two honest options:

- **(a) Collapse to one agent + deterministic tools.** One well-prompted agent with your existing ~35 tools, letting the model choose tools, would be faster, cheaper, and *more* accurate — because the numbers would come from code instead of from prose. This is what I'd do.
- **(b) Commit to real LangGraph.** Actual `StateGraph` with conditional edges, parallel fan-out via `asyncio.gather`, retry nodes, checkpointing to Postgres, and a supervisor that can loop. Then the README claim becomes true and the WebSocket stream has something real to stream.

Either is defensible. What you have now is (b)'s complexity with (a)'s capability.

### 4.5 🟠 The LLM is generating numbers

`deduction_hunter._identify_deductions` asks the model for *"estimated deductible amount (in INR)"*, then feeds that number into savings math and into a **PDF the user might hand to a CA**. The example in your own prompt is a ₹1,80,000 "home office" deduction — which isn't available to a salaried Indian taxpayer under any section.

Clamping to section limits afterwards doesn't help: it turns a fabricated deduction into a fabricated-but-plausible one, which is worse.

**Invert it.** LLM extracts *facts and classifications* from the user's text ("has home loan", "pays rent in a metro", "employer offers NPS"). Deterministic code computes every rupee. This is the highest-leverage change you can make to trustworthiness, and it also makes the whole thing testable.

### 4.6 🟠 Global mutable state and hidden context

`AsyncSessionProxy` + `db_session_var` ContextVar + `OrchestratorProxy` + module-global `tool_executor`. Consequences:

- Scheduler jobs run with no request context, so any DB-touching tool raises `RuntimeError: No active database session`. Your monthly-health-report job is likely broken for this reason.
- Tests need the full lifespan to have run.
- Two replicas behind a load balancer share none of this.

Pass an explicit `RequestContext(db, user, tools, fy)` down the call chain.

### 4.7 🟡 Migrations vs. ad-hoc DDL

`main.py` lifespan executes `ALTER TABLE financial_profiles ADD COLUMN IF NOT EXISTS profile_data JSONB` on **every startup**, while Alembic exists and has three revisions. With multiple replicas booting simultaneously this races. Pick Alembic; delete the DDL.

### 4.8 🟡 Duplicate, conflicting frontend API layers

| | `src/api/client.ts` | `src/services/api.ts` |
|---|---|---|
| Transport | `fetch` | `axios` |
| Base URL | `http://localhost:8001` | `http://localhost:8000/api/v1` |
| Token source | `localStorage['finsage_auth'].state.token` | `sessionStorage/localStorage['token']` |
| 401 handling | none | interceptor |

Different ports, different token keys. One of these is dead code and it isn't obvious which. Also both hardcode an absolute origin, which defeats the Vite `/api` proxy the README describes and forces you into CORS. Use relative paths.

---

## 5. Security, privacy & risk

### 5.1 🔴 The "demo mode" fallback is the most dangerous code in the repo

`useAuthStore.login()` catches **any** exception from the backend — including a network blip, a 500, or a CORS failure — and silently falls back to authenticating against `localStorage`:

```js
function fakeToken(email) { return btoa(`${email}:${Date.now()}`); }
users.push({ name, email, password });   // plaintext password in localStorage
```

Then every page (`Dashboard`, `TaxAnalysis`, `Compliance`, `HealthScore`, `ITRGuide`, `Reports`, `Settings`) falls back to `mockData` on API failure. Net effect: **when the backend is down, the app shows a logged-in user fabricated financial figures that look exactly like real ones.**

For a demo this is a convenience. For anything a person might act on, it's the worst possible failure mode — silent, plausible, and financial. At minimum: gate it behind `import.meta.env.DEV`, never store plaintext passwords, and render an unmissable banner. Better: delete it and show a real error state.

### 5.2 🟠 Token handling

JWT in `localStorage` = XSS-exfiltratable, and this app holds income, PAN and (eventually) AIS data. 15-minute expiry is good. Missing: refresh-token rotation, a revocation check against the `sessions` table in `get_current_user`, and logout-side invalidation. Consider httpOnly cookie + CSRF token.

### 5.3 🟠 Error leakage

`raise HTTPException(status_code=500, detail=str(e))` in `chat.py` returns raw exception text to the client — which for SQLAlchemy errors can include connection strings and schema details. Log the detail, return a correlation ID.

### 5.4 🟠 DPDP Act 2023 obligations you've claimed but not built

Handling income + PAN makes you a **Data Fiduciary**. Required and currently absent:

- Itemised notice + explicit, recorded consent (with withdrawal as easy as giving)
- Purpose limitation and stated retention periods
- Erasure on withdrawal/purpose completion
- Breach notification to the Data Protection Board **and** affected principals
- Verifiable parental consent if any user is under 18
- Grievance officer contact

Also: `exports/` currently holds 40+ generated PDFs with real financial data, unencrypted, in the working tree. Move to object storage with server-side encryption, signed short-lived URLs, and a TTL.

### 5.5 🟡 Regulatory positioning

Personalised investment advice in India is SEBI-regulated (Investment Adviser Regulations, 2013). Tax *computation and information* is fine; "you should invest in X" is not. Your `INVESTMENT_ADVICE` and `PORTFOLIO_ANALYSIS` intents route into `tax_optimizer_agent`. Keep the output framed as tax treatment of instrument categories, add a standing disclaimer, and avoid product-specific recommendations.

### 5.6 🟡 Dependencies

`fastapi==0.104.1` / `starlette==0.27.0` / `pydantic==2.5.0` are ~2 years old — check advisories. `python-jose` is effectively unmaintained (and you already have `PyJWT`; pick one). `sentence-transformers==2.2.2` is known-broken against modern `huggingface_hub`. `celery`, `rq` **and** `APScheduler` are all installed; only APScheduler is used. Frontend pins (`react 19.2.7`, `vite 8.1`, `typescript 6.0`, `lucide-react 1.21`) should be verified as resolvable.

---

## 6. Features worth building

### Tier 1 — makes it actually useful

**6.1 AIS / TIS reconciliation.** ⭐ The single highest-value feature in Indian personal tax, and you have zero code touching it. Users download AIS from the compliance portal; parse it, reconcile against declared income, flag mismatches *before* the department does. AIS mismatch is the #1 cause of tax notices. Nothing else on this list comes close.

**6.2 Form 16 / 16A parser.** You already have PyMuPDF and a `pdf_parser.py` stub. Part B of Form 16 is semi-structured and reliably parseable. Kills the biggest onboarding drop-off: typing in your own salary breakdown.

**6.3 Regime comparison as a deterministic calculator.** Not an LLM agent. Compute old vs new on the user's actual deduction set and show the **breakeven deduction amount** for their income. Under FY 2026-27 numbers the old regime rarely wins below ~₹8L of deductions — compute it exactly, show the crossover, done.

**6.4 Advance tax planner with 234B/234C projection.** Purely deterministic, genuinely useful, nobody does it well. Quarterly instalments, shortfall, projected interest. Special-case 44AD/44ADA (100% by 15 March).

**6.5 Capital gains from broker statements.** Parse Zerodha/Groww/CAMS-KFintech P&L. Correct 111A/112A treatment, ₹1.25L exemption, grandfathering for pre-31-Jan-2018 equity, and **tax-loss harvesting prompts in Feb–March**. This is where retail users actually lose money.

### Tier 2

**6.6 Salary structuring optimiser** (old regime): HRA vs 80GG, LTA, employer NPS 80CCD(2) at 14%, meal cards, car perquisite. Constrained optimisation, fully deterministic.

**6.7 ITR form selector as a decision tree.** The rules are crisp. Your current data is wrong (§3.9). This should never have been LLM territory.

**6.8 Profile-derived deadline calendar.** ITR 31 Jul / 31 Oct (audit) / 30 Nov (TP), advance tax ×4, TDS returns 24Q/26Q, GSTR-1/3B if registered, ITR-U 48-month window. Your scheduler currently has hardcoded global jobs — derive them per profile.

**6.9 Notice triage.** Upload a 139(9) / 143(1) / 142(1) / 148 notice → classify, explain in plain language, lay out the response deadline and steps. High anxiety = high willingness to pay.

**6.10 Citation ledger.** Every displayed number traces to `(rule_id, section, FY, source_url, computed_by)`. You've half-built this in `ValidationReport` — finish it and surface it in the UI. For a tax product, "why is this number this number" is the whole game.

### Tier 3

- GST module for freelancers: 44ADA + GST interaction, LUT for export of services, GSTR-1/3B reminders.
- **Residency day-counter** for the NRI agent: s.6 with the 120-day rule for ₹15L+ Indian income, deemed residency, RNOR status. Deterministic — should not be an LLM.
- HUF / family joint optimisation.

---

## 7. Honest overall opinion

The breadth and structure here are impressive, and the effort shows. Layering, tool registry, validation plumbing, migrations, Docker, reports — you clearly thought about how a real system is put together, and most people building at this level don't.

But for a finance product the priority order is **correctness > trust > breadth > polish**, and right now it's exactly inverted. Twelve agents sit on top of a tax engine that would tell an ₹11 lakh earner they owe ₹75,000 when they owe nothing. RAG that returns random vectors feeds "confidence scores" displayed to users. A "live data fetcher" that fetches nothing. The scaffolding is a 9; the substance underneath is a 4.

**I'd trade eight of the twelve agents for one tax engine that is provably correct for FY 2026-27.** That's not a criticism of ambition — it's where the actual value is. A tool that computes one thing exactly right is worth more than twelve that are approximately wrong, and it's the only version anyone will trust with their PAN.

The good news: nothing here is architecturally unfixable. The rules extraction is a weekend. Real embeddings are half a day. `AsyncGroq` is an afternoon. The demo-mode fallback is a delete. You could be in a fundamentally different place in two weeks.

---

## 8. Suggested order of work

**Week 1 — stop being wrong**
1. Extract `backend/rules/fy_YYYY_YY.yaml`; delete all seven hardcoded copies; thread `fy` through every signature.
2. Implement 87A rebate (₹60,000 / ₹12L) + marginal relief, standard deduction, FY 2026-27 slabs.
3. Fix capital gains: 111A @ 20%, 112A @ 12.5% with ₹1.25L exemption, no indexation.
4. Fix 80D / 80DDB / 80CCD structures. Fix the ITR form table. Fix GST slabs and TDS thresholds.
5. Write 30+ golden tests per FY against the IT Dept calculator. **Non-negotiable.**
6. Rewrite the README to describe what exists.

**Week 2 — stop being slow and fake**
7. `AsyncGroq` everywhere; lazy client construction; `asyncio.gather` for independent agents.
8. Real embeddings (`all-MiniLM-L6-v2`), re-ingest Qdrant, verify retrieval actually retrieves.
9. Delete the frontend demo-auth fallback; delete one of the two API clients; use relative URLs.
10. Stop the LLM emitting rupee amounts — extraction only, computation in code.

**Week 3–4 — become useful**
11. Form 16 parser → profile autofill.
12. Deterministic regime comparison with breakeven.
13. Advance tax + 234B/234C planner.
14. Then AIS reconciliation — the feature that makes this a product rather than a calculator.

**Ongoing**
15. Section alias map for the 1961 → 2025 Act transition; show both citations.
16. DPDP: consent records, retention, erasure endpoint, encrypted document storage.
17. Decide on the agent architecture — collapse to one, or build the real graph.

---

*Tax positions above reflect law in force as of August 2026 and are for engineering guidance, not professional tax advice. Verify against incometax.gov.in before shipping any figure to users.*
