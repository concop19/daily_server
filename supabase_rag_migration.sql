-- Daily Mate Nutrition RAG: Supabase pgvector migration
-- Run once in the Supabase SQL Editor or through Supabase CLI.

create extension if not exists vector with schema public;

create table if not exists public.nutrition_chunks (
    id                  bigserial primary key,
    chunk_id            text unique not null,
    doc_id              text not null,
    content             text not null,
    metadata            jsonb not null default '{}'::jsonb,
    rag_group           text,
    section             text,
    chunk_index         integer,
    embedding           public.vector(1024) not null,
    embedding_model     text not null,
    embedding_provider  text not null,
    content_hash        text not null,
    knowledge_version   text not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists nutrition_chunks_doc_id_idx
    on public.nutrition_chunks (doc_id);

create index if not exists nutrition_chunks_group_idx
    on public.nutrition_chunks (rag_group);

create index if not exists nutrition_chunks_embedding_hnsw_idx
    on public.nutrition_chunks
    using hnsw (embedding vector_cosine_ops);

alter table public.nutrition_chunks enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'nutrition_chunks'
          and policyname = 'nutrition_chunks_service_role_all'
    ) then
        create policy nutrition_chunks_service_role_all
            on public.nutrition_chunks
            for all to service_role
            using (true)
            with check (true);
    end if;
end
$$;

create or replace function public.match_nutrition_chunks (
    query_embedding public.vector(1024),
    match_threshold float,
    match_count int,
    filter_group text default null
)
returns table (
    chunk_id text,
    doc_id text,
    content text,
    metadata jsonb,
    similarity float
)
language sql stable
as $$
    select
        n.chunk_id,
        n.doc_id,
        n.content,
        n.metadata,
        1 - (n.embedding <=> query_embedding) as similarity
    from public.nutrition_chunks n
    where (filter_group is null or n.rag_group = filter_group)
      and 1 - (n.embedding <=> query_embedding) >= match_threshold
    order by n.embedding <=> query_embedding
    limit greatest(match_count, 1);
$$;
