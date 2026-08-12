"""Local Jina embedding provider for Nutrition RAG."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from .chunker import KnowledgeChunk


DEFAULT_MODEL = "jinaai/jina-embeddings-v3"


class JinaEmbedder:
    """Encode RAG passages and user queries with the same local model.

    Jina uses different task adapters for documents and search queries. It is
    important to keep this distinction: passages use ``retrieval.passage``;
    user questions use ``retrieval.query``.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        batch_size: int = 8,
        truncate_dim: int | None = 1024,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.truncate_dim = truncate_dim
        self.model = SentenceTransformer(
            model_name,
            trust_remote_code=True,
            device=device,
        )

    def _encode(self, texts: Sequence[str], task: str) -> np.ndarray:
        if not texts:
            dimension = self.truncate_dim or 0
            return np.empty((0, dimension), dtype=np.float32)
        kwargs: dict[str, Any] = {
            "task": task,
            "batch_size": self.batch_size,
            "normalize_embeddings": True,
            "convert_to_numpy": True,
            "show_progress_bar": False,
        }
        if self.truncate_dim is not None:
            kwargs["truncate_dim"] = self.truncate_dim
        vectors = self.model.encode(list(texts), **kwargs)
        return np.asarray(vectors, dtype=np.float32)

    def embed_documents(self, chunks: Sequence[KnowledgeChunk]) -> np.ndarray:
        """Create normalized passage vectors for Chroma indexing."""

        return self._encode(
            [chunk.content for chunk in chunks],
            task="retrieval.passage",
        )

    def embed_query(self, query: str) -> np.ndarray:
        """Create one normalized vector for a user search query."""

        if not query.strip():
            raise ValueError("Query không được rỗng.")
        return self._encode([query], task="retrieval.query")[0]


if __name__ == "__main__":
    from .chunker import chunk_documents
    from .knowledge_loader import load_knowledge

    chunks = chunk_documents(load_knowledge())
    embedder = JinaEmbedder()
    vectors = embedder.embed_documents(chunks)
    query_vector = embedder.embed_query("Người bị tiểu đường cần quan tâm chỉ số nào?")
    print(f"model={embedder.model_name}")
    print(f"chunks={len(chunks)}")
    print(f"document_vectors_shape={vectors.shape}")
    print(f"query_vector_shape={query_vector.shape}")
    print(f"query_vector_norm={np.linalg.norm(query_vector):.4f}")

