-- Daily Mate Ingredient Videos: Supabase migration
-- Run once in the Supabase SQL Editor or via Supabase CLI.

create table if not exists public.ingredient_videos (
    id                  bigserial primary key,
    ingredient_name     text not null,
    slug                text unique not null,
    video_url           text not null,
    category            text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists idx_ingredient_videos_slug
    on public.ingredient_videos (slug);

create index if not exists idx_ingredient_videos_category
    on public.ingredient_videos (category);

alter table public.ingredient_videos enable row level security;

-- Policy: service_role full access (Insert / Update / Delete / Select)
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'ingredient_videos'
          and policyname = 'ingredient_videos_service_role_all'
    ) then
        create policy ingredient_videos_service_role_all
            on public.ingredient_videos
            for all to service_role
            using (true)
            with check (true);
    end if;
end
$$;

-- Policy: anon read (Select) for public mobile app clients
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'ingredient_videos'
          and policyname = 'ingredient_videos_anon_read'
    ) then
        create policy ingredient_videos_anon_read
            on public.ingredient_videos
            for select to anon
            using (true);
    end if;
end
$$;
