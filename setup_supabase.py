"""
setup_supabase.py — Chạy 1 lần để tạo bảng weather_cache trên Supabase.
Dùng: python setup_supabase.py
"""
import os, sys
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

SQL_STEPS = [
    (
        "Tạo bảng weather_cache",
        """
        CREATE TABLE IF NOT EXISTS weather_cache (
            grid_key       TEXT PRIMARY KEY,
            grid_lat       REAL NOT NULL DEFAULT 0,
            grid_lon       REAL NOT NULL DEFAULT 0,
            weather_vector JSONB NOT NULL,
            raw_data       JSONB,
            temperature    REAL,
            aqi            REAL,
            wind_speed     REAL,
            condition      TEXT,
            fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at     TIMESTAMPTZ NOT NULL,
            hit_count      INTEGER NOT NULL DEFAULT 0
        )
        """,
    ),
    (
        "Tạo index expires_at",
        "CREATE INDEX IF NOT EXISTS idx_weather_cache_expires ON weather_cache (expires_at)",
    ),
    (
        "Enable RLS",
        "ALTER TABLE weather_cache ENABLE ROW LEVEL SECURITY",
    ),
    (
        "Policy: service_role full access",
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename='weather_cache' AND policyname='service_role_all'
          ) THEN
            CREATE POLICY service_role_all ON weather_cache
              FOR ALL TO service_role USING (true) WITH CHECK (true);
          END IF;
        END $$
        """,
    ),
    (
        "Policy: anon read valid cache",
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE tablename='weather_cache' AND policyname='anon_read'
          ) THEN
            CREATE POLICY anon_read ON weather_cache
              FOR SELECT TO anon USING (expires_at > now());
          END IF;
        END $$
        """,
    ),
    (
        "Hàm increment_cache_hit",
        """
        CREATE OR REPLACE FUNCTION increment_cache_hit(p_grid_key TEXT)
        RETURNS void LANGUAGE sql AS $$
            UPDATE weather_cache
            SET    hit_count = hit_count + 1
            WHERE  grid_key  = p_grid_key;
        $$
        """,
    ),
]


def run_sql(label: str, sql: str) -> bool:
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        json={"query": sql.strip()},
        headers=HEADERS,
        timeout=15,
    )
    # Supabase không có exec_sql mặc định — dùng pg endpoint thay thế
    # Thử qua /pg endpoint
    resp2 = requests.post(
        f"{SUPABASE_URL}/pg",
        json={"query": sql.strip()},
        headers=HEADERS,
        timeout=15,
    )
    if resp2.status_code in (200, 201):
        print(f"  ✅ {label}")
        return True
    print(f"  ⚠️  {label}: HTTP {resp2.status_code} — {resp2.text[:120]}")
    return False


def check_table_exists() -> bool:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/weather_cache",
        params={"limit": "1", "select": "grid_key"},
        headers=HEADERS,
        timeout=5,
    )
    return resp.status_code == 200


print("=" * 55)
print("  Daily Mate — Supabase setup")
print("=" * 55)

if check_table_exists():
    print("\n✅ Bảng weather_cache đã tồn tại — không cần tạo lại.")
    print("   Nếu muốn recreate, xóa bảng trước trong Supabase Dashboard.\n")
    sys.exit(0)

print("\nBảng weather_cache chưa có. Tạo qua Supabase SQL Editor:\n")
print("  1. Mở: https://supabase.com/dashboard/project/cluqexxdclgtybmryati/sql")
print("  2. Chạy nội dung file: supabase_migration.sql\n")
print("Hoặc dùng Supabase CLI:")
print("  supabase db push --db-url <your_db_url>\n")
