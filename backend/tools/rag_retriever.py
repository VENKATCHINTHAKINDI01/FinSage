"""
RAG Retriever Tool Module
=========================

Wraps the vector database search to allow agents to run custom semantic queries.
"""

import logging
from typing import Dict, Any
from backend.rag.retriever import rag_retriever

logger = logging.getLogger(__name__)


class ToolRAGRetriever:
    """Agent tool wrapper for Qdrant knowledge base semantic retrieval."""
    
    @staticmethod
    async def semantic_search_tax_kb(query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Perform semantic search against the loaded tax knowledge base documents.
        """
        try:
            # Leverage the existing RAG retriever service
            docs = await rag_retriever.retrieve_with_context(query, top_k=top_k)
            
            return {
                "success": True,
                "query": query,
                "result": {
                    "context": docs,
                    "documents_count": 1 if docs else 0  # retrieve_with_context returns a merged string
                }
            }
        except Exception as e:
            logger.error(f"Error executing semantic search in tool: {e}")
            return {"success": False, "error": str(e)}
