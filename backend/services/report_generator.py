"""
Service to generate, export, and track compiled reports.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.orm_models import Report


class ReportGeneratorService:
    """
    Generate, format, and save reports to database.
    Supports formats: PDF, HTML, JSON, Markdown
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger("service.report_generator")
        
    async def generate_and_save_report(
        self,
        user_id: str,
        report_type: str,
        title: str,
        analysis_data: Dict[str, Any],
        report_format: str = "pdf"
    ) -> Report:
        """
        Generate and persist a new report record.
        """
        try:
            report_id_str = f"rep_{user_id}_{int(datetime.utcnow().timestamp())}"
            file_name = f"{report_id_str}.{report_format}"
            
            # Simulated file compilation path
            file_path = f"/Users/ameersohail/Documents/finsage_ai/exports/{user_id}/{file_name}"
            file_size_bytes = len(json.dumps(analysis_data))
            file_url = f"/api/v1/reports/download/{report_id_str}.{report_format}"
            
            # Format compiler simulation
            if report_format == "html":
                content = self._compile_html_report(title, analysis_data)
                file_size_bytes = len(content)
            elif report_format == "markdown":
                content = self._compile_markdown_report(title, analysis_data)
                file_size_bytes = len(content)
            
            report = Report(
                user_id=user_id,
                report_type=report_type,
                format=report_format,
                title=title,
                generated_at=datetime.utcnow(),
                file_path=file_path,
                file_size=file_size_bytes,
                file_url=file_url,
                delivery_status="generated",
                report_metadata=analysis_data
            )
            
            self.db.add(report)
            await self.db.commit()
            self.logger.info(f"Report generated successfully: {report.title} ({report_format}) for user {user_id}")
            return report
            
        except Exception as e:
            self.logger.error(f"Error compiling report: {e}", exc_info=True)
            await self.db.rollback()
            raise e
            
    async def get_user_reports(self, user_id: str) -> List[Report]:
        """Fetch all reports generated for a user."""
        query = select(Report).where(Report.user_id == user_id).order_by(Report.generated_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
        
    async def record_download(self, report_id: str) -> Optional[Report]:
        """Update download tracking properties."""
        try:
            query = select(Report).where(Report.id == report_id)
            result = await self.db.execute(query)
            report = result.scalars().first()
            
            if report:
                report.download_count += 1
                report.last_downloaded_at = datetime.utcnow()
                report.delivery_status = "downloaded"
                await self.db.commit()
                self.logger.info(f"Report {report_id} downloaded. Count: {report.download_count}")
                return report
            return None
            
        except Exception as e:
            self.logger.error(f"Error recording download: {e}")
            await self.db.rollback()
            return None
            
    def _compile_html_report(self, title: str, data: Dict[str, Any]) -> str:
        """Mock HTML compiler."""
        return f"""
        <html>
        <head><title>{title}</title></head>
        <body>
            <h1>{title}</h1>
            <p>Generated: {datetime.utcnow().isoformat()}</p>
            <pre>{json.dumps(data, indent=2)}</pre>
        </body>
        </html>
        """
        
    def _compile_markdown_report(self, title: str, data: Dict[str, Any]) -> str:
        """Mock Markdown compiler."""
        return f"""
# {title}
*Generated at: {datetime.utcnow().isoformat()}*

```json
{json.dumps(data, indent=2)}
```
"""
