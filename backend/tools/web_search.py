"""
Web Search Tool Module
======================

Queries online search engines (e.g. Tavily) to fetch the latest tax regulations and guidelines.
Includes response validation, retry logic, and source credibility scoring.
"""

import os
import logging
from typing import Dict, Any
import httpx
from backend.tools.data_validator import WebDataValidator

logger = logging.getLogger(__name__)


class OnlineWebSearchTool:
    """Queries Tavily API or falls back to custom indexed mock database."""
    
    def __init__(self):
        # Support both env var names for backward compatibility
        self.api_key = os.getenv("SEARCH_TAVILY_API_KEY") or os.getenv("TAVILY_API_KEY")
        self.client = httpx.AsyncClient(timeout=15.0)
        self.validator = WebDataValidator()
        self.max_retries = 3

    async def web_search_tavily(self, query: str) -> Dict[str, Any]:
        """
        Query Tavily Search API for the latest financial/tax rules.
        Includes retry logic, validation, and source credibility scoring.
        """
        try:
            if not self.api_key:
                logger.info("Tavily API key not found (checked SEARCH_TAVILY_API_KEY and TAVILY_API_KEY), falling back to mock search.")
                raw_result = await self._fallback_mock_search(query)
                validated, report = self.validator.validate_search_results(raw_result, query)
                validated["data_source"] = "fallback_mock"
                validated["validation"] = report.to_dict()
                return validated
            
            # Retry loop with exponential backoff
            last_error = None
            for attempt in range(self.max_retries):
                try:
                    response = await self.client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": self.api_key,
                            "query": query,
                            "search_depth": "basic",
                            "include_answer": True
                        },
                        timeout=10.0 + (attempt * 5)  # Increasing timeout per retry
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        raw_result = {
                            "success": True,
                            "query": query,
                            "data_source": "tavily_api",
                            "result": {
                                "answer": data.get("answer"),
                                "results": data.get("results", [])[:5]
                            }
                        }
                        # Validate results
                        validated, report = self.validator.validate_search_results(raw_result, query)
                        validated["validation"] = report.to_dict()
                        return validated
                    
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(f"Tavily attempt {attempt + 1}/{self.max_retries} failed: {last_error}")
                    
                except httpx.TimeoutException:
                    last_error = "Request timed out"
                    logger.warning(f"Tavily attempt {attempt + 1}/{self.max_retries}: {last_error}")
                except httpx.ConnectError:
                    last_error = "Connection failed"
                    logger.warning(f"Tavily attempt {attempt + 1}/{self.max_retries}: {last_error}")
            
            # All retries exhausted — fallback
            logger.warning(f"All {self.max_retries} Tavily retries failed ({last_error}), using fallback.")
            raw_result = await self._fallback_mock_search(query)
            validated, report = self.validator.validate_search_results(raw_result, query)
            report.add_warning(f"Live search failed after {self.max_retries} retries: {last_error}")
            validated["data_source"] = "fallback_mock"
            validated["validation"] = report.to_dict()
            return validated
            
        except Exception as e:
            logger.error(f"Error during web search: {e}")
            raw_result = await self._fallback_mock_search(query)
            validated, report = self.validator.validate_search_results(raw_result, query)
            report.add_warning(f"Search error: {str(e)}")
            validated["data_source"] = "fallback_mock"
            validated["validation"] = report.to_dict()
            return validated

    async def _fallback_mock_search(self, query: str) -> Dict[str, Any]:
        """Custom search index mock fallback."""
        query_lower = query.lower()
        results = []
        
        mock_web_index = [
            {
                "title": "CBDT circular on Section 80C changes for FY 2024-25",
                "url": "https://www.incometax.gov.in/circulars/80c-changes",
                "content": "The Central Board of Direct Taxes (CBDT) confirmed that the maximum limit under Section 80C remains ₹1,50,000 for FY 2024-25. No new investment vehicles have been added, but digital verification of receipts has been made mandatory.",
                "date": "2024-06-15"
            },
            {
                "title": "Standard deduction increase for salaried employees in FY 2024-25",
                "url": "https://www.incometax.gov.in/news/standard-deduction",
                "content": "Finance Act 2024 increased the standard deduction for salaried individuals under the new tax regime from ₹50,000 to ₹75,000. Under the old regime, it remains ₹50,000.",
                "date": "2024-07-01"
            },
            {
                "title": "HRA exemption rules under Section 10(13A)",
                "url": "https://www.incometaxindia.gov.in/HRA-rules",
                "content": "Under Section 10(13A) of the Income Tax Act, HRA is exempt to the extent of the minimum of actual HRA, rent paid over 10% of basic salary, or 50%/40% of basic salary.",
                "date": "2024-04-01"
            }
        ]
        
        for item in mock_web_index:
            if any(term in item["title"].lower() or term in item["content"].lower() for term in query_lower.split()):
                results.append(item)
                
        # If no terms match, return default index contents
        if not results:
            results = mock_web_index[:2]
            
        return {
            "success": True,
            "query": query,
            "result": {
                "answer": "Retrieved search details from tax regulations index.",
                "results": results
            }
        }

    async def close(self):
        await self.client.aclose()
