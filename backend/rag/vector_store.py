"""
Qdrant vector store client - stores and retrieves embeddings.
Enables semantic search over knowledge base.
"""

from typing import List, Dict, Any, Optional
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from backend.config import settings

logger = logging.getLogger(__name__)

# Qdrant connection settings
QDRANT_URL = settings.qdrant.url or "http://localhost:6333"
COLLECTION_NAME = "finsage_knowledge"
VECTOR_DIM = 768


class QdrantStore:
    """
    Qdrant vector store for storing and retrieving document embeddings.
    
    Features:
    - Store document embeddings
    - Semantic search
    - Metadata filtering
    - Batch operations
    """
    
    def __init__(self, collection_name: str = COLLECTION_NAME):
        """Initialize Qdrant client."""
        try:
            self.client = QdrantClient(url=QDRANT_URL)
            self.collection_name = collection_name
            
            # Verify connection
            self.client.get_collections()
            logger.info(f"Connected to Qdrant at {QDRANT_URL}")
            
            # Create collection if it doesn't exist
            self._ensure_collection_exists()
        
        except Exception as e:
            logger.error(f"Error connecting to Qdrant: {e}")
            raise
    
    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist."""
        try:
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=VECTOR_DIM,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Collection created: {self.collection_name}")
        
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise
    
    async def store_document(
        self,
        document_id: str,
        text: str,
        embedding: List[float],
        metadata: Dict[str, Any] | None = None
    ) -> bool:
        """
        Store a document with its embedding.
        
        Args:
            document_id: Unique ID for document
            text: Document text
            embedding: Vector embedding
            metadata: Additional metadata (source, category, etc.)
        
        Returns:
            True if successful
        
        Example:
            success = await store.store_document(
                "doc-123",
                "Tax deductions include home office expenses...",
                [0.1, -0.05, ...],
                {"source": "tax_guide.pdf", "category": "tax"}
            )
        """
        
        try:
            metadata = metadata or {}
            metadata["text"] = text  # Store original text in metadata
            
            point = PointStruct(
                id=self._hash_to_int(document_id),
                vector=embedding,
                payload=metadata
            )
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.debug(f"Stored document: {document_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error storing document {document_id}: {e}")
            return False
    
    async def store_documents_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> int:
        """
        Store multiple documents.
        
        Args:
            documents: List of dicts with keys:
                - document_id (str)
                - text (str)
                - embedding (List[float])
                - metadata (Dict, optional)
        
        Returns:
            Number of documents stored
        
        Example:
            count = await store.store_documents_batch([
                {
                    "document_id": "doc-1",
                    "text": "...",
                    "embedding": [...],
                    "metadata": {"source": "guide.pdf"}
                }
            ])
        """
        
        try:
            points = []
            for doc in documents:
                metadata = doc.get("metadata", {})
                metadata["text"] = doc["text"]
                
                point = PointStruct(
                    id=self._hash_to_int(doc["document_id"]),
                    vector=doc["embedding"],
                    payload=metadata
                )
                points.append(point)
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(f"Stored {len(points)} documents")
            return len(points)
        
        except Exception as e:
            logger.error(f"Error storing documents: {e}")
            return 0
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        
        Args:
            query_embedding: Vector embedding of query
            top_k: Number of results to return
            threshold: Minimum similarity score (0-1)
        
        Returns:
            List of matching documents with scores
        
        Example:
            results = await store.search(query_embedding, top_k=3)
            for result in results:
                print(f"{result['text']} (score: {result['score']})")
        """
        
        try:
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                score_threshold=threshold
            )
            
            results = []
            for point in search_result:
                result = {
                    "document_id": str(point.id),
                    "score": point.score,
                    "text": point.payload.get("text", ""),
                    "metadata": {k: v for k, v in point.payload.items() if k != "text"}
                }
                results.append(result)
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
        
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector={"ids": [self._hash_to_int(document_id)]}
            )
            logger.debug(f"Deleted document: {document_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "points_count": collection_info.points_count,
                "vector_size": VECTOR_DIM
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
    
    def _hash_to_int(self, text: str) -> int:
        """Convert string to unique integer ID."""
        import hashlib
        hash_val = hashlib.md5(text.encode()).hexdigest()
        return int(hash_val, 16) % (2**63 - 1)


# Global Qdrant store instance
qdrant_store = QdrantStore()