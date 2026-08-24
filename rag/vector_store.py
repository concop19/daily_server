"""Persistent Chroma vector store for the Nutrition RAG knowledge base."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import chromadb

from .chunker import KnowledgeChunk, chunk_documents
from .embedder import JinaEmbedder
from .knowledge_loader import load_knowledge


DEFAULT_DB_PATH = Path("data/chroma_nutrition")
DEFAULT_COLLECTION = "nutrition_knowledge"


def _chroma_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Convert document metadata to Chroma-supported scalar values."""

    result: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, list):
            result[key] = ",".join(str(item) for item in value)
        else:
            result[key] = str(value)
    return result


class NutritionVectorStore:
    """Index and query Nutrition RAG chunks in a local Chroma collection."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        self.db_path = Path(db_path)
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Daily Mate Nutrition RAG knowledge"},
        )

    def index_chunks(
        self,
        chunks: list[KnowledgeChunk],
        embedder: JinaEmbedder | None = None,
    ) -> int:
        """Embed and upsert chunks. Re-running is safe because IDs are stable."""

        if not chunks:
            return 0
        embedder = embedder or JinaEmbedder()
        vectors = embedder.embed_documents(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("Số vector không khớp số chunk.")

        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            embeddings=vectors.tolist(),
            metadatas=[_chroma_metadata(chunk.metadata) for chunk in chunks],
        )
        return len(chunks)

    def query_by_embedding(
        self,
        query_embedding: list[float] | Any,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve nearest chunks using a precomputed embedding vector."""
        if n_results < 1:
            raise ValueError("n_results phải >= 1.")
        vector = query_embedding.tolist() if hasattr(query_embedding, "tolist") else list(query_embedding)
        kwargs: dict[str, Any] = {
            "query_embeddings": [vector],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    def query(
        self,
        query: str,
        embedder: JinaEmbedder,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve the nearest chunks for a user query."""
        if n_results < 1:
            raise ValueError("n_results phải >= 1.")
        query_vector = embedder.embed_query(query)
        return self.query_by_embedding(query_vector, n_results=n_results, where=where)


def build_index(
    db_path: str | Path = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    chunks = chunk_documents(load_knowledge())
    store = NutritionVectorStore(db_path, collection_name)
    return store.index_chunks(chunks)


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    count = build_index()
    print(f"Indexed chunks: {count}")
    store = NutritionVectorStore()
    print(f"Collection count: {store.collection.count()}")

