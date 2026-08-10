"""Text embeddings — DEM-004.

What this replaced
------------------
    hash_val = hashlib.md5(text.encode()).hexdigest()
    np.random.seed(int(hash_val, 16) % (2**32))
    embedding = np.random.randn(self.dim)

That is deterministic, and it is not an embedding. "80C deduction limit" and
"Section 80C limit" hash differently, so they seed differently, so they produce
orthogonal vectors. Semantic search over it returns noise.

The damage was not just poor retrieval. Every agent claimed its answer was
grounded in retrieved sources, and `ValidationReport` reported a
`sources_verified` count, while the retrieval underneath was random. The
confidence numbers shown to users were measuring nothing.

Now: BAAI/bge-small-en-v1.5 via fastembed (ONNX runtime). Chosen over
sentence-transformers because that pulls torch plus ~18 nvidia-* packages —
several gigabytes — into the image for a CPU-only workload.

Failure policy
--------------
If the model cannot load, this raises. It does NOT fall back to a hash, a zero
vector, or anything else that would let retrieval silently resume returning
nonsense. Broken retrieval must look broken.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384  # must match the Qdrant collection dimension

# bge models are trained with an asymmetric query prefix; omitting it measurably
# degrades retrieval on short queries, which is most of what users type.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingsUnavailable(RuntimeError):
    """The embedding model could not be loaded or run."""


class EmbeddingsService:
    """Sentence embeddings for semantic retrieval.

    The model is loaded lazily on first use (it downloads on first run and is
    cached thereafter), and encoding is pushed to a worker thread so it never
    blocks the event loop.
    """

    def __init__(self, model_name: str = MODEL_NAME, dim: int = EMBEDDING_DIM) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None
        self._lock = asyncio.Lock()

    # ── model lifecycle ─────────────────────────────────────────────────────

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingsUnavailable(
                "fastembed is not installed. Semantic search is unavailable. "
                "Install it rather than falling back to a hash — random vectors "
                "produce confident nonsense."
            ) from exc

        logger.info("Loading embedding model %s", self.model_name)
        self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    async def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        async with self._lock:
            model = await asyncio.to_thread(self._load)
        vectors = await asyncio.to_thread(lambda: [v.tolist() for v in model.embed(list(texts))])

        for v in vectors:
            if len(v) != self.dim:
                raise EmbeddingsUnavailable(
                    f"{self.model_name} produced {len(v)} dimensions, expected "
                    f"{self.dim}. The Qdrant collection dimension must match; "
                    f"re-ingest rather than truncating."
                )
        return vectors

    # ── public API ──────────────────────────────────────────────────────────

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query, with the bge query prefix applied."""
        if not text or not text.strip():
            raise EmbeddingsUnavailable("cannot embed empty text")
        return (await self._encode([QUERY_PREFIX + text.strip()]))[0]

    async def embed_text(self, text: str) -> list[float]:
        """Embed a document or passage (no query prefix)."""
        if not text or not text.strip():
            raise EmbeddingsUnavailable("cannot embed empty text")
        return (await self._encode([text.strip()]))[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed many passages in one pass.

        Batched properly rather than looped — the previous implementation
        called the single-text path in a Python loop, which for a real model
        would be an order of magnitude slower on ingest.
        """
        cleaned = [t.strip() for t in texts if t and t.strip()]
        if not cleaned:
            return []
        return await self._encode(cleaned)

    @staticmethod
    def similarity(a: Sequence[float], b: Sequence[float]) -> float:
        """Cosine similarity, clamped to [0, 1].

        Not clamped to [0,1] because negatives are impossible — they are
        possible — but because a negative similarity and a zero similarity mean
        the same thing to a retrieval threshold.
        """
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nb)))


embeddings_service = EmbeddingsService()
