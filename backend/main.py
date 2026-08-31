"""
FinSage AI — FastAPI Application
Main entry point for the backend.
Run with: uvicorn backend.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.deduction_hunter import DeductionHunterAgent
from backend.agents.income_classifier import IncomeClassifierAgent
from backend.agents.tax_optimizer import TaxOptimizerAgent
from backend.api import knowledge
from backend.config import settings
from backend.logging_config import setup_logging
from backend.security.startup import enforce

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Handles database and external service initialization.
    """
    # Startup
    logger.info(f"🚀 Starting {settings.app_name}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug: {settings.debug}")

    # ── Configuration audit — PRD-005 ─────────────────────────────────
    # BEFORE anything else, and before a single request is served. An app
    # that boots on a placeholder JWT secret and then serves traffic is
    # authenticating nobody; failing here names the variable and is diagnosed
    # in ten seconds instead of never.
    enforce(settings)

    # ── Startup Health Checks ─────────────────────────────────────────
    logger.info("🔍 Running startup health checks...")

    # Check Groq API key
    if settings.llm.api_key and settings.llm.api_key != "":
        logger.info("✅ Groq API key configured")
    else:
        logger.warning("⚠️ Groq API key missing — LLM features will not work")

    # Check Tavily API key
    import os
    tavily_key = os.getenv("SEARCH_TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY")
    if tavily_key and not tavily_key.startswith("your_"):
        logger.info("✅ Tavily API key configured — live web search enabled")
    else:
        logger.warning("⚠️ Tavily API key missing — using fallback mock search")

    # Check Redis connectivity
    try:
        from backend.db.redis_client import get_redis
        redis_client = await get_redis()
        if redis_client:
            await redis_client.ping()
            logger.info("✅ Redis connected")
        else:
            logger.warning("⚠️ Redis not available — caching disabled")
    except Exception as redis_err:
        logger.warning(f"⚠️ Redis connection failed: {redis_err} — caching disabled")

    # Check Qdrant connectivity
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.qdrant.url}/collections")
            if resp.status_code == 200:
                logger.info("✅ Qdrant vector DB connected")
            else:
                logger.warning(f"⚠️ Qdrant returned status {resp.status_code} — RAG search may not work")
    except Exception as qdrant_err:
        logger.warning(f"⚠️ Qdrant not reachable: {qdrant_err} — RAG search will use fallback")

    logger.info("🔍 Health checks complete")

    # DEM-007: the ALTER TABLE that used to run here is gone.
    #
    # It executed `ADD COLUMN IF NOT EXISTS profile_data JSONB` on EVERY
    # startup, while Alembic sat beside it with three revisions. With more than
    # one replica booting at once those statements race, and schema drift
    # becomes invisible because the app repairs it silently on restart.
    #
    # Alembic owns the schema. Run `alembic upgrade head` as a deploy step.
    from backend.db.postgres import get_engine
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            from sqlalchemy import text as _sql
            row = await conn.execute(_sql("SELECT 1"))
            row.scalar()
        logger.info("Database reachable")
    except Exception as db_err:
        logger.error(f"Database unreachable at startup: {db_err}")

    # Initialize tool components
    from backend.orchestrator.graph import AsyncSessionProxy
    from backend.tools.calculation import TaxCalculationEngine
    from backend.tools.database import DatabaseToolFactory
    from backend.tools.registry import ToolExecutor
    from backend.tools.reports_notifications import (
        ExportTool,
        NotificationTool,
        ReportGenerationTool,
    )
    from backend.tools.schemes_search import SchemeLookupTool, WebSearchTool

    logger.info("🔧 Initializing tools...")
    db = AsyncSessionProxy()
    calc_engine = TaxCalculationEngine()
    db_factory = DatabaseToolFactory(db)
    db_tools = db_factory.create_tools()

    scheme_tools = SchemeLookupTool()
    search_tools = WebSearchTool()
    report_tools = ReportGenerationTool()
    notification_tools = NotificationTool()
    export_tools = ExportTool()

    global tool_executor
    tool_executor = ToolExecutor(
        calculation_engine=calc_engine,
        database_tools=db_tools,
        scheme_tools=scheme_tools,
        search_tools=search_tools,
        report_tools=report_tools,
        notification_tools=notification_tools,
        export_tools=export_tools
    )
    logger.info(f"✅ Tools initialized ({len(tool_executor.list_tools())} tools available)")

    # Initialize orchestrator with tools
    from backend.orchestrator.graph import init_orchestrator
    await init_orchestrator(tools=tool_executor)

    # Initialize intent detector in chat.py
    import backend.api.chat as chat_module
    from backend.orchestrator.intent_detector import IntentDetector
    chat_module.intent_detector = IntentDetector()

    # Register agents
    from backend.agents.tax_agent import TaxDeductionAgent
    from backend.api.chat import orchestrator

    tax_agent = TaxDeductionAgent()
    orchestrator.register_agent("tax_deduction_agent", tax_agent)

    income_agent = IncomeClassifierAgent()
    orchestrator.register_agent("income_classifier_agent", income_agent)

    deduction_agent = DeductionHunterAgent()
    orchestrator.register_agent("deduction_hunter_agent", deduction_agent)

    optimizer_agent = TaxOptimizerAgent()
    orchestrator.register_agent("tax_optimizer_agent", optimizer_agent)

    from backend.agents.benefits_discovery import BenefitsDiscoveryAgent
    benefits_agent = BenefitsDiscoveryAgent()
    orchestrator.register_agent("benefits_discovery_agent", benefits_agent)

    from backend.agents.eligibility_verifier import EligibilityVerifierAgent
    verifier_agent = EligibilityVerifierAgent()
    orchestrator.register_agent("eligibility_verifier_agent", verifier_agent)

    from backend.agents.compliance_checker import ComplianceCheckerAgent
    compliance_agent = ComplianceCheckerAgent()
    orchestrator.register_agent("compliance_checker_agent", compliance_agent)

    from backend.agents.itr_helper import ITRHelperAgent
    itr_agent = ITRHelperAgent()
    orchestrator.register_agent("itr_helper_agent", itr_agent)

    from backend.agents.advanced_calculator import AdvancedCalculatorAgent
    calculator_agent = AdvancedCalculatorAgent()
    orchestrator.register_agent("advanced_calculator_agent", calculator_agent)

    from backend.agents.cross_border_tax import CrossBorderTaxAgent
    cross_border_tax_agent = CrossBorderTaxAgent()
    orchestrator.register_agent("cross_border_tax_agent", cross_border_tax_agent)

    from backend.agents.price_intelligence import PriceIntelligenceAgent
    price_intelligence_agent = PriceIntelligenceAgent()
    orchestrator.register_agent("price_intelligence_agent", price_intelligence_agent)

    from backend.agents.tax_strategy import TaxStrategyAgent
    tax_strategy_agent = TaxStrategyAgent()
    orchestrator.register_agent("tax_strategy_agent", tax_strategy_agent)

    from backend.agents.wealth_planner import WealthPlannerAgent
    wealth_planner_agent = WealthPlannerAgent()
    orchestrator.register_agent("wealth_planner_agent", wealth_planner_agent)


    # Initialize India Tax Data Fetcher
    from backend.services.india_tax_data_fetcher import get_india_tax_data
    await get_india_tax_data()
    logger.info("🇮🇳 India Tax Data Fetcher initialized in lifespan")

    # Initialize Step 10 Scheduler
    from backend.services.scheduler import init_scheduler
    scheduler_result = init_scheduler()
    if scheduler_result["success"]:
        logger.info(f"✅ Scheduler initialized with {scheduler_result['jobs_scheduled']} jobs")
    else:
        logger.error(f"❌ Failed to initialize scheduler: {scheduler_result.get('error')}")

    logger.info(f"Registered agents: {list(orchestrator.agents.keys())}")

    yield

    # Shutdown
    logger.info("🛑 Shutting down FinSage AI")

    # Shutdown scheduler
    from backend.services.scheduler import get_scheduler
    scheduler = get_scheduler()
    if scheduler:
        scheduler.shutdown_scheduler()
        logger.info("✅ Scheduler shut down successfully")

    # Close database connection pool
    from backend.db.postgres import close_db
    await close_db()
    logger.info("✅ Database connections closed")

    # Close Redis connection
    from backend.db.redis_client import close_redis
    await close_redis()
    logger.info("✅ Redis connection closed")


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.app_name,
    description="Intelligent Financial Optimization & Government Benefits Discovery",
    version=settings.api_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# DEM-008: correlation ids in, raw exception text out.
from backend.middleware.errors import install_error_handlers

install_error_handlers(app)

# PRD-003: per-user and per-IP token buckets. Added before CORS so CORS ends
# up outermost and still decorates a 429 with the right headers — otherwise a
# browser client sees an opaque CORS failure instead of "too many requests".
from backend.middleware.asgi_ratelimit import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)

# PRD-004: request metrics and the scrape endpoint. Added AFTER the rate
# limiter so it ends up OUTSIDE it — a request refused with 429 is still a
# request, and a limiter that starts rejecting everything must show up as
# traffic rather than as silence.
from backend.middleware.metrics import install as install_metrics
from backend.observability import metrics as _metrics


def _rules_version() -> str:
    """Which rule pack this process is serving.

    On the build_info gauge rather than in a log line, so that a dashboard
    showing a change in withheld answers can be correlated with the rule pack
    that changed underneath it — the question "did our numbers move because
    the law moved?" is otherwise unanswerable after the fact.
    """
    try:
        from datetime import date

        from backend.core.rules import fy_for_date, load_ruleset

        return load_ruleset(fy_for_date(date.today())).version
    except Exception:  # noqa: BLE001 — never block startup for a label
        return "unknown"


install_metrics(
    app,
    token=settings.metrics.token,
    is_production=settings.is_production,
)
_metrics.set_build_info(
    version=settings.api_version,
    rules_version=_rules_version(),
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
from backend.api import auth, benefits, chat, compliance, consent, notifications, profile, reports, suggestions, websocket

app.include_router(auth.router, tags=["Authentication"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(websocket.router, tags=["WebSocket"])
app.include_router(knowledge.router, tags=["Knowledge Base"])
app.include_router(benefits.router)
app.include_router(compliance.router)
app.include_router(consent.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(profile.router)
app.include_router(suggestions.router, tags=["Suggestions"])


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.app_name}",
        "docs": "/docs" if settings.debug else "Not available",
        "health": "/health",
    }


# Global tool executor (populated in lifespan startup)
tool_executor = None


if __name__ == "__main__":
    import uvicorn
    # Trigger reload
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
