"""Build the Nutrition RAG index in Supabase pgvector."""

from __future__ import annotations

from dotenv import load_dotenv

from .api_embedder import JinaAPIEmbedder
from .chunker import chunk_documents
from .knowledge_loader import load_knowledge
from .supabase_vector_store import SupabaseVectorStore


def build_index() -> int:
    load_dotenv()
    chunks = chunk_documents(load_knowledge())
    embedder = JinaAPIEmbedder()
    store = SupabaseVectorStore()
    return store.index_chunks(chunks, embedder)


if __name__ == "__main__":
    print(f"Indexed chunks: {build_index()}")

