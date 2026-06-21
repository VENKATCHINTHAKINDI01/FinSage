"""
RAG (Retrieval Augmented Generation) - retrieves relevant documents for agents.
Enables agents to answer questions with reference to knowledge base.
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Retrieves relevant documents from vector store based on query.
    Used by agents to ground responses in knowledge base.
    
    Features:
    - Semantic search
    - Relevance ranking
    - Metadata filtering
    - Source tracking
    """
    
    def __init__(self, top_k: int = 5, similarity_threshold: float = 0.7):
        """
        Initialize retriever.
        
        Args:
            top_k: Number of documents to retrieve
            similarity_threshold: Minimum similarity score (0-1)
        """
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        logger.info(f"RAG retriever initialized (top_k={top_k})")
    
    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve documents relevant to query.
        
        Args:
            query: User's question
            top_k: Override default top_k
            metadata_filter: Filter by metadata (e.g., {"source": "tax_guide"})
        
        Returns:
            List of relevant documents with scores and content
        
        Example:
            results = await retriever.retrieve(
                "What are tax deductions?",
                top_k=3
            )
            for doc in results:
                print(f"{doc['title']}: {doc['content']}")
        """
        
        try:
            from backend.rag.embeddings import embeddings_service
            from backend.rag.vector_store import qdrant_store
            
            # Embed the query
            query_embedding = await embeddings_service.embed_text(query)
            
            # Search vector store
            top_k = top_k or self.top_k
            search_results = await qdrant_store.search(
                query_embedding=query_embedding,
                top_k=top_k,
                threshold=self.similarity_threshold
            )
            
            # Format results
            formatted_results = []
            for result in search_results:
                doc = {
                    "document_id": result["document_id"],
                    "content": result["text"],
                    "score": result["score"],
                    "metadata": result["metadata"]
                }
                formatted_results.append(doc)
            
            logger.info(f"Retrieved {len(formatted_results)} documents for query")
            return formatted_results
        
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}")
            return []
    
    async def retrieve_with_context(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> str:
        """
        Retrieve documents and format as context string for LLM.
        
        Args:
            query: User's question
            top_k: Number of documents to retrieve
        
        Returns:
            Formatted context string with retrieved documents
        
        Example:
            context = await retriever.retrieve_with_context("Tax deductions?")
            # Returns: "Retrieved documents:\n1. [source] ... \n2. [source] ..."
        """
        
        results = await self.retrieve(query, top_k)
        
        if not results:
            return "No relevant documents found in knowledge base."
        
        context_parts = ["Retrieved documents from knowledge base:\n"]
        
        for i, result in enumerate(results, 1):
            source = result.get("metadata", {}).get("source", "Unknown")
            score = result.get("score", 0)
            content = result.get("content", "")
            
            context_parts.append(
                f"{i}. [{source}] (relevance: {score:.2%})\n{content}\n"
            )
        
        return "\n".join(context_parts)
    
    async def add_document(
        self,
        document_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a document to knowledge base.
        
        Args:
            document_id: Unique document ID
            text: Document text
            metadata: Additional metadata
        
        Returns:
            True if successful
        """
        
        try:
            from backend.rag.embeddings import embeddings_service
            from backend.rag.vector_store import qdrant_store
            
            # Generate embedding
            embedding = await embeddings_service.embed_text(text)
            
            # Store in vector database
            success = await qdrant_store.store_document(
                document_id=document_id,
                text=text,
                embedding=embedding,
                metadata=metadata
            )
            
            if success:
                logger.info(f"Added document to knowledge base: {document_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            return False
    
    async def add_documents_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> int:
        """
        Add multiple documents to knowledge base.
        
        Args:
            documents: List of dicts with document_id, text, and metadata
        
        Returns:
            Number of documents added
        """
        
        try:
            from backend.rag.embeddings import embeddings_service
            from backend.rag.vector_store import qdrant_store
            
            # Generate embeddings for all documents
            prepared_docs = []
            for doc in documents:
                embedding = await embeddings_service.embed_text(doc["text"])
                prepared_docs.append({
                    "document_id": doc.get("document_id"),
                    "text": doc.get("text"),
                    "embedding": embedding,
                    "metadata": doc.get("metadata", {})
                })
            
            # Store all documents
            count = await qdrant_store.store_documents_batch(prepared_docs)
            
            logger.info(f"Added {count} documents to knowledge base")
            return count
        
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return 0


# Global RAG retriever
rag_retriever = RAGRetriever()