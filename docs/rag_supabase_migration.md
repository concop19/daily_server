# Nutrition RAG: Jina API + Supabase pgvector

## Runtime configuration

Keep the following values in the server-side `.env` only:

```env
JINA_API_KEY=...
JINA_BASE_URL=https://api.jina.ai/v1
JINA_EMBEDDING_MODEL=jina-embeddings-v3
JINA_EMBEDDING_DIM=1024

SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
RAG_VECTOR_BACKEND=supabase
RAG_VECTOR_TABLE=nutrition_chunks
RAG_VECTOR_RPC=match_nutrition_chunks
RAG_KNOWLEDGE_VERSION=v1
```

Do not expose either API key to the mobile client or commit `.env`.

## One-time database migration

Run `supabase_rag_migration.sql` in the Supabase SQL Editor or with the
Supabase CLI. The migration creates the `nutrition_chunks` table, its vector
index, RLS policy, and the `match_nutrition_chunks` RPC function.

## Build the index

After the migration has succeeded:

```bash
python -m rag.index_supabase
```

The indexer reads the Markdown files in `knowledge/`, creates the same chunks
as the current local RAG, calls Jina with `retrieval.passage`, and upserts the
vectors into Supabase.

## Switch and verify

Set `RAG_VECTOR_BACKEND=supabase`, restart the server, then run:

```bash
python -m rag.evaluate_retriever
```

To roll back, set `RAG_VECTOR_BACKEND=local` and restart. The original local
Chroma path remains available until the Supabase backend has been validated.

