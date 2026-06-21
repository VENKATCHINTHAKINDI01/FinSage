"""
Unified Tool Registry
====================

Central registry and management of all agent tools.
This is the interface that agents use to access tools.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL EXECUTION INTERFACE
# ============================================================================

class ToolExecutor:
    """Execute tools on behalf of agents."""
    
    def __init__(
        self,
        calculation_engine,
        database_tools,
        scheme_tools,
        search_tools,
        report_tools,
        notification_tools,
        export_tools
    ):
        """Initialize with all tool implementations."""
        
        self.calc_engine = calculation_engine
        self.db_tools = database_tools
        self.scheme_tools = scheme_tools
        self.search_tools = search_tools
        self.report_tools = report_tools
        self.notification_tools = notification_tools
        self.export_tools = export_tools
        
        self.logger = logging.getLogger("tool.executor")
        
        # Initialize new tool engines
        from backend.tools.calculator import TaxDeductionCalculator
        from backend.tools.alert_engine import TaxAlertEngine
        from backend.tools.financial_api import FinancialAPIClient
        from backend.tools.govt_portal import GovtPortalClient
        from backend.tools.pdf_parser import PDFStatementParser
        from backend.tools.rag_retriever import ToolRAGRetriever
        from backend.tools.web_search import OnlineWebSearchTool
        
        self.calculator = TaxDeductionCalculator()
        self.alert_engine = TaxAlertEngine()
        self.financial_api = FinancialAPIClient()
        self.govt_portal = GovtPortalClient()
        self.pdf_parser = PDFStatementParser()
        self.rag_retriever = ToolRAGRetriever()
        self.online_search = OnlineWebSearchTool()
        
        # Tool registry
        self.tools = {
            # Calculation tools
            "calculate_tax_liability": self.calculate_tax_liability,
            "calculate_deduction_impact": self.calculate_deduction_impact,
            "estimate_tax_refund": self.estimate_tax_refund,
            "calculate_capital_gains_tax": self.calculate_capital_gains_tax,
            
            # New Calculation tools
            "calculate_hra_exemption": self.calculate_hra_exemption,
            "calculate_professional_tax": self.calculate_professional_tax,
            
            # Database tools
            "get_user_profile": self.get_user_profile,
            "get_user_income_history": self.get_user_income_history,
            "get_user_deductions": self.get_user_deductions,
            "get_user_investments": self.get_user_investments,
            "save_analysis": self.save_analysis,
            "save_recommendation": self.save_recommendation,
            "get_analysis_history": self.get_analysis_history,
            "update_user_data": self.update_user_data,
            
            # Scheme tools
            "get_scheme_details": self.get_scheme_details,
            "search_schemes": self.search_schemes,
            "get_applicable_schemes": self.get_applicable_schemes,
            "check_scheme_eligibility": self.check_scheme_eligibility,
            
            # Search tools
            "search_latest_tax_rules": self.search_latest_tax_rules,
            "search_government_schemes": self.search_government_schemes,
            "get_tax_deadlines": self.get_tax_deadlines,
            
            # Report tools
            "generate_tax_report": self.generate_tax_report,
            "generate_deduction_report": self.generate_deduction_report,
            "generate_optimization_report": self.generate_optimization_report,
            
            # Notification tools
            "send_email": self.send_email,
            "send_sms": self.send_sms,
            "create_reminder": self.create_reminder,
            
            # Export tools
            "export_to_excel": self.export_to_excel,
            "export_to_pdf": self.export_to_pdf,
            
            # New Alert tools
            "generate_tax_saving_alerts": self.generate_tax_saving_alerts,
            "check_upcoming_deadlines": self.check_upcoming_deadlines,
            
            # New Financial API tools
            "fetch_live_market_data": self.fetch_live_market_data,
            "fetch_bank_statements": self.fetch_bank_statements,
            
            # New Govt Portal tools
            "verify_pan_details": self.verify_pan_details,
            "fetch_form_26as_statement": self.fetch_form_26as_statement,
            
            # New PDF Parser tools
            "parse_investment_receipt": self.parse_investment_receipt,
            "parse_form16": self.parse_form16,
            
            # New RAG search tools
            "semantic_search_tax_kb": self.semantic_search_tax_kb,
            
            # New Web search tools
            "web_search_tavily": self.web_search_tavily,
        }
        
        self.logger.info(f"Tool registry initialized with {len(self.tools)} tools")
    
    # ======================================================================
    # CALCULATION TOOLS
    # ======================================================================
    
    async def calculate_tax_liability(
        self,
        total_income: float,
        deductions: float,
        age: int = 0,
        employment_type: str = "individual",
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate total tax liability."""
        try:
            result = self.calc_engine.calculate_tax_with_deductions(
                gross_income=total_income,
                deductions={"total": deductions},
                category=employment_type,
                age=age
            )
            return {
                "success": True,
                "tool": "calculate_tax_liability",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Error calculating tax liability: {e}")
            return {"success": False, "error": str(e)}
    
    async def calculate_deduction_impact(
        self,
        deduction_amount: float,
        current_taxable_income: float = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate tax savings from a deduction."""
        try:
            income = current_taxable_income if current_taxable_income is not None else kwargs.get("current_income", 0.0)
            result = self.calc_engine.calculate_deduction_benefit(
                deduction_amount=deduction_amount,
                current_taxable_income=income
            )
            return {
                "success": True,
                "tool": "calculate_deduction_impact",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Error calculating deduction impact: {e}")
            return {"success": False, "error": str(e)}
    
    async def estimate_tax_refund(
        self,
        tds_paid: float,
        estimated_tax_liability: float,
        other_taxes: float = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """Estimate tax refund."""
        try:
            result = self.calc_engine.calculate_refund(
                tds_paid=tds_paid,
                estimated_tax_liability=estimated_tax_liability,
                other_taxes=other_taxes
            )
            return {
                "success": True,
                "tool": "estimate_tax_refund",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Error estimating refund: {e}")
            return {"success": False, "error": str(e)}
    
    async def calculate_capital_gains_tax(
        self,
        short_term_gains: float = 0,
        long_term_gains: float = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate capital gains tax."""
        try:
            results = {}
            
            if short_term_gains > 0:
                results["stcg"] = self.calc_engine.CapitalGainsTaxCalculator.calculate_stcg_tax(
                    short_term_gains=short_term_gains,
                    total_income=kwargs.get("total_income", 0)
                )
            
            if long_term_gains > 0:
                results["ltcg"] = self.calc_engine.CapitalGainsTaxCalculator.calculate_ltcg_tax(
                    long_term_gains=long_term_gains
                )
            
            return {
                "success": True,
                "tool": "calculate_capital_gains_tax",
                "result": results
            }
        except Exception as e:
            self.logger.error(f"Error calculating capital gains tax: {e}")
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # DATABASE TOOLS
    # ======================================================================
    
    async def get_user_profile(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Get user's complete financial profile."""
        try:
            result = await self.db_tools["user_data"].get_user_profile(user_id)
            return {"success": True, "tool": "get_user_profile", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_user_income_history(self, user_id: str, years: int = 3, **kwargs) -> Dict[str, Any]:
        """Get user's income history."""
        try:
            result = await self.db_tools["user_data"].get_user_income_history(user_id, years)
            return {"success": True, "tool": "get_user_income_history", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_user_deductions(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Get user's claimed deductions."""
        try:
            result = await self.db_tools["user_data"].get_user_deductions(user_id)
            return {"success": True, "tool": "get_user_deductions", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_user_investments(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Get user's investment portfolio."""
        try:
            result = await self.db_tools["user_data"].get_user_investments(user_id)
            return {"success": True, "tool": "get_user_investments", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def save_analysis(
        self,
        user_id: str,
        analysis_type: str,
        analysis_data: Dict[str, Any] = None,
        agent_name: str = "unknown",
        **kwargs
    ) -> Dict[str, Any]:
        """Save analysis results."""
        try:
            data = analysis_data if analysis_data is not None else kwargs.get("result_data", {})
            result = await self.db_tools["storage"].save_analysis(
                user_id=user_id,
                analysis_type=analysis_type,
                analysis_data=data,
                agent_name=agent_name
            )
            return {"success": True, "tool": "save_analysis", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def save_recommendation(
        self,
        user_id: str,
        recommendation_type: str,
        recommendation: Dict[str, Any],
        agent_name: str = "unknown",
        **kwargs
    ) -> Dict[str, Any]:
        """Save recommendation."""
        try:
            result = await self.db_tools["storage"].save_recommendation(
                user_id=user_id,
                recommendation_type=recommendation_type,
                recommendation=recommendation,
                agent_name=agent_name
            )
            return {"success": True, "tool": "save_recommendation", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_analysis_history(
        self,
        user_id: str,
        analysis_type: Optional[str] = None,
        limit: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """Get analysis history."""
        try:
            result = await self.db_tools["storage"].get_analysis_history(
                user_id=user_id,
                analysis_type=analysis_type,
                limit=limit
            )
            return {"success": True, "tool": "get_analysis_history", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def update_user_data(
        self,
        user_id: str,
        data_type: str,
        data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Update user data."""
        try:
            if data_type == "income":
                result = await self.db_tools["update"].update_income(user_id, data)
            elif data_type == "deductions":
                result = await self.db_tools["update"].update_deductions(user_id, data)
            elif data_type == "investments":
                result = await self.db_tools["update"].update_investments(user_id, data)
            else:
                return {"success": False, "error": f"Unknown data type: {data_type}"}
            
            return {"success": True, "tool": "update_user_data", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # SCHEME TOOLS
    # ======================================================================
    
    async def get_scheme_details(self, scheme_code: str, **kwargs) -> Dict[str, Any]:
        """Get scheme details."""
        try:
            result = await self.scheme_tools.get_scheme_details(scheme_code)
            return {"success": True, "tool": "get_scheme_details", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def search_schemes(self, keyword: str, **kwargs) -> Dict[str, Any]:
        """Search schemes."""
        try:
            result = await self.scheme_tools.search_schemes_by_keyword(keyword)
            return {"success": True, "tool": "search_schemes", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_applicable_schemes(
        self,
        age: int,
        employment_type: str,
        has_health_insurance: bool = False,
        has_education_loan: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Get applicable schemes for user."""
        try:
            result = await self.scheme_tools.get_applicable_schemes(
                age=age,
                employment_type=employment_type,
                has_health_insurance=has_health_insurance,
                has_education_loan=has_education_loan
            )
            return {"success": True, "tool": "get_applicable_schemes", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def check_scheme_eligibility(
        self,
        scheme_code: str,
        user_age: int,
        user_income: float,
        has_health_insurance: bool = False,
        has_education_loan: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Check user eligibility for a specific scheme."""
        try:
            result = await self.scheme_tools.check_scheme_eligibility(
                scheme_code=scheme_code,
                user_age=user_age,
                user_income=user_income,
                has_health_insurance=has_health_insurance,
                has_education_loan=has_education_loan
            )
            return {"success": True, "tool": "check_scheme_eligibility", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # SEARCH TOOLS
    # ======================================================================
    
    async def search_latest_tax_rules(self, keyword: str = "", **kwargs) -> Dict[str, Any]:
        """Search latest tax rules."""
        try:
            result = await self.search_tools.search_latest_tax_rules(keyword)
            return {"success": True, "tool": "search_latest_tax_rules", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def search_government_schemes(self, keyword: str = "", **kwargs) -> Dict[str, Any]:
        """Search government schemes."""
        try:
            result = await self.search_tools.search_government_schemes(keyword)
            return {"success": True, "tool": "search_government_schemes", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_tax_deadlines(self, **kwargs) -> Dict[str, Any]:
        """Get tax deadlines."""
        try:
            result = await self.search_tools.get_tax_deadlines()
            return {"success": True, "tool": "get_tax_deadlines", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # REPORT TOOLS
    # ======================================================================
    
    async def generate_tax_report(
        self,
        user_id: str,
        analysis_data: Dict[str, Any],
        format: str = "json",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate tax analysis report."""
        try:
            result = await self.report_tools.generate_tax_analysis_report(
                user_id=user_id,
                analysis_data=analysis_data,
                format=format
            )
            return {"success": True, "tool": "generate_tax_report", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def generate_deduction_report(
        self,
        user_id: str,
        deductions: List[Dict[str, Any]],
        total_savings: float,
        format: str = "json",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate deduction report."""
        try:
            result = await self.report_tools.generate_deduction_report(
                user_id=user_id,
                deductions=deductions,
                total_savings=total_savings,
                format=format
            )
            return {"success": True, "tool": "generate_deduction_report", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def generate_optimization_report(
        self,
        user_id: str,
        strategies: List[Dict[str, Any]],
        total_savings: float,
        format: str = "json",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate optimization report."""
        try:
            result = await self.report_tools.generate_optimization_report(
                user_id=user_id,
                strategies=strategies,
                total_savings=total_savings,
                format=format
            )
            return {"success": True, "tool": "generate_optimization_report", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # NOTIFICATION TOOLS
    # ======================================================================
    
    async def send_email(
        self,
        user_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send email notification."""
        try:
            result = await self.notification_tools.send_email(
                user_email=user_email,
                subject=subject,
                body=body,
                html_body=html_body
            )
            return {"success": True, "tool": "send_email", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def send_sms(self, phone_number: str, message: str, **kwargs) -> Dict[str, Any]:
        """Send SMS notification."""
        try:
            result = await self.notification_tools.send_sms(
                phone_number=phone_number,
                message=message
            )
            return {"success": True, "tool": "send_sms", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def create_reminder(
        self,
        user_id: str,
        reminder_text: str,
        reminder_date: str,
        reminder_type: str = "notification",
        **kwargs
    ) -> Dict[str, Any]:
        """Create reminder."""
        try:
            result = await self.notification_tools.create_reminder(
                user_id=user_id,
                reminder_text=reminder_text,
                reminder_date=reminder_date,
                reminder_type=reminder_type
            )
            return {"success": True, "tool": "create_reminder", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # EXPORT TOOLS
    # ======================================================================
    
    async def export_to_excel(
        self,
        user_id: str,
        data: Dict[str, Any],
        filename: str = "tax_analysis.xlsx",
        **kwargs
    ) -> Dict[str, Any]:
        """Export to Excel."""
        try:
            result = await self.export_tools.export_to_excel(
                user_id=user_id,
                data=data,
                filename=filename
            )
            return {"success": True, "tool": "export_to_excel", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def export_to_pdf(
        self,
        user_id: str,
        report_data: Dict[str, Any],
        filename: str = "tax_analysis.pdf",
        **kwargs
    ) -> Dict[str, Any]:
        """Export to PDF."""
        try:
            result = await self.export_tools.export_to_pdf(
                user_id=user_id,
                report_data=report_data,
                filename=filename
            )
            return {"success": True, "tool": "export_to_pdf", "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW CALCULATOR TOOLS
    # ======================================================================
    
    async def calculate_hra_exemption(
        self,
        basic_salary: float,
        hra_received: float,
        rent_paid: float,
        is_metro: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate HRA exemption."""
        try:
            res = self.calculator.calculate_hra_exemption(
                basic_salary=basic_salary,
                hra_received=hra_received,
                rent_paid=rent_paid,
                is_metro=is_metro
            )
            return {"success": True, "tool": "calculate_hra_exemption", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def calculate_professional_tax(
        self,
        state: str,
        monthly_income: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate Professional Tax."""
        try:
            res = self.calculator.calculate_professional_tax(
                state=state,
                monthly_income=monthly_income
            )
            return {"success": True, "tool": "calculate_professional_tax", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW ALERT TOOLS
    # ======================================================================
    
    async def generate_tax_saving_alerts(
        self,
        investments: Dict[str, float] = None,
        deductions: Dict[str, float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate tax saving alerts."""
        try:
            res = self.alert_engine.generate_tax_saving_alerts(
                investments=investments or {},
                deductions=deductions or {}
            )
            return {"success": True, "tool": "generate_tax_saving_alerts", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def check_upcoming_deadlines(self, **kwargs) -> Dict[str, Any]:
        """Check tax filing deadlines."""
        try:
            res = self.alert_engine.check_upcoming_deadlines()
            return {"success": True, "tool": "check_upcoming_deadlines", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW FINANCIAL API TOOLS
    # ======================================================================
    
    async def fetch_live_market_data(self, ticker: str, **kwargs) -> Dict[str, Any]:
        """Fetch market valuations."""
        try:
            res = await self.financial_api.fetch_live_market_data(ticker=ticker)
            return {"success": True, "tool": "fetch_live_market_data", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def fetch_bank_statements(
        self,
        bank_name: str,
        account_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Fetch linked transactions."""
        try:
            res = await self.financial_api.fetch_bank_statements(
                bank_name=bank_name,
                account_id=account_id
            )
            return {"success": True, "tool": "fetch_bank_statements", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW GOVT PORTAL TOOLS
    # ======================================================================
    
    async def verify_pan_details(self, pan_number: str, **kwargs) -> Dict[str, Any]:
        """Verify PAN card registry status."""
        try:
            res = self.govt_portal.verify_pan_details(pan_number=pan_number)
            return {"success": True, "tool": "verify_pan_details", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def fetch_form_26as_statement(self, pan_number: str, **kwargs) -> Dict[str, Any]:
        """Fetch official tax credits."""
        try:
            res = self.govt_portal.fetch_form_26as_statement(pan_number=pan_number)
            return {"success": True, "tool": "fetch_form_26as_statement", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW PDF PARSER TOOLS
    # ======================================================================
    
    async def parse_investment_receipt(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """Parse ELSS/NPS receipts."""
        try:
            res = self.pdf_parser.parse_investment_receipt(file_path=file_path)
            return {"success": True, "tool": "parse_investment_receipt", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def parse_form16(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """Parse Form 16 PDF."""
        try:
            res = self.pdf_parser.parse_form16(file_path=file_path)
            return {"success": True, "tool": "parse_form16", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW RAG RETRIEVER TOOLS
    # ======================================================================
    
    async def semantic_search_tax_kb(self, query: str, top_k: int = 5, **kwargs) -> Dict[str, Any]:
        """Semantic search Qdrant database."""
        try:
            res = await self.rag_retriever.semantic_search_tax_kb(query=query, top_k=top_k)
            return {"success": True, "tool": "semantic_search_tax_kb", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================================================================
    # NEW WEB SEARCH TOOLS
    # ======================================================================
    
    async def web_search_tavily(self, query: str, **kwargs) -> Dict[str, Any]:
        """Search Web via Tavily."""
        try:
            res = await self.online_search.web_search_tavily(query=query)
            return {"success": True, "tool": "web_search_tavily", "result": res}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ======================================================================
    # REGISTRY METHODS
    # ======================================================================
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found",
                "available_tools": list(self.tools.keys())
            }
        
        try:
            tool_func = self.tools[tool_name]
            res = await tool_func(**kwargs)
            if isinstance(res, dict) and "result" in res and "data" not in res:
                res["data"] = res["result"]
            return res
        except Exception as e:
            self.logger.error(f"Error executing tool {tool_name}: {e}")
            return {"success": False, "error": str(e), "tool": tool_name}
    
    def list_tools(self) -> List[str]:
        """List all available tools."""
        return sorted(list(self.tools.keys()))
    
    def get_tool_categories(self) -> Dict[str, List[str]]:
        """Get tools grouped by category."""
        return {
            "calculation": [
                "calculate_tax_liability",
                "calculate_deduction_impact",
                "estimate_tax_refund",
                "calculate_capital_gains_tax",
                "calculate_hra_exemption",
                "calculate_professional_tax"
            ],
            "database": [
                "get_user_profile",
                "get_user_income_history",
                "get_user_deductions",
                "get_user_investments",
                "save_analysis",
                "save_recommendation",
                "get_analysis_history",
                "update_user_data"
            ],
            "schemes": [
                "get_scheme_details",
                "search_schemes",
                "get_applicable_schemes",
                "check_scheme_eligibility"
            ],
            "search": [
                "search_latest_tax_rules",
                "search_government_schemes",
                "get_tax_deadlines",
                "web_search_tavily",
                "semantic_search_tax_kb"
            ],
            "reporting": [
                "generate_tax_report",
                "generate_deduction_report",
                "generate_optimization_report",
                "export_to_excel",
                "export_to_pdf"
            ],
            "notification": [
                "send_email",
                "send_sms",
                "create_reminder"
            ],
            "alerts": [
                "generate_tax_saving_alerts",
                "check_upcoming_deadlines"
            ],
            "parser": [
                "parse_investment_receipt",
                "parse_form16"
            ],
            "external_apis": [
                "fetch_live_market_data",
                "fetch_bank_statements",
                "verify_pan_details",
                "fetch_form_26as_statement"
            ]
        }