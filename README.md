# 🧠 FinSage AI

> **Intelligent Financial Optimization & Government Benefits Discovery Platform**  
> India-first, AI-powered platform that helps individuals and businesses optimize taxes, discover government benefits, and make smarter financial decisions — powered by Groq Llama 3.3 70B and a 12-agent LangGraph orchestration system.

---

## ✨ Features

- 🤖 **12 Specialized AI Agents** — Income classification, deduction hunting, ITR filing, compliance checking, cross-border tax, wealth planning, and more
- 🏛️ **Government Benefits Discovery** — Matches you to eligible Central & State schemes
- 📊 **Financial Health Score** — 5-factor scoring across tax efficiency, savings, compliance, investments, and deduction optimization
- 📄 **Report Generation** — PDF/HTML tax summaries and financial health reports
- 🔔 **Smart Notifications** — Scheduled email alerts for deadlines, tips, and reviews
- 🔐 **Secure Auth** — JWT-based authentication with AES-256 encryption
- ⚡ **Real-time Streaming** — WebSocket live-streaming of agent reasoning

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      React + Vite Frontend                   │
│  Dashboard │ Tax Analysis │ Compliance │ Reports │ Settings  │
└─────────────────────────────────────────────────────────────┘
                            │ REST + WebSocket
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Port 8000)              │
│  /api/v1/auth  │  /api/v1/chat  │  /api/v1/compliance       │
│  /api/v1/reports │ /api/v1/benefits │ /api/v1/notifications  │
│  /ws/agent-stream/{id}                                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│               LangGraph Agent Orchestrator                   │
│  IntentDetector → AgentRouter → 12 Specialized Agents       │
└─────────────────────────────────────────────────────────────┘
           │                    │                    │
    ┌──────▼──────┐   ┌─────────▼──────┐   ┌───────▼──────┐
    │ PostgreSQL  │   │   Qdrant RAG   │   │    Redis     │
    │  (data)     │   │  (knowledge)   │   │   (cache)    │
    └─────────────┘   └────────────────┘   └──────────────┘
```

---

## 🤖 Agent Catalog

| Agent | Intent | Description |
|---|---|---|
| `IncomeClassifierAgent` | `FINANCIAL_PLANNING` | Classifies salary, business, rental, capital gains |
| `DeductionHunterAgent` | `TAX_DEDUCTION` | Finds all applicable 80C/D/E/G deductions |
| `TaxOptimizerAgent` | `TAX_SAVINGS` | Generates tax-saving strategies |
| `BenefitsDiscoveryAgent` | `GOVERNMENT_BENEFITS` | Discovers Central & State govt schemes |
| `EligibilityVerifierAgent` | `ELIGIBILITY_CHECK` | Verifies eligibility for schemes |
| `ComplianceCheckerAgent` | `COMPLIANCE_CHECK` | Compliance score & audit readiness |
| `ITRHelperAgent` | `TAX_FILING` | ITR form selection & filing guidance |
| `AdvancedCalculatorAgent` | `TAX_CALCULATION` | Capital gains, STCG/LTCG, loss carryforward |
| `CrossBorderTaxAgent` | `CROSS_BORDER_TAX` | NRI rules, DTAA, foreign asset declaration |
| `PriceIntelligenceAgent` | `PRICE_INTELLIGENCE` | CII indexation, SGB, post-tax yield comparison |
| `TaxStrategyAgent` | `TAX_STRATEGY` | Multi-year planning, old vs new regime |
| `WealthPlannerAgent` | `WEALTH_PLANNING` | NPS/PPF retirement, Section 54/54EC |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | Groq — Llama 3.3 70B Versatile |
| **Agents** | LangGraph |
| **Backend** | FastAPI, SQLAlchemy (async), Pydantic v2 |
| **Databases** | PostgreSQL 15, Redis 7, Qdrant (vectors) |
| **Frontend** | React 19, TypeScript, Vite 8, TailwindCSS v4 |
| **Auth** | JWT (HS256), bcrypt |
| **Search** | Tavily AI, Serper |
| **Scheduler** | APScheduler |
| **Deployment** | Docker Compose |

---

## ⚙️ Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 15, Redis 7, Qdrant (or use Docker)

---

### 1. Clone the repo

```bash
git clone https://github.com/your-org/finsage_ai.git
cd finsage_ai
```

### 2. Configure environment

```bash
cp env.example .env
```

Open `.env` and fill in the required values (see [Environment Variables](#-environment-variables) below).

### 3. Option A — Docker Compose (Recommended)

Starts PostgreSQL, Redis, Qdrant, and the FastAPI backend automatically:

```bash
docker-compose up -d
```

Verify services are running:

```bash
docker-compose ps
```

### 3. Option B — Manual Setup

**Create and activate the virtual environment:**

```bash
python3 -m venv senv
source senv/bin/activate      # Linux / macOS
# OR
senv\Scripts\activate         # Windows
```

**Install Python dependencies:**

```bash
pip install -r requirements.txt
```

**Start external services (PostgreSQL, Redis, Qdrant) separately**, then:

**Run database migrations:**

```bash
cd backend
alembic upgrade head
cd ..
```

**Start the backend:**

```bash
uvicorn backend.main:app --reload --port 8000
```

Backend: http://localhost:8000  
API docs: http://localhost:8000/docs

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

> **Note:** The Vite dev server proxies all `/api/*` and `/ws/*` requests to the backend at `http://localhost:8000`, so you don't need to configure CORS manually.

---

## 🌍 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | API key from [console.groq.com](https://console.groq.com) |
| `SEARCH_TAVILY_API_KEY` | ✅ | Tavily search key from [tavily.com](https://tavily.com) |
| `TELEGRAM_BOT_TOKEN` | Optional | From [@BotFather](https://t.me/BotFather) |
| `POSTGRES_URL` | ✅ | `postgresql+asyncpg://user:pass@host:5432/finsage` |
| `REDIS_URL` | ✅ | `redis://localhost:6379` |
| `QDRANT_URL` | Optional | `http://localhost:6333` (default) |
| `JWT_SECRET_KEY` | ✅ | Random secret ≥ 32 chars |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | Default: 15 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Optional | Default: 7 |
| `EMAIL_SMTP_HOST` | Optional | SMTP host for notifications |
| `EMAIL_SENDER_EMAIL` | Optional | From address for email alerts |
| `EMAIL_RESEND_API_KEY` | Optional | [Resend](https://resend.com) API key |
| `AWS_ACCESS_KEY_ID` | Optional | For S3 document vault |
| `AWS_SECRET_ACCESS_KEY` | Optional | For S3 document vault |
| `APP_ENVIRONMENT` | Optional | `development` / `production` |
| `APP_DEBUG` | Optional | `true` / `false` |

---

## 📡 API Reference

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register new user — returns JWT tokens |
| `POST` | `/api/v1/auth/login` | Login — returns JWT tokens |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |
| `GET` | `/api/v1/auth/me` | Get current user info |

### Chat & Agents

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat/query` | Submit query → multi-agent response |
| `GET` | `/api/v1/chat/health` | Chat service health |
| `GET` | `/api/v1/chat/tools` | List available tools |
| `WS` | `/ws/agent-stream/{session_id}` | Live agent activity stream |

### Compliance

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/compliance/report` | Compliance assessment & audit readiness |
| `POST` | `/api/v1/compliance/filing` | ITR filing guidance |
| `POST` | `/api/v1/compliance/calculator` | Advanced tax calculation |
| `GET` | `/api/v1/compliance/audit-history` | Compliance history |
| `GET` | `/api/v1/compliance/itr-status` | Current FY ITR filing status |

### Reports

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/reports/generate` | Generate tax summary or health report |
| `POST` | `/api/v1/reports/health-score` | Financial health score |
| `GET` | `/api/v1/reports/list` | List all reports |

### Benefits

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/benefits/discover` | Discover applicable govt schemes |
| `POST` | `/api/v1/benefits/eligibility` | Check eligibility for a scheme |
| `GET` | `/api/v1/benefits/schemes` | Browse all schemes |

### Notifications

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/notifications/preferences` | Set notification channel preferences |
| `GET` | `/api/v1/notifications/preferences` | Get notification preferences |
| `GET` | `/api/v1/notifications/history` | Get notification history |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health check |
| `GET` | `/` | Root welcome message |
| `GET` | `/docs` | Interactive API docs (dev mode) |

---

## 📁 Project Structure

```
finsage_ai/
├── backend/                    # FastAPI application
│   ├── main.py                 # App entry point, lifespan manager, router inclusion
│   ├── config.py               # Pydantic settings (env-based config)
│   ├── logging_config.py       # Structured logging setup
│   ├── alembic.ini             # Alembic migration configuration
│   ├── api/                    # HTTP route handlers
│   │   ├── auth.py             # Register / login / refresh / me
│   │   ├── chat.py             # /api/v1/chat/query — main AI query endpoint
│   │   ├── compliance.py       # Compliance, ITR, tax calculation
│   │   ├── benefits.py         # Government schemes discovery
│   │   ├── reports.py          # Report generation & health score
│   │   ├── notifications.py    # Notification preferences & history
│   │   ├── knowledge.py        # Knowledge base management
│   │   └── websocket.py        # /ws/agent-stream WebSocket
│   ├── agents/                 # AI agents (12 total)
│   │   ├── base_agent.py       # BaseAgent class with common interface
│   │   ├── income_classifier.py
│   │   ├── deduction_hunter.py
│   │   ├── tax_optimizer.py
│   │   ├── compliance_checker.py
│   │   ├── itr_helper.py
│   │   ├── advanced_calculator.py
│   │   ├── cross_border_tax.py
│   │   ├── benefits_discovery.py
│   │   ├── eligibility_verifier.py
│   │   ├── price_intelligence.py
│   │   ├── tax_strategy.py
│   │   └── wealth_planner.py
│   ├── orchestrator/           # Multi-agent coordinator
│   │   ├── graph.py            # AgentOrchestrator — sequential execution
│   │   ├── intent_detector.py  # Groq-powered intent classification
│   │   ├── memory.py           # Conversation & semantic memory
│   │   └── advanced_orchestrator.py
│   ├── db/                     # Database layer
│   │   ├── postgres.py         # Async SQLAlchemy engine & session
│   │   ├── redis_client.py     # Redis cache & session store
│   │   ├── orm_models.py       # SQLAlchemy ORM table definitions
│   │   └── crud/               # Create/Read/Update/Delete helpers
│   ├── models/                 # Pydantic request/response schemas
│   ├── services/               # Business logic services
│   │   ├── health_scorer.py    # 5-factor financial health scoring
│   │   ├── report_generator.py # PDF/HTML report generation
│   │   ├── notification.py     # Email/Telegram/SMS notifications
│   │   ├── alert_service.py    # Red flag detection & alerts
│   │   ├── scheduler.py        # APScheduler background jobs
│   │   └── india_tax_data_fetcher.py  # Live tax data ingestion
│   ├── tools/                  # Agent tools (callable by agents)
│   │   ├── registry.py         # ToolExecutor (unified tools interface)
│   │   ├── calculation.py      # Tax calculation engine
│   │   ├── database.py         # Database read/write tools
│   │   ├── schemes_search.py   # Government schemes lookup
│   │   └── reports_notifications.py   # Report & notification tools
│   ├── rag/                    # Retrieval-Augmented Generation
│   │   ├── vector_store.py     # Qdrant vector store client
│   │   ├── embeddings.py       # Embedding model wrapper
│   │   ├── retriever.py        # Semantic search retrieval
│   │   └── document_loader.py  # PDF/text document ingestion
│   ├── security/               # Authentication & JWT
│   │   ├── jwt_handler.py      # Token creation & verification
│   │   ├── password.py         # bcrypt hashing
│   │   └── dependencies.py     # FastAPI auth dependencies
│   └── tests/                  # Pytest test suite (50 tests)
├── frontend/                   # React + Vite + TypeScript
│   ├── src/
│   │   ├── App.tsx             # Route tree (protected & public routes)
│   │   ├── pages/              # Dashboard, TaxAnalysis, Compliance, etc.
│   │   ├── components/         # Reusable UI components
│   │   ├── api/
│   │   │   ├── client.ts       # Fetch-based API client with auth header
│   │   │   └── services.ts     # All backend API calls
│   │   ├── store/              # Zustand state stores
│   │   │   ├── useAuthStore.ts # Auth state management
│   │   │   ├── useProfileStore.ts # Profile state management
│   │   │   └── useUIStore.ts   # UI layout state management
│   │   └── hooks/              # Custom React hooks
│   ├── vite.config.ts          # Vite config with /api proxy → localhost:8000
│   └── package.json
├── docker/                     # Docker service configurations
├── docker-compose.yml          # Full-stack local dev orchestration
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Python build config & linter settings
└── .env                        # Your secret keys (gitignored)
```

---

## 🐳 Docker Compose Services

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 15 database |
| `redis` | 6379 | Redis 7 cache & sessions |
| `qdrant` | 6333 | Qdrant vector database |
| `backend` | 8000 | FastAPI application |

---

## 🧪 Running Tests

```bash
# From project root
PYTHONPATH=. ./senv/bin/pytest

# With coverage
PYTHONPATH=. ./senv/bin/pytest --cov=backend --cov-report=html
```

Frontend linting and type check:

```bash
cd frontend
npm run lint      # Oxlint
npm run build     # TypeScript + Vite build (zero errors = success)
```

---

## 🔐 Security

- JWT access tokens expire in 15 minutes; refresh tokens in 7 days
- Passwords hashed with bcrypt (cost factor 12)
- All API endpoints require `Authorization: Bearer <token>` except auth routes
- AES-256 encryption available for document vault
- Audit trail for every agent recommendation (stored in `audit_logs` table)
- DPDP Act 2023 & GDPR compliance design

---

## 📅 Scheduled Jobs

The APScheduler automatically runs these background tasks:

| Job | Schedule | Description |
|---|---|---|
| Tax Deadline Reminder | July 20, 9 AM | Reminds all users 11 days before ITR deadline |
| Annual Review Reminder | April 1, 9 AM | Start-of-year financial review prompt |
| Investment Deadline | 25th of Mar/Jun/Sep/Dec | Quarterly investment deadline alerts |
| Weekly Tax Tips | Monday 10 AM | Rotating tax-saving tips via email |
| Monthly Health Report | 1st of month, 9 AM | Financial health score report email |

---

## 🚀 Deployment

### Production with Docker

```bash
# Set production env
export APP_ENVIRONMENT=production
export APP_DEBUG=false

docker-compose -f docker-compose.yml up -d

# Run migrations
docker-compose exec backend alembic upgrade head
```

### Frontend Build

```bash
cd frontend
npm run build
# Serve dist/ with nginx or any static file server
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run tests: `PYTHONPATH=. ./senv/bin/pytest`
5. Commit: `git commit -m "feat: add amazing feature"`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

---

## 📞 Support

- 📧 Email: support@finsage.ai
- 🤖 Telegram: [@finsageai_bot](https://t.me/finsageai_bot)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

**Built with ❤️ for smarter financial decisions across India**