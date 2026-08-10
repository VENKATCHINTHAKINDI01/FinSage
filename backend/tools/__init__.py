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

from .database import (
    UserFinancialDataTool,
    AnalysisStorageTool,
    UserDataUpdateTool,
    AuditLogTool,
    DatabaseToolFactory,
    AnalysisType
)

from .schemes_search import (
    GovernmentSchemesDatabase,
    SchemeLookupTool,
    WebSearchTool
)

from .reports_notifications import (
    ReportGenerationTool,
    NotificationTool,
    ExportTool,
    ReportFormatEnum
)

from .data_validator import (
    DataValidator,
    ValidationReport,
    WebDataValidator,
    LLMResponseValidator,
    FinancialDataValidator
)

from .registry import ToolExecutor

__all__ = [
    "TaxCalculationEngine",
    "CapitalGainsTaxCalculator",
    "BusinessIncomeTaxCalculator",
    "ComprehensiveTaxCalculator",
    "UserFinancialDataTool",
    "AnalysisStorageTool",
    "UserDataUpdateTool",
    "AuditLogTool",
    "DatabaseToolFactory",
    "GovernmentSchemesDatabase",
    "SchemeLookupTool",
    "WebSearchTool",
    "ReportGenerationTool",
    "NotificationTool",
    "ExportTool",
    "ToolExecutor",
    "AnalysisType",
    "ReportFormatEnum",
    "DataValidator",
    "ValidationReport",
    "WebDataValidator",
    "LLMResponseValidator",
    "FinancialDataValidator"
]