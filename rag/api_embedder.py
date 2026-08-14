"""Jina AI Embeddings API provider for Nutrition RAG."""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import Any

import requests

from .chunker import KnowledgeChunk


DEFAULT_BASE_URL = "https://api.jina.ai/v1"
DEFAULT_MODEL = "jina-embeddings-v3"
DEFAULT_DIMENSIONS = 1024


class JinaAPIError(RuntimeError):
    """Raised when Jina returns an unusable embedding response."""


class JinaAPIEmbedder:
    """Generate normalized passage/query vectors through Jina's API."""

    provider = "jina_api"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        dimensions: int | None = None,
        batch_size: int = 32,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = (api_key or os.environ.get("JINA_API_KEY", "")).strip()
        if not self.api_key:
            raise RuntimeError("JINA_API_KEY chưa được cấu hình")
        self.base_url = (
            base_url or os.environ.get("JINA_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model_name = (
            model_name or os.environ.get("JINA_EMBEDDING_MODEL", DEFAULT_MODEL)
        ).strip()
        self.dimensions = int(
            dimensions
            or os.environ.get("JINA_EMBEDDING_DIM", str(DEFAULT_DIMENSIONS))
        )
        self.batch_size = max(1, int(batch_size))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self._session = requests.Session()

    def _request(self, texts: Sequence[str], task: str) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": list(texts),
            "task": task,
            "dimensions": self.dimensions,
            "normalized": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{self.base_url}/embeddings"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2**attempt))
                        continue
                response.raise_for_status()
                raw = response.json().get("data")
                if not isinstance(raw, list) or len(raw) != len(texts):
                    raise JinaAPIError("Jina trả về số vector không khớp số input")

                ordered = sorted(raw, key=lambda item: int(item.get("index", 0)))
                vectors = [item.get("embedding") for item in ordered]
                if any(not isinstance(vector, list) for vector in vectors):
                    raise JinaAPIError("Jina trả về embedding không hợp lệ")
                if any(len(vector) != self.dimensions for vector in vectors):
                    raise JinaAPIError(
                        f"Kích thước embedding khác {self.dimensions} dimensions"
                    )
                return [[float(value) for value in vector] for vector in vectors]
            except (requests.RequestException, ValueError, JinaAPIError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                break

        raise JinaAPIError(
            f"Jina Embeddings API thất bại: {type(last_error).__name__}"
        ) from last_error

    def _encode(self, texts: Sequence[str], task: str) -> list[list[float]]:
        results: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            results.extend(self._request(texts[start : start + self.batch_size], task))
        return results

    def embed_documents(self, chunks: Sequence[KnowledgeChunk]) -> list[list[float]]:
        return self._encode(
            [chunk.content for chunk in chunks],
            task="retrieval.passage",
        )

    def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            raise ValueError("Query không được rỗng.")
        return self._encode([query], task="retrieval.query")[0]

