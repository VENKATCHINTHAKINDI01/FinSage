"""
FinSage AI — FastAPI Application
Main entry point for the backend.
Run with: uvicorn backend.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from backend.config import settings
from backend.api import knowledge
from backend.agents.income_classifier import IncomeClassifierAgent
from backend.agents.deduction_hunter import DeductionHunterAgent
from backend.agents.tax_optimizer import TaxOptimizerAgent


from backend.logging_config import setup_logging

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
    
    # Initialize tool components
    from backend.orchestrator.graph import AsyncSessionProxy
    from backend.tools import ToolExecutor
    from backend.tools.calculation import TaxCalculationEngine
    from backend.tools.database import DatabaseToolFactory
    from backend.tools.schemes_search import SchemeLookupTool, WebSearchTool
    from backend.tools.reports_notifications import (
        ReportGenerationTool,
        NotificationTool,
        ExportTool
    )
    
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
    
    logger.info(f"Registered agents: {list(orchestrator.agents.keys())}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down FinSage AI")
    # TODO: Close database pool
    # TODO: Close Redis connection
    # TODO: Close Qdrant connection


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.app_name,
    description="Intelligent Financial Optimization & Government Benefits Discovery",
    version=settings.api_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
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
from backend.api import auth, chat, websocket, benefits, compliance

app.include_router(auth.router, tags=["Authentication"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(websocket.router, tags=["WebSocket"])
app.include_router(knowledge.router, tags=["Knowledge Base"])
app.include_router(benefits.router)
app.include_router(compliance.router)
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


# TODO: Import and include routers
# from backend.api import auth, chat, reports, schemes, documents, websocket
# app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
# app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
# app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])
# app.include_router(schemes.router, prefix="/api/v1", tags=["Schemes"])
# app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])


# Tools initialization
from backend.tools import ToolExecutor
from backend.tools.calculation import TaxCalculationEngine
from backend.tools.database import DatabaseToolFactory
from backend.tools.schemes_search import SchemeLookupTool, WebSearchTool
from backend.tools.reports_notifications import (
    ReportGenerationTool,
    NotificationTool,
    ExportTool
)

# Global tool executor
tool_executor = None

async def get_db():
    from backend.orchestrator.graph import AsyncSessionProxy
    yield AsyncSessionProxy()

@app.on_event("startup")
async def init_tools():
    global tool_executor
    
    logger.info("🔧 Initializing tools...")
    
    # Get database session
    async for db in get_db():
        break
    
    # Initialize tool components
    calc_engine = TaxCalculationEngine()
    
    db_factory = DatabaseToolFactory(db)
    db_tools = db_factory.create_tools()
    
    scheme_tools = SchemeLookupTool()
    search_tools = WebSearchTool()
    report_tools = ReportGenerationTool()
    notification_tools = NotificationTool()
    export_tools = ExportTool()
    
    # Create unified tool executor
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
    
    # Initialize India Tax Data Fetcher
    from backend.services.india_tax_data_fetcher import get_india_tax_data
    await get_india_tax_data()
    logger.info("🇮🇳 India Tax Data Fetcher initialized in startup event")





if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )