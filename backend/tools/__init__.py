"""
Tools Module - Agent Tools Layer
================================

All tools available to agents.
"""

# DEM-006: `BusinessIncomeTaxCalculator` and `ComprehensiveTaxCalculator` were
# removed along with the rest of this module's private tax tables. Nothing
# imported either of them, and both re-derived slab tax rather than calling a
# shared engine. Business income is an income head on TaxInput; the
# "comprehensive" case is what compute_tax already does.
from .calculation import (
    CapitalGainsTaxCalculator,
    TaxCalculationEngine,
)
from .data_validator import (
    DataValidator,
    FinancialDataValidator,
    LLMResponseValidator,
    ValidationReport,
    WebDataValidator,
)
from .database import (
    AnalysisStorageTool,
    AnalysisType,
    AuditLogTool,
    DatabaseToolFactory,
    UserDataUpdateTool,
    UserFinancialDataTool,
)
from .registry import ToolExecutor
from .reports_notifications import (
    ExportTool,
    NotificationTool,
    ReportFormatEnum,
    ReportGenerationTool,
)
from .schemes_search import GovernmentSchemesDatabase, SchemeLookupTool, WebSearchTool

__all__ = [
    "AnalysisStorageTool",
    "AnalysisType",
    "AuditLogTool",
    "BusinessIncomeTaxCalculator",
    "CapitalGainsTaxCalculator",
    "ComprehensiveTaxCalculator",
    "DataValidator",
    "DatabaseToolFactory",
    "ExportTool",
    "FinancialDataValidator",
    "GovernmentSchemesDatabase",
    "LLMResponseValidator",
    "NotificationTool",
    "ReportFormatEnum",
    "ReportGenerationTool",
    "SchemeLookupTool",
    "TaxCalculationEngine",
    "ToolExecutor",
    "UserDataUpdateTool",
    "UserFinancialDataTool",
    "ValidationReport",
    "WebDataValidator",
    "WebSearchTool"
]
