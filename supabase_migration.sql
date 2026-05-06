-- ============================================================
-- Daily Mate — Supabase Migration
-- Chạy file này trong Supabase SQL Editor
-- https://supabase.com/dashboard → SQL Editor → New query
-- ============================================================

-- 1. Bảng weather_cache (thay thế SQLite weather_cache)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS weather_cache (
    grid_key      TEXT PRIMARY KEY,
    grid_lat      REAL NOT NULL DEFAULT 0,
    grid_lon      REAL NOT NULL DEFAULT 0,
    weather_vector JSONB NOT NULL,
    raw_data      JSONB,
    temperature   REAL,
    aqi           REAL,
    wind_speed    REAL,
    condition     TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    hit_count     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_weather_cache_expires
    ON weather_cache (expires_at);

-- Cho phép anonymous read (mobile app gọi trực tiếp nếu cần)
ALTER TABLE weather_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON weather_cache
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "anon_read" ON weather_cache
    FOR SELECT TO anon USING (expires_at > now());


-- 2. Hàm increment hit count (gọi từ cache_manager._l2_inc_hit)
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION increment_cache_hit(p_grid_key TEXT)
RETURNS void LANGUAGE sql AS $$
    UPDATE weather_cache
    SET    hit_count = hit_count + 1
    WHERE  grid_key  = p_grid_key;
$$;


-- 3. Tự dọn dẹp các row hết hạn (chạy mỗi giờ)
-- Cần extension pg_cron — bật trong Supabase Dashboard > Database > Extensions
-- ────────────────────────────────────────────────────────────
-- SELECT cron.schedule(
--     'purge-expired-weather-cache',
--     '0 * * * *',
--     $$ DELETE FROM weather_cache WHERE expires_at < now() $$
-- );


-- 4. Kiểm tra kết quả
-- ────────────────────────────────────────────────────────────
SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name)))
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('weather_cache', 'session_feedback', 'request_log')
ORDER BY table_name;
