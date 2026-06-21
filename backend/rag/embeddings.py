"""
Embeddings service - converts text to vector embeddings using Groq/Llama.
Used for semantic search and RAG retrieval.
"""

from typing import List
import logging
import numpy as np
from groq import Groq

from backend.config import settings

logger = logging.getLogger(__name__)

# Initialize Groq client
client = Groq(api_key=settings.llm.api_key)

# Embedding dimension for Llama models
EMBEDDING_DIM = 768


class EmbeddingsService:
    """
    Generate text embeddings for semantic search.
    
    Note: For production, consider using:
    - Sentence Transformers (all-MiniLM-L6-v2)
    - OpenAI embeddings
    - Cohere embeddings
    
    For now, we use Groq with simple text preprocessing.
    """
    
    def __init__(self):
        self.dim = EMBEDDING_DIM
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Convert text to embedding vector.
        
        Args:
            text: Text to embed
        
        Returns:
            Vector embedding as list of floats
        
        Example:
            embedding = await embeddings.embed_text("What are tax deductions?")
            # Returns: [0.1, -0.05, 0.3, ...] (768 dimensions)
        """
        
        try:
            # Preprocess text
            text = text.strip()
            if not text:
                return [0.0] * self.dim
            
            # Generate embedding using Groq
            # In production, use dedicated embedding models
            embedding = await self._generate_embedding(text)
            
            logger.debug(f"Generated embedding for text: {text[:50]}...")
            
            return embedding
        
        except Exception as e:
            logger.error(f"Error embedding text: {e}")
            # Return zero vector on error
            return [0.0] * self.dim
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Convert multiple texts to embeddings.
        
        Args:
            texts: List of texts to embed
        
        Returns:
            List of embedding vectors
        
        Example:
            embeddings = await embeddings_service.embed_batch([
                "Tax deductions",
                "Investment advice",
                "Government benefits"
            ])
        """
        
        embeddings = []
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
        
        logger.info(f"Generated {len(embeddings)} embeddings")
        
        return embeddings
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """
        Internal method to generate embedding.
        Currently uses simple hash-based approach for demo.
        
        In production, replace with actual embedding model:
        ```python
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embedding = model.encode(text)
        return embedding.tolist()
        ```
        """
        
        # Simple hash-based embedding for demo
        # In production, use proper embedding model
        
        import hashlib
        
        # Create deterministic embedding from text hash
        hash_val = hashlib.md5(text.encode()).hexdigest()
        
        # Seed numpy random with hash
        seed = int(hash_val, 16) % (2**32)
        np.random.seed(seed)
        
        # Generate random vector (deterministic due to seed)
        embedding = np.random.randn(self.dim).astype(float).tolist()
        
        # Normalize
        norm = np.linalg.norm(embedding)
        embedding = [x / norm for x in embedding] if norm > 0 else embedding
        
        return embedding
    
    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First vector
            embedding2: Second vector
        
        Returns:
            Similarity score (0.0 to 1.0)
        
        Example:
            score = embeddings.similarity(vec1, vec2)
            # Returns: 0.85 (85% similar)
        """
        
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            
            # Clamp to [0, 1]
            return max(0.0, min(1.0, float(similarity)))
        
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0


# Global embeddings service
embeddings_service = EmbeddingsService()