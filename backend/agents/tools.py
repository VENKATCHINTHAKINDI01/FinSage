"""
Agent Tools Architecture
========================

This module defines all tools available to agents for analysis and recommendations.
Tools are the "hands and feet" that allow agents to interact with the system.

Tool Categories:
1. Calculation Tools - Tax math, impact analysis
2. Scheme Tools - Government scheme lookup & eligibility
3. Data Tools - User financial data access
4. Storage Tools - Save & retrieve analysis results
5. Report Tools - Generate reports & exports
6. Search Tools - Web search for latest information
7. Notification Tools - Alert users
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# BASE TOOL CLASS
# ============================================================================

class BaseTool(ABC):
    """Base class for all agent tools."""
    
    def __init__(self, name: str, description: str):
        """
        Initialize tool.
        
        Args:
            name: Tool name (e.g., "calculate_tax_liability")
            description: What the tool does
        """
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"tool.{name}")
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool with given parameters.
        
        Returns:
            Result dict with status and data
        """
        pass
    
    def _result(self, success: bool, data: Any, message: str = ""):
        """Format tool result."""
        return {
            "success": success,
            "data": data,
            "message": message,
            "tool": self.name,
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================================================
# CATEGORY 1: CALCULATION TOOLS
# ============================================================================

class CalculateTaxLiabilityTool(BaseTool):
    """Calculate total tax liability based on income and deductions."""
    
    def __init__(self):
        super().__init__(
            "calculate_tax_liability",
            "Calculate tax liability from income and deductions"
        )
    
    async def execute(
        self,
        total_income: float,
        deductions: float,
        age: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Calculate tax liability.
        
        Args:
            total_income: Total annual income in INR
            deductions: Total deductions in INR
            age: User age (for senior citizen exemption)
        
        Returns:
            Tax liability breakdown
        """
        try:
            taxable_income = max(0, total_income - deductions)
            
            # Simple tax bracket calculation (can be enhanced)
            tax = self._calculate_tax(taxable_income, age)
            
            # Add surcharge (if applicable)
            surcharge = self._calculate_surcharge(taxable_income)
            
            # Add health & education cess
            cess = (tax + surcharge) * 0.04
            
            total_tax = tax + surcharge + cess
            
            return self._result(
                success=True,
                data={
                    "total_income": total_income,
                    "deductions": deductions,
                    "taxable_income": taxable_income,
                    "income_tax": tax,
                    "surcharge": surcharge,
                    "cess": cess,
                    "total_tax_liability": total_tax,
                    "effective_tax_rate": (total_tax / total_income * 100) if total_income > 0 else 0
                },
                message="Tax liability calculated"
            )
        except Exception as e:
            logger.error(f"Error calculating tax: {e}")
            return self._result(False, None, str(e))
    
    def _calculate_tax(self, taxable_income: float, age: int) -> float:
        """Calculate income tax based on brackets (India FY 2024-25)."""
        
        # Exemption limit
        if age >= 60:
            exemption = 500000
        elif age >= 80:
            exemption = 500000
        else:
            exemption = 250000
        
        if taxable_income <= exemption:
            return 0
        
        # Tax brackets (India FY 2024-25)
        brackets = [
            (300000, 0.05),    # 0-3L: 5%
            (600000, 0.10),    # 3-6L: 10%
            (900000, 0.15),    # 6-9L: 15%
            (1200000, 0.20),   # 9-12L: 20%
            (float('inf'), 0.30) # 12L+: 30%
        ]
        
        tax = 0
        prev_limit = exemption
        
        for limit, rate in brackets:
            if taxable_income > prev_limit:
                taxable_in_bracket = min(taxable_income, limit) - prev_limit
                tax += taxable_in_bracket * rate
                prev_limit = limit
            else:
                break
        
        return tax
    
    def _calculate_surcharge(self, taxable_income: float) -> float:
        """Calculate surcharge on income tax."""
        if taxable_income > 10000000:
            return 0.10  # 10% surcharge
        elif taxable_income > 5000000:
            return 0.07  # 7% surcharge
        return 0


class CalculateDeductionImpactTool(BaseTool):
    """Calculate tax savings from a deduction."""
    
    def __init__(self):
        super().__init__(
            "calculate_deduction_impact",
            "Calculate tax savings from a specific deduction"
        )
    
    async def execute(
        self,
        deduction_amount: float,
        current_income: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate tax savings from adding a deduction."""
        try:
            # Estimate tax bracket
            tax_bracket = self._estimate_bracket(current_income)
            
            # Tax savings
            tax_savings = deduction_amount * tax_bracket
            
            return self._result(
                success=True,
                data={
                    "deduction_amount": deduction_amount,
                    "estimated_tax_bracket": tax_bracket,
                    "tax_savings": tax_savings,
                    "savings_percentage": (tax_savings / current_income * 100) if current_income > 0 else 0
                },
                message=f"Deduction will save ₹{tax_savings:,.0f} in taxes"
            )
        except Exception as e:
            return self._result(False, None, str(e))
    
    def _estimate_bracket(self, income: float) -> float:
        """Estimate effective tax bracket."""
        if income <= 250000:
            return 0.0
        elif income <= 500000:
            return 0.05
        elif income <= 750000:
            return 0.10
        elif income <= 1000000:
            return 0.15
        elif income <= 1250000:
            return 0.20
        else:
            return 0.30


class EstimateTaxRefundTool(BaseTool):
    """Estimate potential tax refund based on deductions."""
    
    def __init__(self):
        super().__init__(
            "estimate_tax_refund",
            "Estimate potential tax refund from deductions and credits"
        )
    
    async def execute(
        self,
        tds_paid: float,
        estimated_tax_liability: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Calculate estimated refund."""
        try:
            refund = max(0, tds_paid - estimated_tax_liability)
            
            return self._result(
                success=True,
                data={
                    "tds_paid": tds_paid,
                    "estimated_tax_liability": estimated_tax_liability,
                    "refund": refund,
                    "refund_expected": refund > 0
                },
                message=f"Estimated refund: ₹{refund:,.0f}"
            )
        except Exception as e:
            return self._result(False, None, str(e))


# ============================================================================
# CATEGORY 2: SCHEME TOOLS
# ============================================================================

class GetSchemeDetailsTool(BaseTool):
    """Get details of a tax saving scheme."""
    
    def __init__(self):
        super().__init__(
            "get_scheme_details",
            "Get details of a tax saving scheme (e.g., 80C, 80D)"
        )
        
        # Hardcoded scheme database (can be replaced with DB)
        self.schemes = {
            "80C": {
                "name": "Section 80C - Life Insurance Premium, etc.",
                "limit": 150000,
                "applicable_to": ["All individuals", "HUF"],
                "investment_options": ["ELSS", "PPF", "Life Insurance", "NSC", "FDs"],
                "lock_in_period": "3 years (ELSS), 15 years (PPF)",
                "eligibility": "All",
                "documents": ["Investment receipts", "Premium receipts"],
                "benefits": "Direct tax deduction"
            },
            "80D": {
                "name": "Section 80D - Health Insurance Premium",
                "limit": 150000,
                "applicable_to": ["All individuals", "HUF"],
                "eligibility": "Own or family health insurance",
                "lock_in_period": "None",
                "documents": ["Insurance policy", "Premium receipts"],
                "benefits": "Direct tax deduction"
            },
            "80E": {
                "name": "Section 80E - Education Loan Interest",
                "limit": None,
                "applicable_to": ["Individual student/parent"],
                "eligibility": "Education loan for higher education",
                "lock_in_period": "8 years",
                "documents": ["Loan agreement", "Interest receipts"],
                "benefits": "Deduction of interest paid"
            },
            "80TTA": {
                "name": "Section 80TTA - Savings Account Interest",
                "limit": 10000,
                "applicable_to": ["Individual (not senior citizen)"],
                "eligibility": "Savings account interest income",
                "lock_in_period": "None",
                "documents": ["Bank statements"],
                "benefits": "Tax deduction on interest"
            },
            "80TTB": {
                "name": "Section 80TTB - Senior Citizen Interest Income",
                "limit": 50000,
                "applicable_to": ["Senior citizen (60+)"],
                "eligibility": "Interest from savings deposits",
                "lock_in_period": "None",
                "documents": ["Bank/interest statements"],
                "benefits": "Tax deduction on interest"
            },
            "80CCD": {
                "name": "Section 80CCD - National Pension Scheme",
                "limit": 150000,
                "applicable_to": ["All individuals"],
                "eligibility": "NPS contributions",
                "lock_in_period": "Till retirement",
                "documents": ["NPS statements"],
                "benefits": "Tax deduction + pension"
            }
        }
    
    async def execute(
        self,
        scheme_code: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Get scheme details."""
        try:
            scheme = self.schemes.get(scheme_code.upper())
            
            if not scheme:
                return self._result(
                    False,
                    None,
                    f"Scheme {scheme_code} not found"
                )
            
            return self._result(
                True,
                scheme,
                f"Retrieved details for {scheme_code}"
            )
        except Exception as e:
            return self._result(False, None, str(e))


class CheckSchemeEligibilityTool(BaseTool):
    """Check if user is eligible for a scheme."""
    
    def __init__(self):
        super().__init__(
            "check_scheme_eligibility",
            "Check if user qualifies for a tax scheme"
        )
    
    async def execute(
        self,
        scheme_code: str,
        user_age: int,
        user_income: float,
        has_health_insurance: bool = False,
        has_education_loan: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Check scheme eligibility."""
        try:
            eligible = True
            reasons = []
            
            scheme = scheme_code.upper()
            
            if scheme == "80TTB":
                if user_age < 60:
                    eligible = False
                    reasons.append("Must be 60 years or older")
            
            elif scheme == "80D":
                if not has_health_insurance:
                    eligible = False
                    reasons.append("Must have health insurance policy")
            
            elif scheme == "80E":
                if not has_education_loan:
                    eligible = False
                    reasons.append("Must have active education loan")
            
            return self._result(
                True,
                {
                    "scheme": scheme,
                    "eligible": eligible,
                    "reasons": reasons if not eligible else ["Eligible"]
                },
                "Eligibility checked"
            )
        except Exception as e:
            return self._result(False, None, str(e))


# ============================================================================
# CATEGORY 3: DATA TOOLS
# ============================================================================

class GetUserFinancialDataTool(BaseTool):
    """Get user's financial profile data."""
    
    def __init__(self):
        super().__init__(
            "get_user_financial_data",
            "Retrieve user's financial profile from database"
        )
    
    async def execute(
        self,
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Get user financial data."""
        try:
            # TODO: Integrate with actual DB
            # For now, return placeholder
            
            return self._result(
                True,
                {
                    "user_id": user_id,
                    "annual_income": 0,
                    "employment_type": "unknown",
                    "monthly_expenses": 0,
                    "investments": [],
                    "loans": [],
                    "health_insurance": False,
                    "life_insurance": False
                },
                "User financial data retrieved"
            )
        except Exception as e:
            return self._result(False, None, str(e))


# ============================================================================
# CATEGORY 4: STORAGE TOOLS
# ============================================================================

class SaveAnalysisTool(BaseTool):
    """Save analysis results for future reference."""
    
    def __init__(self):
        super().__init__(
            "save_analysis",
            "Save agent analysis results to database"
        )
    
    async def execute(
        self,
        user_id: str,
        analysis_type: str,
        result_data: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Save analysis."""
        try:
            # TODO: Save to database
            analysis_id = f"analysis_{user_id}_{datetime.utcnow().timestamp()}"
            
            return self._result(
                True,
                {
                    "analysis_id": analysis_id,
                    "user_id": user_id,
                    "type": analysis_type,
                    "saved_at": datetime.utcnow().isoformat()
                },
                f"Analysis saved with ID: {analysis_id}"
            )
        except Exception as e:
            return self._result(False, None, str(e))


# ============================================================================
# CATEGORY 5: REPORT TOOLS
# ============================================================================

class GenerateTaxReportTool(BaseTool):
    """Generate a tax analysis report."""
    
    def __init__(self):
        super().__init__(
            "generate_tax_report",
            "Generate a comprehensive tax analysis report"
        )
    
    async def execute(
        self,
        user_id: str,
        analysis_data: Dict[str, Any],
        format: str = "json",  # json, pdf, excel
        **kwargs
    ) -> Dict[str, Any]:
        """Generate report."""
        try:
            # TODO: Implement report generation
            
            return self._result(
                True,
                {
                    "report_id": f"report_{user_id}_{datetime.utcnow().timestamp()}",
                    "format": format,
                    "generated_at": datetime.utcnow().isoformat(),
                    "url": f"/reports/{user_id}/latest.{format}"
                },
                "Report generated"
            )
        except Exception as e:
            return self._result(False, None, str(e))


# ============================================================================
# TOOL REGISTRY
# ============================================================================

class ToolRegistry:
    """Registry of all available tools."""
    
    def __init__(self):
        """Initialize all tools."""
        
        # Calculation tools
        self.calculate_tax_liability = CalculateTaxLiabilityTool()
        self.calculate_deduction_impact = CalculateDeductionImpactTool()
        self.estimate_tax_refund = EstimateTaxRefundTool()
        
        # Scheme tools
        self.get_scheme_details = GetSchemeDetailsTool()
        self.check_scheme_eligibility = CheckSchemeEligibilityTool()
        
        # Data tools
        self.get_user_financial_data = GetUserFinancialDataTool()
        
        # Storage tools
        self.save_analysis = SaveAnalysisTool()
        
        # Report tools
        self.generate_tax_report = GenerateTaxReportTool()
        
        # Register all tools
        self.tools = {
            "calculate_tax_liability": self.calculate_tax_liability,
            "calculate_deduction_impact": self.calculate_deduction_impact,
            "estimate_tax_refund": self.estimate_tax_refund,
            "get_scheme_details": self.get_scheme_details,
            "check_scheme_eligibility": self.check_scheme_eligibility,
            "get_user_financial_data": self.get_user_financial_data,
            "save_analysis": self.save_analysis,
            "generate_tax_report": self.generate_tax_report,
        }
        
        logger.info(f"Registered {len(self.tools)} tools")
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool by name.
        
        Args:
            tool_name: Name of the tool
            **kwargs: Tool parameters
        
        Returns:
            Tool result
        """
        tool = self.tools.get(tool_name)
        
        if not tool:
            return {
                "success": False,
                "message": f"Tool '{tool_name}' not found",
                "available_tools": list(self.tools.keys())
            }
        
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {
                "success": False,
                "message": str(e),
                "tool": tool_name
            }
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, str]]:
        """Get information about a tool."""
        tool = self.tools.get(tool_name)
        if tool:
            return {
                "name": tool.name,
                "description": tool.description
            }
        return None
    
    def list_tools(self) -> List[Dict[str, str]]:
        """List all available tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description
            }
            for tool in self.tools.values()
        ]


# Global tool registry
tool_registry = ToolRegistry()