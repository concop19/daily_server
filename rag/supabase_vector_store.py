"""Supabase pgvector store for the Nutrition RAG knowledge base."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import requests

from .chunker import KnowledgeChunk


DEFAULT_TABLE = "nutrition_chunks"
DEFAULT_RPC = "match_nutrition_chunks"


def _metadata_scalar(metadata: dict[str, Any], key: str) -> Any:
    value = metadata.get(key)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


class SupabaseVectorStore:
    """Store and query embeddings through Supabase REST + Postgres RPC."""

    def __init__(
        self,
        supabase_url: str | None = None,
        service_role_key: str | None = None,
        table_name: str | None = None,
        rpc_name: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.supabase_url = (
            supabase_url or os.environ.get("SUPABASE_URL", "")
        ).strip().rstrip("/")
        self.service_role_key = (
            service_role_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()
        if not self.supabase_url or not self.service_role_key:
            raise RuntimeError(
                "SUPABASE_URL và SUPABASE_SERVICE_ROLE_KEY chưa được cấu hình"
            )
        self.table_name = table_name or os.environ.get(
            "RAG_VECTOR_TABLE", DEFAULT_TABLE
        )
        self.rpc_name = rpc_name or os.environ.get("RAG_VECTOR_RPC", DEFAULT_RPC)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._session = requests.Session()
        self._headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _raise_response_error(self, response: requests.Response, action: str) -> None:
        if response.ok:
            return
        raise RuntimeError(
            f"Supabase {action} thất bại: HTTP {response.status_code}"
        )

    def index_chunks(self, chunks: list[KnowledgeChunk], embedder: Any) -> int:
        if not chunks:
            return 0
        vectors = embedder.embed_documents(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("Số vector không khớp số chunk.")

        rows: list[dict[str, Any]] = []
        knowledge_version = os.environ.get("RAG_KNOWLEDGE_VERSION", "v1")
        model_name = getattr(embedder, "model_name", "unknown")
        for chunk, vector in zip(chunks, vectors):
            metadata = dict(chunk.metadata)
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "content": chunk.content,
                    "metadata": metadata,
                    "rag_group": _metadata_scalar(metadata, "group"),
                    "section": _metadata_scalar(metadata, "section"),
                    "chunk_index": _metadata_scalar(metadata, "chunk_index"),
                    "embedding": vector,
                    "embedding_model": model_name,
                    "embedding_provider": getattr(embedder, "provider", "unknown"),
                    "content_hash": hashlib.sha256(
                        chunk.content.encode("utf-8")
                    ).hexdigest(),
                    "knowledge_version": knowledge_version,
                }
            )

        response = self._session.post(
            f"{self.supabase_url}/rest/v1/{self.table_name}",
            params={"on_conflict": "chunk_id"},
            headers={
                **self._headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=rows,
            timeout=self.timeout_seconds,
        )
        self._raise_response_error(response, "upsert vector")
        return len(rows)

    def query_by_embedding(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if n_results < 1:
            raise ValueError("n_results phải >= 1.")
        filter_group = (where or {}).get("group")
        payload = {
            "query_embedding": query_embedding,
            "match_threshold": float(
                os.environ.get("RAG_MATCH_THRESHOLD", "0.0")
            ),
            "match_count": n_results,
            "filter_group": filter_group,
        }
        response = self._session.post(
            f"{self.supabase_url}/rest/v1/rpc/{self.rpc_name}",
            headers=self._headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        self._raise_response_error(response, "query vector")
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError("Supabase RPC trả về format không hợp lệ")

        return {
            "ids": [[row.get("chunk_id") for row in rows]],
            "documents": [[row.get("content") for row in rows]],
            "metadatas": [[row.get("metadata") or {} for row in rows]],
            "distances": [
                [1.0 - float(row.get("similarity", 0.0)) for row in rows]
            ],
        }

    def query(
        self,
        query: str,
        embedder: Any,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if n_results < 1:
            raise ValueError("n_results phải >= 1.")
        query_vector = embedder.embed_query(query)
        return self.query_by_embedding(query_vector, n_results=n_results, where=where)

