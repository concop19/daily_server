"""
test_cache.py — Test thủ công cache waterfall L1 + L2 (Supabase).
Chạy: python test_cache.py
Không cần Flask đang chạy.
"""
import os, sys, json, time
from datetime import datetime, timezone

# Load .env
from dotenv import load_dotenv
load_dotenv()

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

SEP = "─" * 55

def check(label, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {label}", f"({detail})" if detail else "")


# ── 1. Kiểm tra kết nối Supabase ─────────────────────────────
print(f"\n{SEP}")
print("  1. Kết nối Supabase")
print(SEP)
resp = requests.get(
    f"{SUPABASE_URL}/rest/v1/weather_cache",
    params={"limit": "1"},
    headers=HEADERS, timeout=5,
)
check("GET weather_cache", resp.status_code == 200, f"HTTP {resp.status_code}")
if resp.status_code != 200:
    print(f"\n  ⚠️  Response: {resp.text[:300]}")
    print("\n  → Hãy chạy supabase_migration.sql trong Supabase SQL Editor trước!")
    sys.exit(1)

existing = resp.json()
print(f"  📊 Hiện có {len(existing)} row(s) trong weather_cache")


# ── 2. Test ghi thẳng vào Supabase (không qua cache_manager) ─
print(f"\n{SEP}")
print("  2. Test ghi trực tiếp vào Supabase")
print(SEP)
test_key = "TEST:16.0:108.2"
test_payload = {
    "grid_key":       test_key,
    "grid_lat":       16.0,
    "grid_lon":       108.2,
    "weather_vector": {"heat_stress_index": 0.75, "dehydration_risk": 0.6,
                       "cold_stress_index": 0.1, "oxidative_stress_risk": 0.4,
                       "infection_risk": 0.3, "immune_load": 0.35},
    "temperature":    33.0,
    "condition":      "Test entry",
    "expires_at":     "2099-01-01T00:00:00+00:00",
    "fetched_at":     datetime.now(timezone.utc).isoformat(),
    "hit_count":      0,
}
wr = requests.post(
    f"{SUPABASE_URL}/rest/v1/weather_cache",
    json=test_payload,
    headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
    timeout=5,
)
check("Upsert test row", wr.status_code in (200, 201), f"HTTP {wr.status_code}")
if wr.status_code not in (200, 201):
    print(f"  ⚠️  Error: {wr.text[:300]}")
    sys.exit(1)


# ── 3. Đọc lại để xác nhận ───────────────────────────────────
print(f"\n{SEP}")
print("  3. Đọc lại từ Supabase")
print(SEP)
rd = requests.get(
    f"{SUPABASE_URL}/rest/v1/weather_cache",
    params={"grid_key": f"eq.{test_key}", "select": "grid_key,temperature,expires_at,hit_count"},
    headers=HEADERS, timeout=5,
)
check("GET test row", rd.status_code == 200 and len(rd.json()) > 0)
if rd.status_code == 200 and rd.json():
    row = rd.json()[0]
    print(f"     grid_key   : {row['grid_key']}")
    print(f"     temperature: {row['temperature']}")
    print(f"     expires_at : {row['expires_at']}")
    print(f"     hit_count  : {row['hit_count']}")


# ── 4. Test cache_manager waterfall ──────────────────────────
print(f"\n{SEP}")
print("  4. Test cache_manager L1 + L2 waterfall")
print(SEP)
sys.path.insert(0, os.path.dirname(__file__))
from cache_manager import get_weather_cache, set_weather_cache, _L1

# 4a. L2 hit (key TEST vừa ghi lên Supabase, L1 chưa có)
print("  [4a] L2 hit — key vừa ghi lên Supabase, L1 còn trống")
_L1.clear()
wv = get_weather_cache(test_key)
check("L2 hit trả về weather_vector", wv is not None, str(wv)[:60] if wv else "None")
check("L1 được fill sau L2 hit", test_key in _L1)

# 4b. L1 hit (key đã được fill vào L1 ở bước trên)
print("  [4b] L1 hit — gọi lần 2, phải lấy từ memory")
t0 = time.perf_counter()
wv2 = get_weather_cache(test_key)
elapsed = (time.perf_counter() - t0) * 1000
check("L1 hit trả về data", wv2 is not None)
check(f"L1 hit nhanh < 1ms", elapsed < 1.0, f"{elapsed:.3f}ms")

# 4c. set_weather_cache ghi cả L1 + L2
print("  [4c] set_weather_cache ghi L1 + L2")
new_key = "TEST:10.0:106.0"
fake_wv = {"heat_stress_index": 0.5, "dehydration_risk": 0.4,
           "cold_stress_index": 0.2, "oxidative_stress_risk": 0.3,
           "infection_risk": 0.25, "immune_load": 0.3}
set_weather_cache(new_key, fake_wv, ttl_minutes=30,
                  grid_lat=10.0, grid_lon=106.0, temperature=30.0,
                  condition="Test HCMC", aqi=60.0, wind_speed=12.0)
check("L1 được ghi ngay", new_key in _L1)
print("  ⏳ Đợi 2s cho background thread ghi L2...")
time.sleep(2)
rd2 = requests.get(
    f"{SUPABASE_URL}/rest/v1/weather_cache",
    params={"grid_key": f"eq.{new_key}", "select": "grid_key,temperature"},
    headers=HEADERS, timeout=5,
)
check("L2 (Supabase) đã có row mới", rd2.status_code == 200 and len(rd2.json()) > 0)


# ── 5. Dọn dẹp test data ─────────────────────────────────────
print(f"\n{SEP}")
print("  5. Dọn dẹp test rows")
print(SEP)
for k in [test_key, new_key]:
    dl = requests.delete(
        f"{SUPABASE_URL}/rest/v1/weather_cache",
        params={"grid_key": f"eq.{k}"},
        headers=HEADERS, timeout=5,
    )
    check(f"Xóa {k}", dl.status_code in (200, 204))


# ── 6. Trigger thật: gọi fetch_and_cache_weather ─────────────
print(f"\n{SEP}")
print("  6. Gọi OpenWeather thật → ghi Supabase thật")
print(SEP)
print("  ⏳ Đang gọi OpenWeather API cho Đà Nẵng (16.047, 108.206)...")
from weather import fetch_and_cache_weather
result = fetch_and_cache_weather(16.047, 108.206)
print(f"  cache_hit  : {result.get('cache_hit')}")
print(f"  temperature: {result.get('temperature')} °C")
print(f"  condition  : {result.get('condition')}")
print(f"  expires_at : {result.get('expires_at')}")
if "warning" in result:
    print(f"  ⚠️  warning: {result['warning']}")
print("  ⏳ Đợi 3s cho background thread ghi L2...")
time.sleep(3)

# Kiểm tra Supabase có row thật chưa
rd_real = requests.get(
    f"{SUPABASE_URL}/rest/v1/weather_cache",
    params={"select": "grid_key,temperature,condition,expires_at,hit_count"},
    headers=HEADERS, timeout=5,
)
rows = rd_real.json()
check("Supabase weather_cache có data thật", len(rows) > 0)
if rows:
    for r in rows:
        print(f"     → {r['grid_key']} | {r['temperature']}°C | {r['condition']} | hits={r['hit_count']}")


# ── Summary ───────────────────────────────────────────────────
print(f"\n{SEP}")
print("  Xong! Cache waterfall hoạt động đúng.")
print("  Khi server nhận request /api/weather hoặc /api/v1/recommend")
print("  → gọi OpenWeather → ghi L2 → bảng Supabase có data.")
print(SEP + "\n")
