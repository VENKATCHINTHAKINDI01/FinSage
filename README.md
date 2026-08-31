# FinSage AI

**Deterministic tax computation, AI-assisted tax planning, and major-purchase cost intelligence for India — FY 2024-25 through FY 2026-27, under the Income-tax Act, 2025 (in force 2026-04-01) and the Income-tax Act, 1961 for prior years.**

`████████████████████░░` **91%** — 69/76 tracked features verified · full ledger in [`PROGRESS.md`](PROGRESS.md), generated from [`feature.json`](feature.json)

---

## Table of contents

1. [What this is](#what-this-is)
2. [The one rule everything follows](#the-one-rule-everything-follows)
3. [Architecture](#architecture)
4. [Tech stack](#tech-stack)
5. [Features](#features)
6. [Agents](#agents)
7. [Tools](#tools)
8. [Frontend](#frontend)
9. [Project structure](#project-structure)
10. [Getting started](#getting-started)
11. [Configuration](#configuration)
12. [Running it](#running-it)
13. [Testing](#testing)
14. [API reference](#api-reference)
15. [Security & compliance](#security--compliance)
16. [Project status & roadmap](#project-status--roadmap)
17. [Known limitations](#known-limitations)
18. [Contributing / development conventions](#contributing--development-conventions)
19. [License](#license)

---

## What this is

FinSage AI is a full-stack platform that computes Indian personal income tax exactly, explains it in plain language, and helps a user act on it — regime selection, deductions, advance tax, capital gains, government scheme eligibility, ITR filing guidance, compliance/audit readiness, and cost comparisons for large purchases (vehicles, property, gold, electronics) that factor in GST, subsidies, and financing.

It is **not** a chatbot wrapped around a language model's idea of tax law. The tax math lives in a pure Python engine with versioned, dated rule packs; the language model's job is to explain a number the engine already computed, never to invent one.

---

## The one rule everything follows

> **No rupee figure shown to a user may originate from a language model.**

Every number is computed by deterministic Python in `backend/core/` from versioned rule packs, and carries a trace back to the rule, the section, the financial year, and the source it was verified against. The LLM's only jobs are to understand the question, extract structure from unstructured input (a payslip, a broker statement, a free-text query), and explain numbers that code produced.

This is enforced mechanically, not by convention:

- **`numeric_provenance`** (`backend/evals/scorers/numeric_provenance.py`) extracts every number from an agent's drafted answer and fails the eval suite if it doesn't appear in the tool results that agent actually received.
- **`test_no_agent_arithmetic.py`** statically scans every agent module for money-related arithmetic. Rebuilt ("thin") agents are asserted at **zero** tolerance; the handful of legacy modules still mid-rewrite carry a shrinking budget that a CI test enforces can only go down, never up.
- **Core purity**, enforced by an `import-linter` contract: `backend/core` cannot import `api`, `agents`, `db`, `groq`, `httpx`, or `sqlalchemy`. If the core can't reach the network or an LLM, it can't be non-deterministic — and if it's deterministic, it can be exhaustively tested.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  frontend/            React 19 + Vite. One fetch-based API client,    │
│                        no mock-data fallbacks.                        │
└───────────────────────────────────┬────────────────────────────────┘
                                     │  /api/v1/*  ·  /ws/*
┌───────────────────────────────────▼────────────────────────────────┐
│  backend/api/          FastAPI routers — auth, chat, compliance,      │
│                         benefits, suggestions, profile, reports,      │
│                         knowledge (RAG), notifications, consent, ws   │
├───────────────────────────────────────────────────────────────────┤
│  backend/orchestrator/                                                │
│    intent_detector      classifies the query into one of 16 intents   │
│    intent_bridge        routes tax-computation intents to the         │
│                          Analyst → Reviewer pipeline (below)          │
│    graph.AgentOrchestrator + parallel.fan_out()                       │
│                          async, per-agent-timeout fan-out for the     │
│                          intents not yet migrated to the pipeline     │
├───────────────────────────────────────────────────────────────────┤
│  backend/agents/                                                      │
│    Pipeline:  analyst → reviewer_ca → reviewer_risk → graded answer   │
│    Domain:    13 single-purpose agents, one per capability (§Agents)  │
├───────────────────────────────────────────────────────────────────┤
│  backend/tools/        ToolExecutor registry — 33 named tools across  │
│                         12 categories. Thin adapters; no tax knowledge│
│                         lives here (§Tools)                           │
├───────────────────────────────────────────────────────────────────┤
│  backend/core/         PURE. No I/O, no LLM, no database. This is     │
│                         the only place a tax figure is computed.      │
│    rules/              versioned FY rule packs (YAML) + the 1961→2025 │
│                         Act section-alias map                         │
│    tax_engine/         slabs · s.87A rebate with marginal relief ·    │
│                         surcharge with marginal relief · cess ·       │
│                         Chapter VI-A deductions · capital gains       │
│                         (111A/112A/112) · presumptive taxation        │
│    eligibility/        date-windowed eligibility DSL (ELIGIBLE /      │
│                         INELIGIBLE / WINDOW_CLOSED / INSUFFICIENT_DATA)│
│    provenance/         Money (Decimal) · Citation · Trace · a         │
│                         confidence model composed from input          │
│                         provenance, rule freshness & completeness     │
│    costing/            landed-cost model for the procurement advisor  │
└───────────────────────────────────────────────────────────────────┘
```

### Two computation paths

Most tax-computation intents (`tax_calculation`, `tax_deduction`, `tax_savings`, `tax_filing`, `tax_strategy`, `financial_planning`, `business_expense`, `price_intelligence`, `wealth_planning`, `general`) run through the **Analyst → Reviewer pipeline**:

```
draft ──► review ──┬─ clean ──────────────► answer
                    ├─ amend / flag ───────► answer + verbatim caveats
                    └─ block ─► redraft ─► review ─┬─ clean ─► answer
                                                    └─ block ─► WITHHELD
```

1. **Analyst** drafts to the standard a chartered accountant applies when advising a client — and computes nothing; every figure it states was produced by `backend/core` and handed to it as a tool result.
2. **Reviewer (CA pass)** re-checks the draft against the same tool results a *different* model, prompted differently, so agreement is real evidence rather than two instances of the same failure mode agreeing with itself.
3. **Reviewer (risk pass)** asks a different question — "if the tax department looked at this, what would they query?" — and can only annotate, never edit a number.
4. Verdicts are graded (**clean / amend / flag / block**). A reviewer can stop an answer from reaching the user; it can never change a figure in one — if it could, an LLM would again be deciding what a taxpayer owes.

A handful of intents not yet migrated to the pipeline (`investment_advice`, `portfolio_analysis`, `government_benefits`, `eligibility_check`, `compliance_check`, `cross_border_tax`) still route through the lightweight **`AgentOrchestrator`**, which fans invoked agents out concurrently via `asyncio.gather` with a per-agent timeout.

*(LangGraph is present as a dependency and a `StateGraph`-based orchestrator exists in `backend/orchestrator/advanced_orchestrator.py`, but it is not what's on the live request path today — the layering above is. Lazy `__getattr__`-based imports in `orchestrator/__init__.py` keep langgraph from being a hard dependency of the modules that don't need it.)*

### Enforced boundaries

Three `import-linter` contracts run in CI and locally via `lint-imports --config .importlinter`:

| Contract | Rule |
|---|---|
| Core purity | `backend.core` imports nothing that does I/O, touches a database, or calls a language model |
| Layered architecture | `api → orchestrator → agents → tools → core`, one direction only |
| Agents reach the core only through tools | No agent module imports `backend.core` directly |

---

## Tech stack

### Backend

| Layer | Choice |
|---|---|
| Framework | FastAPI 0.141 (async), Uvicorn |
| Validation / settings | Pydantic 2.13, pydantic-settings |
| Database | PostgreSQL 15, SQLAlchemy 2.0 (async), asyncpg, Alembic migrations |
| Cache / rate limiting | Redis 7/8 |
| Vector search | Qdrant + `fastembed` (`BAAI/bge-small-en-v1.5`, ONNX runtime — CPU-only, no torch/CUDA) |
| LLM | Groq (`AsyncGroq`), Llama 3.3 70B |
| Auth | PyJWT, bcrypt |
| Documents | ReportLab (PDF generation), PyMuPDF (parsing) |
| Background jobs | APScheduler |
| Object storage | boto3 (S3-compatible; MinIO for local dev) |
| Observability | `prometheus-client`, structured JSON logging with PII redaction |

### Frontend

| Layer | Choice |
|---|---|
| Framework | React 19, Vite 8, TypeScript 6 |
| Styling | Tailwind CSS 4 |
| State | Zustand 5 (with `persist` middleware) |
| Routing | React Router 7 |
| Forms | React Hook Form 7 + Zod 4 |
| Charts | Recharts 3 |
| 3D / motion | `@react-three/fiber` + `drei`, Framer Motion (landing page) |
| Icons | lucide-react |
| Testing | Vitest 4, Testing Library, jsdom |
| Lint | oxlint |

### Infrastructure

Docker Compose brings up Postgres, Redis, Qdrant, the FastAPI backend, and an Nginx-served frontend build. GitHub Actions runs CI (`.github/workflows/ci.yml`).

---

## Features

**Deterministic tax computation** — slabs, s.87A rebate with marginal relief, surcharge with marginal relief, cess, Chapter VI-A deductions with correct (not flattened) structures, capital gains (111A/112A/112), presumptive taxation (44AD/44ADA/44AE), both regimes, all age bands, for FY 2024-25 / 2025-26 / 2026-27.

**AI tax assistant** — a general-purpose chat (`/assistant`) backed by the full agent roster for free-form questions, plus a purpose-built purchase advisor inside Smart Savings for buy-decision-specific flows. Every answer is grounded in the user's real saved profile (income, deductions, regime, capital gains) and in the deterministic core — never a generic LLM answer.

**Tax planning tools** — regime comparison with the exact breakeven deduction amount, an advance-tax planner with 234B/234C interest projection, a capital-gains optimizer with tax-loss-harvesting prompts, a salary-structuring optimizer (HRA vs 80GG, LTA, employer NPS 80CCD(2) at 14%), and a deterministic ITR form selector.

**Document intelligence** — Form 16 / 16A parsing with profile autofill, broker P&L statement parsing, and AIS/TIS reconciliation against declared income, all backed by an encrypted, S3-stored document vault.

**Government benefits & schemes discovery** — ranks applicable central/state schemes against the user's real profile, with eligibility verification, required documents, and potential savings — not a static catalogue.

**Compliance & audit readiness** — a compliance score, red-flag detection, document completeness, and ITR filing guidance (recommended form, step-by-step process, TDS/advance-tax validation), all derived per-user rather than templated.

**Procurement intelligence** — cost comparison across purchase options ranked by **landed cost** (not sticker price), a tiered source-gathering pipeline (official / manufacturer / aggregator, with a hard invariant that a Tier-3 source can never produce a rupee figure), per-source freshness TTLs, and a dealer quote teardown.

**Reports** — generated PDF tax reports and a downloadable "evidence pack" carrying the citation ledger behind every figure it contains.

**Security** — JWT access tokens (15 min) with single-use refresh-token rotation and reuse-detection revocation, bcrypt password hashing, per-user/IP rate limiting, and DPDP Act 2023 controls (consent notice/grant/withdraw, a data-access endpoint, retention policy, PII-redacting logs) — see [Security & compliance](#security--compliance).

---

## Agents

Agents fall into two groups: the **pipeline** (drafts and reviews explanations of core-computed figures) and **domain agents** (one per capability, invoked by intent).

### Pipeline

| Module | Role |
|---|---|
| `analyst.py` | Drafts the answer to the standard a CA applies advising a client. Computes nothing — every figure comes from a tool result. |
| `reviewer_ca.py` | Independent file-review pass: is the draft right and complete against the same tool results? |
| `reviewer_risk.py` | Independent risk pass: what would a tax-department assessment query about this? Can annotate, never edit a figure. |
| `review_protocol.py` | The graded verdict contract (clean / amend / flag / block) that both reviewers speak. |
| `pipeline.py` | Wires draft → review → (redraft → review) → answer, with a WITHHELD state if a redraft is still blocked. |
| `intent_bridge.py` | Maps a detected intent to the right `backend.core` computation(s) and feeds the results into the pipeline. |
| `freshness.py` | Checks cached source freshness at answer time — never re-fetches over the network on the request path. |
| `base_agent.py` | Shared `BaseAgent` / `AgentOutput` contract every agent implements. |

### Domain agents

| Module | Capability |
|---|---|
| `advanced_calculator.py` | Multi-income-source tax calculation with database-persisted history. |
| `tax_optimizer.py` | Tax-saving strategies, priced against each scheme's real statutory limit — never a flat-rate guess. |
| `tax_strategy.py` | Long-term planning, regime-transition modelling, harvesting strategy. |
| `tax_agent.py` | Deductible-expense identification and savings estimation. |
| `deduction_hunter.py` | Finds deductions from user context and the knowledge base. |
| `income_classifier.py` | Classifies income sources (salary, freelance, passive, investment, etc.). |
| `benefits_discovery.py` | Ranks applicable government schemes against the user's real profile. |
| `eligibility_verifier.py` | Verifies eligibility for a specific scheme — requirements, documents, deadlines. |
| `compliance_checker.py` | Compliance score, audit readiness, red flags, document completeness. |
| `itr_helper.py` | ITR form recommendation and step-by-step filing guidance. |
| `cross_border_tax.py` | Foreign income, DTAA, residential status, foreign-asset disclosure. |
| `wealth_planner.py` | Long-term wealth and retirement planning integrated with Indian tax law. |
| `price_intelligence.py` | Cost-inflation indexation and purchase-timing signals for the procurement advisor. |

---

## Tools

Agents never touch `backend.core`, the database, or the network directly — they call named tools through `ToolExecutor` (`backend/tools/registry.py`), which validates every result before it reaches an agent. 33 tools across 12 categories:

| Category | Tools |
|---|---|
| Calculation | `calculate_tax_liability`, `calculate_deduction_impact`, `estimate_tax_refund`, `calculate_capital_gains_tax`, `calculate_capital_gains`, `calculate_hra_exemption`, `calculate_professional_tax` |
| Database | `get_user_profile`, `get_user_income_history`, `get_user_deductions`, `get_user_investments`, `save_analysis`, `save_recommendation`, `get_analysis_history`, `update_user_data` |
| Schemes | `get_scheme_details`, `search_schemes`, `get_applicable_schemes`, `check_scheme_eligibility` |
| Search | `search_latest_tax_rules`, `search_government_schemes`, `get_tax_deadlines` |
| Reports | `generate_tax_report`, `generate_deduction_report`, `generate_optimization_report` |
| Notifications | `send_email`, `send_sms`, `create_reminder` |
| Export | `export_to_excel`, `export_to_pdf` |
| Alerts | `generate_tax_saving_alerts`, `check_upcoming_deadlines` |
| Financial API | `fetch_live_market_data`, `fetch_bank_statements` |
| Government portal | `verify_pan_details`, `fetch_form_26as_statement` |
| Document parsing | `parse_investment_receipt`, `parse_form16` |
| RAG / search | `semantic_search_tax_kb`, `web_search_tavily` |

`calculation.py` is a thin adapter over `backend/core/tax_engine` — every number it returns is traceable back to a rule pack, not computed in the tool itself.

---

## Frontend

| Route | Page | Notes |
|---|---|---|
| `/` | Landing | Public marketing page |
| `/dashboard` | Dashboard | Tax position summary, financial health score, AI-generated savings suggestions (real, from `tax_optimizer_agent`) |
| `/assistant` | AI Assistant | General-purpose chat across the full agent roster |
| `/tax-analysis` | Tax Analysis | Slab breakdown, what-if calculator, regime comparison |
| `/smart-savings` | Smart Savings | Savings strategies + the purchase-advisor chat |
| `/benefits` | Benefits & Schemes | Ranked government scheme discovery |
| `/compliance` | Compliance | Compliance score, red flags, audit readiness |
| `/itr-guide` | ITR Filing Guide | Form recommendation, step-by-step filing |
| `/health-score` | Health Score | Financial health scoring and trends |
| `/reports` | Reports | Generated PDF reports |
| `/settings` | Settings | Notification preferences |
| `/profile` | Profile | Financial profile (income, deductions, investments) |
| `/login`, `/register`, `/forgot-password` | Auth | JWT-based auth flows |

The API client (`src/api/client.ts`) is the single fetch-based client for the whole app — it handles silent access-token refresh on a 401 (single-flight, so concurrent requests don't each trigger their own refresh) and broadcasts auth state changes via `window` events that `useAuthStore` listens for, since the client can't import the store directly without a circular import back through the service layer.

---

## Project structure

```
finsage_ai/
├── backend/
│   ├── api/              FastAPI routers (one per resource area)
│   ├── orchestrator/     intent detection, the pipeline bridge, parallel fan-out
│   ├── agents/            pipeline + domain agents (see §Agents)
│   ├── tools/             ToolExecutor registry (see §Tools)
│   ├── core/               pure tax engine — rules, tax_engine, eligibility,
│   │                        provenance, costing (see §Architecture)
│   ├── services/          report generation, health scoring, notifications,
│   │                        scheduler, the shared user-context builder
│   ├── db/                 SQLAlchemy models + Alembic migrations
│   ├── security/          JWT, sessions/refresh rotation, password hashing
│   ├── compliance/dpdp/   consent records (DPDP Act 2023)
│   ├── vault/              encrypted document storage
│   ├── rag/                embeddings, vector store, retriever
│   ├── procurement/       tiered source gathering, landed-cost fetchers
│   ├── observability/     logging, Prometheus metrics
│   ├── middleware/         rate limiting, error handling
│   ├── evals/               agent eval harness + numeric_provenance scorer
│   └── tests/               integration-style API tests
├── frontend/
│   └── src/
│       ├── pages/          one file per route
│       ├── components/    shared UI, per-feature components
│       ├── api/             client.ts (fetch + refresh) + services.ts
│       ├── store/           Zustand stores (auth, profile, UI)
│       └── hooks/           useApiData — per-endpoint data fetching
├── docs/                  DPDP register/controls, deployment runbook, plan
├── scripts/               phase_gate.sh, gen_progress.py, verify_freshness.py
├── docker/                 Dockerfiles for backend + frontend
├── feature.json           source of truth for what's built and verified
└── PROGRESS.md            generated from feature.json — never hand-edited
```

---

## Getting started

### Prerequisites

- Python 3.12
- Node.js 20+
- PostgreSQL 15, Redis, Qdrant — or just use Docker Compose for these
- A [Groq API key](https://console.groq.com) (LLM calls)

### Try the core engine standalone

No services required — the tax engine has zero I/O:

```python
from backend.core.provenance import rupees
from backend.core.tax_engine import TaxInput, compute_tax

r = compute_tax(TaxInput(fy="2026-27", regime="new", salary=rupees(1_275_000), age=34))
print(r.total_tax)       # ₹0 — s.87A rebate + standard deduction
print(r.trace.render())  # the worksheet, line by line
```

### Full stack, manual setup

```bash
python3 -m venv senv && source senv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp env.example .env      # fill in GROQ_API_KEY, POSTGRES_URL, JWT_SECRET_KEY, etc.

# Postgres / Redis / Qdrant, if not already running locally
docker-compose up -d postgres redis qdrant

alembic upgrade head      # apply migrations

uvicorn backend.main:app --reload --port 8001

cd frontend
npm install
npm run dev                # http://localhost:5173, proxies /api and /ws to :8001
```

### Full stack, Docker Compose

```bash
cp env.example .env
docker-compose up -d
# backend  → http://localhost:8000
# frontend → http://localhost:80
```

---

## Configuration

All configuration is environment variables; see [`env.example`](env.example) for the complete, commented template. The main groups:

| Group | Key variables |
|---|---|
| App | `ENVIRONMENT`, `DEBUG`, `LOG_LEVEL`, `ALLOWED_ORIGINS` |
| Database | `POSTGRES_URL`, `POSTGRES_POOL_SIZE` |
| Redis | `REDIS_URL`, `REDIS_DB` |
| Qdrant | `QDRANT_URL`, `QDRANT_API_KEY` |
| LLM | `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_TEMPERATURE`, `GROQ_MAX_TOKENS` |
| Web search | `SEARCH_TAVILY_API_KEY`, `SEARCH_SERPER_API_KEY` |
| Auth | `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 15), `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (default 7) |
| Email | `EMAIL_SMTP_HOST`, `EMAIL_RESEND_API_KEY` |
| Document vault | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_BUCKET_NAME`, `AWS_REGION` (or `AWS_ENDPOINT_URL` for local MinIO) |

`backend/security/startup.py` refuses to boot with a default/dev secret in a non-development environment — there is no way to accidentally ship `JWT_SECRET_KEY=your-super-secret-key-change-in-production`.

---

## Running it

| What | Command |
|---|---|
| Backend, dev (auto-reload) | `uvicorn backend.main:app --reload --port 8001` |
| Frontend, dev | `cd frontend && npm run dev` (port 5173, proxies to :8001) |
| Full stack | `docker-compose up -d` |
| New migration | `alembic revision --autogenerate -m "..."` |
| Apply migrations | `alembic upgrade head` |

---

## Testing

Four backend layers, each a CI gate, plus the frontend suite:

| Layer | What it proves | Where |
|---|---|---|
| 1 · Golden | Specific verified numbers, each case citing where it was checked | `backend/core/tests/golden/` |
| 2 · Property | Invariants over all inputs — monotonicity, marginal-relief bounds, trace replay | `backend/core/tests/properties/` |
| 3 · Evals | Agents faithfully report what the tools returned (`numeric_provenance`) | `backend/evals/` |
| 4 · Contract | API shape, migrations, load | `tests/` |

```bash
# Full local gate: registry check, lint, layering, all four test layers
./scripts/phase_gate.sh

# Backend suite directly
pytest backend/ -q

# Architectural boundaries
lint-imports --config .importlinter

# Frontend
cd frontend
npm run test          # Vitest
npx tsc --noEmit       # type check
npm run lint           # oxlint
npm run build          # production build
```

Layer 2 earns its keep: the naive invariant "post-tax income is monotonic in income" fails at ₹50L, ₹1cr and ₹2cr — not from a bug, but because cess applies *after* marginal relief, so the all-in marginal rate inside a relief zone is exactly 104%. The suite asserts what relief actually guarantees, not the intuitive-but-wrong version.

---

## API reference

All routes are prefixed `/api/v1` unless noted. Auth uses a `Bearer` JWT access token; `/auth/refresh` rotates it via an httpOnly-eligible refresh token.

| Router | Prefix | Endpoints |
|---|---|---|
| `auth` | `/auth` | `POST /register`, `POST /login`, `POST /refresh`, `POST /logout`, `GET /me` |
| `profile` | `/profile` | `GET`, `POST` — the financial profile every agent reads from |
| `chat` | `/chat` | `POST /query` (routes through the pipeline or the legacy orchestrator by intent), `GET /health`, `GET /tools` |
| `suggestions` | `/suggestions` | `POST` — `tax_optimizer_agent` savings strategies |
| `benefits` | `/benefits` | `POST /discover`, `POST /verify-eligibility`, `GET /schemes` |
| `compliance` | `/compliance` | `POST /report`, `POST /filing`, `POST /calculator`, `GET /audit-history`, `GET /itr-status` |
| `reports` | `/reports` | `POST /generate`, `POST /health-score`, `GET /list` |
| `knowledge` | `/knowledge` | `POST /upload`, `GET /stats`, `GET /health` — RAG document ingestion |
| `notifications` | `/notifications` | `POST /preferences`, `GET /preferences`, `GET /history` |
| `consent` | `/` | `GET /consent/notice`, `GET /consent/status`, `POST /consent/grant`, `POST /consent/withdraw`, `GET /me/data` |
| `websocket` | `/ws` | `WS /agent-stream/{conversation_id}`, `GET /connections-count` |

Interactive OpenAPI docs are served at `/docs` (Swagger UI) and `/redoc` when the backend is running in development.

---

## Security & compliance

**Authentication.** JWT access tokens (15-minute expiry) with single-use refresh-token rotation: each refresh issues a new token pair and invalidates the old one, and reuse of an already-rotated refresh token revokes the entire session family — a stolen-and-reused token is detected, not just rejected. Passwords are hashed with bcrypt. `backend/security/startup.py` audits secrets at boot and refuses to start with a placeholder secret outside development.

**Rate limiting.** Per-user and per-IP limits at the ASGI layer, Redis-backed so limits hold across replicas.

**DPDP Act 2023.** Handling income and PAN data makes this product a Data Fiduciary under the Act. What's actually implemented, tracked obligation-by-obligation in [`docs/dpdp_controls.md`](docs/dpdp_controls.md) (status read literally: `implemented` / `partial` / `not started`, not marked done because it's planned):

- Itemised, versioned consent notice per purpose; consent is invalidated if the notice text changes (`GET /consent/notice`, `POST /consent/grant`)
- Withdrawal as easy as granting, same request shape (`POST /consent/withdraw`); processing stops immediately on withdrawal
- Stated, per-purpose retention periods (`docs/dpdp_register.md`)
- A data-access endpoint (`GET /me/data`) covering account, profile, and consent-ledger data
- PII-redacting log formatter (PAN, GSTIN, Verhoeff-checked Aadhaar, email, phone never reach logs)
- An encrypted, S3-backed document vault
- What's explicitly **not** claimed: no DPIA, no independent audit, no appointed grievance/DPO ticketing flow, no age gate for under-18 users, and erasure isn't yet wired through the document vault and vector store — see the doc for the full gap list.

**Regulatory positioning.** This is a tax computation and information tool, not investment advice — personalised investment advice in India is SEBI-regulated (Investment Adviser Regulations, 2013), and outputs are deliberately framed as the tax treatment of instrument categories rather than product recommendations.

---

## Project status & roadmap

`feature.json` is the single source of truth for what exists; `PROGRESS.md` is generated from it and should never be hand-edited. A feature counts as complete only at status `verified` — its legal basis confirmed against an official source, with the date recorded. Anything below that is work in flight, and the README does not claim it.

```bash
python scripts/gen_progress.py            # regenerate PROGRESS.md
python scripts/gen_progress.py --check    # CI: fail if stale or invalid
python scripts/verify_freshness.py        # CI: fail if a shipped tax rule has decayed
```

**Tax rules are perishable.** `verify_freshness.py` fails the build when a rule pack backing a shipped feature is more than 180 days past its last verification date — an earlier version of this codebase went two years stale in seven files at once with nothing objecting.

As of this writing: **91% (69/76) verified**, **44/47 P0 (release-blocking) features verified**. What's still in flight:

| Item | State |
|---|---|
| `AGT-001` Thin-agent refactor | in progress — 5 legacy agent modules still carry a shrinking, CI-enforced budget of money-arithmetic sites rather than zero |
| `AGT-005` Eval scenario corpus | in progress |
| `AGT-007` Real WebSocket token-level agent streaming | implemented at the transport level; agents don't yet emit token-level reasoning into it |
| `DEM-005` Async LLM client | implemented (`AsyncGroq`, no blocking calls); not yet verified against the p95-under-load acceptance criterion |
| `PRD-006` Deployment & operations | implemented; not yet verified |
| `PRD-007` Load & resilience testing | tested; not yet verified at target concurrency |

Full detail, including every verified feature's legal source and verification date, is in [`PROGRESS.md`](PROGRESS.md).

---

## Known limitations

- **Section citations (`CORE-002`).** The 1961 → 2025 Act section-alias map is loaded and used, but not yet verified against the published concordance — new-Act section numbers render as provisional rather than asserted.
- **A handful of agents still do their own arithmetic.** `test_no_agent_arithmetic.py` tracks this explicitly as a ratchet (can only shrink) rather than hiding it; see that file for the current per-module count.
- **Agent reasoning isn't streamed token-by-token yet** — the WebSocket transport exists; what flows over it isn't real-time model output.
- **This is not tax advice.** It's a computation tool with its working shown, built so a chartered accountant can check it. Verify any figure against incometax.gov.in or a qualified CA before filing or acting on it.

---

## Contributing / development conventions

- **Adding a financial year** is data, not code: one new `backend/core/rules/fy_YYYY_YY.yaml` plus a golden-test file. No Python changes.
- **Layering is enforced, not advisory.** `api → orchestrator → agents → tools → core`, checked by `lint-imports --config .importlinter` in CI and locally.
- **No agent computes tax arithmetic.** Route through `backend/tools/calculation.py` (which itself is a thin adapter over `backend/core`). `test_no_agent_arithmetic.py` catches a regression before review does.
- **`feature.json` before code.** A feature is `verified` only once its legal basis is confirmed against an official source and the date is recorded — not once the code merges.
- Run `./scripts/phase_gate.sh` before opening a PR; it's the same gate CI runs.

---

## License

No `LICENSE` file is currently present in this repository. In the absence of one, all rights are reserved by default — add a `LICENSE` file if you intend to open-source this project under a specific license (MIT, Apache-2.0, etc.).
