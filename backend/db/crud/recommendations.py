"""
CRUD queries to fetch recommendations, suggestions, and red flags for users.
"""

from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import ComplianceReport, TaxCalculation, RedFlagLog


async def get_user_compliance_recommendations(
    db: AsyncSession,
    user_id: str
) -> List[str]:
    """Retrieve compliance recommendations from the latest report."""
    query = (
        select(ComplianceReport)
        .where(ComplianceReport.user_id == user_id)
        .order_by(ComplianceReport.created_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    report = result.scalars().first()
    if report and report.recommendations:
        if isinstance(report.recommendations, list):
            return report.recommendations
        elif isinstance(report.recommendations, str):
            import json
            try:
                return json.loads(report.recommendations)
            except Exception:
                return [report.recommendations]
    return []


async def get_user_tax_suggestions(
    db: AsyncSession,
    user_id: str
) -> List[Dict[str, Any]]:
    """Retrieve optimization suggestions from the latest tax calculation."""
    query = (
        select(TaxCalculation)
        .where(TaxCalculation.user_id == user_id)
        .order_by(TaxCalculation.created_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    calc = result.scalars().first()
    if calc and calc.optimization_suggestions:
        if isinstance(calc.optimization_suggestions, list):
            return calc.optimization_suggestions
        elif isinstance(calc.optimization_suggestions, str):
            import json
            try:
                return json.loads(calc.optimization_suggestions)
            except Exception:
                return [{"suggestion": calc.optimization_suggestions}]
    return []


async def get_user_red_flags(
    db: AsyncSession,
    user_id: str,
    resolved: bool = False
) -> List[RedFlagLog]:
    """Retrieve active or resolved red flags for a user."""
    query = (
        select(RedFlagLog)
        .where(RedFlagLog.user_id == user_id)
        .where(RedFlagLog.resolved == resolved)
        .order_by(RedFlagLog.created_at.desc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())
