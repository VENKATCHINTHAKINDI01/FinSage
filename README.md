# FinSage AI

**Intelligent Financial Optimization & Government Benefits Discovery Platform**

India-first, AI-powered platform that helps individuals and businesses optimize taxes, discover government benefits, and make smarter financial decisions.

---

## ✨ Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15
- Redis 7
- Docker & Docker Compose (recommended)

### 1. Clone & Setup

```bash
git clone <repo-url>
cd finsage_ai
cp .env.example .env
```

### 2. Fill in `.env` with API Keys

Required:
- `GROQ_API_KEY` from [console.groq.com](https://console.groq.com)
- `SEARCH_TAVILY_API_KEY` from [tavily.com](https://tavily.com)
- `TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/BotFather)

### 3. Start Services (Docker Compose)

```bash
docker-compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Qdrant (port 6333)
- FastAPI backend (port 8000)
- Telegram bot

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 5. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### 6. Start Backend

```bash
uvicorn backend.main:app --reload
```

Backend running at: http://localhost:8000  
API docs: http://localhost:8000/docs

### 7. Start Frontend (Phase 2)

```bash
cd frontend
npm install
npm run dev
```

Frontend at: http://localhost:5173

---

## 📁 Project Structure

```
finsage_ai/
├── backend/              # FastAPI application
│   ├── api/             # Route handlers
│   ├── agents/          # AI agents (LangGraph)
│   ├── tools/           # Agent tools & utilities
│   ├── models/          # Pydantic data models
│   ├── db/              # Database layer
│   ├── services/        # Business logic
│   └── security/        # Auth & encryption
├── frontend/            # React + Vite dashboard
├── telegram_bot/        # Telegram bot interface
├── ingestion/           # Data ingestion jobs
└── docker/              # Docker configurations
```

---

## 🚀 Development Phases

### Phase 1 (Weeks 1–3): Core Platform ✅ IN PROGRESS
- [x] Config & project bootstrap
- [ ] Database layer
- [ ] Auth system
- [ ] FastAPI core + WebSocket
- [ ] RAG pipeline
- [ ] First 2 agents (Income Classifier, Deduction Hunter)
- [ ] LangGraph orchestrator
- [ ] Govt Benefits agent + live search
- [ ] Tax Strategy & Compliance agents
- [ ] Report generation & Health Score

### Phase 2 (Weeks 4–6): Full Suite
- All 12 agents
- Investment optimizer with portfolio analysis
- GST module for businesses
- Document vault
- Proactive alert engine

### Phase 3 (Weeks 7–12): Intelligence
- WhatsApp integration
- Voice financial advisor
- Startup India dedicated agent
- Personal Wealth Twin

---

## 🔐 Security

- JWT-based authentication
- AES-256 encryption for document vault
- DPDP Act 2023 & GDPR compliant
- Audit trail for all recommendations
- Role-based access control (RBAC)

---

## 📊 API Endpoints (Phase 1)

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/register` | User signup |
| `POST` | `/api/v1/auth/login` | User login |
| `POST` | `/api/v1/chat/query` | Submit financial query |
| `WS` | `/ws/agent-stream/{session_id}` | Live agent activity stream |
| `GET` | `/api/v1/reports` | Get generated reports |
| `GET` | `/api/v1/schemes` | Browse govt schemes |
| `GET` | `/health` | Health check |

---

## 🛠 Tech Stack

| Layer | Tools |
|---|---|
| LLM | Groq — Llama 3.3 70B |
| Agents | LangGraph |
| Backend | FastAPI, SQLAlchemy, Pydantic |
| Databases | PostgreSQL, Redis, Qdrant |
| Frontend | React, Vite, TailwindCSS |
| Search | Tavily, Serper |

---

## 📚 Documentation

- [API Reference](./docs/api_reference.md)
- [Agent Design](./docs/agent_design.md)
- [RAG Pipeline](./docs/rag_pipeline.md)
- [Deployment](./docs/deployment.md)

---

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -m "Add feature"`
3. Push to branch: `git push origin feature/your-feature`
4. Open a Pull Request

---

## 📄 License

MIT License — see LICENSE file for details

---

## 📞 Support

- 📧 Email: support@finsage.ai
- 🤖 Telegram: [@finsageai_bot](https://t.me/finsageai_bot)
- 💬 Discord: [FinSage Community](#)

---

**Built with ❤️ for smarter financial decisions**