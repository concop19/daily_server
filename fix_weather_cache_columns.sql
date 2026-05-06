-- fix_weather_cache_columns.sql
-- Chạy trong Supabase SQL Editor để thêm các cột còn thiếu

ALTER TABLE weather_cache
  ADD COLUMN IF NOT EXISTS aqi        REAL,
  ADD COLUMN IF NOT EXISTS wind_speed REAL,
  ADD COLUMN IF NOT EXISTS condition  TEXT,
  ADD COLUMN IF NOT EXISTS raw_data   JSONB;

-- Xác nhận kết quả
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'weather_cache'
ORDER BY ordinal_position;
