"""
weather.py — Xử lý thời tiết: fetch API, cache L1/L2, tính weather vector.

Cache strategy:
  L1 (in-memory, process-fast) + L2 (Supabase, persist qua restart)
  → xem cache_manager.py

FIX ID-015: Thêm _FLAT_CACHE để lưu flat fields (temperature, humidity…)
  kèm theo weather_vector. Tránh trả hardcoded 30.0°C khi cache hit.
"""

import os
import threading
from datetime import datetime, timedelta, timezone

import requests
from cache_manager import get_weather_cache, set_weather_cache

# ── Constants ────────────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
CELL_SIZE = 0.1

_OW_CONDITION_VI = {
    "thunderstorm": "Giông bão",
    "drizzle":      "Mưa phùn",
    "rain":         "Mưa",
    "snow":         "Tuyết",
    "mist":         "Sương mù",
    "fog":          "Sương dày",
    "haze":         "Mờ sương",
    "clear":        "Trời quang",
    "clouds":       "Có mây",
}

# FIX ID-015: Cache riêng cho flat fields (temperature, humidity, v.v.)
# key = grid_key, value = (flat_dict, expires_at)
_FLAT_CACHE: dict[str, tuple[dict, datetime]] = {}
_FLAT_LOCK = threading.Lock()

def _flat_cache_get(grid_key: str) -> dict | None:
    with _FLAT_LOCK:
        entry = _FLAT_CACHE.get(grid_key)
    if not entry:
        return None
    flat, exp = entry
    if datetime.now(timezone.utc) < exp:
        return flat
    with _FLAT_LOCK:
        _FLAT_CACHE.pop(grid_key, None)
    return None

def _flat_cache_set(grid_key: str, flat: dict, expires_at: datetime) -> None:
    with _FLAT_LOCK:
        _FLAT_CACHE[grid_key] = (flat, expires_at)


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_current_season() -> str:
    m = datetime.now().month
    if m in (12, 1, 2):  return "winter"
    if m in (3, 4, 5):   return "spring"
    if m in (6, 7, 8):   return "summer"
    return "autumn"


def _grid_key(lat: float, lon: float):
    g_lat = round(round(lat / CELL_SIZE) * CELL_SIZE, 1)
    g_lon = round(round(lon / CELL_SIZE) * CELL_SIZE, 1)
    return f"{g_lat}:{g_lon}", g_lat, g_lon


def _norm(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _adaptive_ttl(temperature, aqi, wind_speed) -> int:
    """Trả về TTL (phút). Thời tiết cực đoan → TTL ngắn hơn."""
    hour = datetime.now().hour
    base = 15 if (6 <= hour < 22) else 30   # giảm từ 30/60 → 15/30
    if aqi and aqi > 150:              base = min(base, 10)
    if wind_speed and wind_speed > 50: base = min(base, 10)
    if temperature and temperature > 40: base = min(base, 10)
    return base


def _ow_condition_vi(raw: dict) -> str:
    try:
        main = raw["weather"][0]["main"].lower()
        return _OW_CONDITION_VI.get(main, raw["weather"][0]["description"].capitalize())
    except Exception:
        return "Không rõ"


# ── Core computation ─────────────────────────────────────────────────────────
def compute_weather_vector(t, humidity, wind, pressure, aqi, uv, season) -> dict:
    tn   = _norm(t,        10.0, 42.0)
    hn   = _norm(humidity, 20.0, 100.0)
    wn   = _norm(wind,     0.0,  80.0)
    aqin = _norm(aqi,      0.0,  300.0)
    uvn  = _norm(uv,       0.0,  11.0)
    pn   = _norm(pressure, 980.0, 1020.0)

    heat_stress = min(1.0, 0.6 * tn + 0.4 * hn)
    cold_stress = min(1.0, max(0.0, 1.0 - tn) * 0.7 + wn * 0.3)
    dehydration = min(1.0, 0.5 * heat_stress + 0.3 * wn + 0.2 * aqin)
    season_ox   = 0.8 if season == "summer" else 0.3
    oxidative   = min(1.0, 0.4 * uvn + 0.3 * aqin + 0.3 * season_ox)
    infection   = min(1.0, 0.4 * (1 - pn) + 0.6 * aqin)
    season_im   = 0.8 if season in ("spring", "autumn") else 0.2
    immune_load = min(1.0, 0.4 * aqin + 0.3 * infection + 0.3 * season_im)

    return {
        "heat_stress_index":     round(heat_stress, 4),
        "dehydration_risk":      round(dehydration, 4),
        "cold_stress_index":     round(cold_stress, 4),
        "oxidative_stress_risk": round(oxidative,   4),
        "infection_risk":        round(infection,   4),
        "immune_load":           round(immune_load, 4),
    }


# ── API fetch ─────────────────────────────────────────────────────────────────
def fetch_from_openweather(lat: float, lon: float) -> tuple:
    """Gọi OpenWeather + Air Pollution API. Trả (raw, wv, flat, aqi_val, wind_kmh)."""
    if not OPENWEATHER_API_KEY:
        raise ValueError("OPENWEATHER_API_KEY chưa được set")

    ow_resp = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"},
        timeout=6,
    )
    ow_resp.raise_for_status()
    raw = ow_resp.json()

    temp     = float(raw["main"]["temp"])
    humidity = float(raw["main"]["humidity"])
    wind_ms  = float(raw["wind"].get("speed", 0))
    wind_kmh = round(wind_ms * 3.6, 1)
    pressure = float(raw["main"]["pressure"])
    uv_index = 0.0

    aqi_val = 50.0
    try:
        ap_resp = requests.get(
            "https://api.openweathermap.org/data/2.5/air_pollution",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
            timeout=5,
        )
        if ap_resp.ok:
            aqi_index = ap_resp.json()["list"][0]["main"]["aqi"]
            aqi_val = float({1: 25, 2: 60, 3: 100, 4: 160, 5: 220}.get(aqi_index, 50))
    except Exception:
        pass

    season = get_current_season()
    wv = compute_weather_vector(temp, humidity, wind_kmh, pressure, aqi_val, uv_index, season)

    flat = {
        "temperature": round(temp, 1),
        "humidity":    round(humidity, 1),
        "wind_speed":  wind_kmh,
        "pressure":    round(pressure, 1),
        "aqi":         round(aqi_val, 1),
        "uv_index":    uv_index,
        "season":      season,
        "condition":   _ow_condition_vi(raw),
    }
    return raw, wv, flat, aqi_val, wind_kmh


# ── Main entry points ─────────────────────────────────────────────────────────

def get_or_compute_weather(lat: float, lon: float, weather_override: dict | None,
                           db=None) -> dict:
    """
    Trả về weather_vector.
    Ưu tiên: override → L1 cache → L2 cache (Supabase) → OpenWeather API → hardcode fallback.
    Tham số db giữ lại để không break caller, nhưng không dùng nữa.
    """
    if weather_override and "weather_vector" in weather_override:
        return weather_override["weather_vector"]

    key, g_lat, g_lon = _grid_key(lat, lon)

    if weather_override:
        wv = compute_weather_vector(
            weather_override.get("temperature", 30),
            weather_override.get("humidity",    70),
            weather_override.get("wind_speed",  10),
            weather_override.get("pressure",    1010),
            weather_override.get("aqi",         50),
            weather_override.get("uv_index",    6),
            weather_override.get("season",      get_current_season()),
        )
        set_weather_cache(key, wv, ttl_minutes=30, grid_lat=g_lat, grid_lon=g_lon)
        return wv

    # L1 + L2 waterfall
    cached = get_weather_cache(key)
    if cached is not None:
        return cached

    # OpenWeather fetch
    try:
        _, wv, flat, aqi_val, wind_kmh = fetch_from_openweather(g_lat, g_lon)
        ttl = _adaptive_ttl(flat["temperature"], aqi_val, wind_kmh)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
        set_weather_cache(
            key, wv, ttl_minutes=ttl,
            grid_lat=g_lat, grid_lon=g_lon,
            temperature=flat["temperature"],
            condition=flat["condition"],
            aqi=aqi_val,
            wind_speed=wind_kmh,
        )
        # FIX ID-015: lưu flat fields vào _FLAT_CACHE để fetch_and_cache_weather dùng
        _flat_cache_set(key, flat, expires_at)
        return wv
    except Exception:
        pass

    # Hardcoded fallback
    wv = compute_weather_vector(33, 75, 12, 1008, 80, 7.5, get_current_season())
    set_weather_cache(key, wv, ttl_minutes=15, grid_lat=g_lat, grid_lon=g_lon)
    return wv


def fetch_and_cache_weather(lat: float, lon: float, db=None) -> dict:
    """
    Dùng cho route GET /api/weather.
    Trả full dict gồm flat fields + weather_vector + cache meta.
    Tham số db giữ lại để không break caller, nhưng không dùng nữa.
    """
    key, g_lat, g_lon = _grid_key(lat, lon)
    now = datetime.now(timezone.utc)

    # L1 + L2 waterfall cho vector
    cached_wv = get_weather_cache(key)
    if cached_wv is not None:
        # FIX ID-015: trả flat fields thực nếu có trong _FLAT_CACHE,
        # thay vì hardcode 30.0°C gây misleading UX.
        cached_flat = _flat_cache_get(key)
        if cached_flat:
            return {
                **cached_flat,
                "weather_vector": cached_wv,
                "cache_hit":  True,
                "expires_at": "",
            }
        # Flat cache miss (server restart): _FLAT_CACHE bị xóa nhưng L2 vẫn còn
        # weather_vector. Thử fetch fresh từ OpenWeather để lấy lại flat fields
        # thay vì trả về None / "Dữ liệu cũ (cache)" gây misleading UX.
        try:
            raw, wv, flat, aqi_val, wind_kmh = fetch_from_openweather(g_lat, g_lon)
            ttl     = _adaptive_ttl(flat["temperature"], aqi_val, wind_kmh)
            expires = now + timedelta(minutes=ttl)
            set_weather_cache(
                key, wv, ttl_minutes=ttl,
                grid_lat=g_lat, grid_lon=g_lon,
                temperature=flat["temperature"],
                condition=flat["condition"],
                aqi=aqi_val,
                wind_speed=wind_kmh,
                raw_data=raw,
            )
            _flat_cache_set(key, flat, expires)
            return {**flat, "weather_vector": wv, "cache_hit": False, "expires_at": expires.isoformat()}
        except Exception:
            pass
        # OpenWeather cũng thất bại → trả stale vector + báo rõ lý do
        season = get_current_season()
        return {
            "temperature": None,
            "humidity":    None,
            "wind_speed":  None,
            "pressure":    None,
            "aqi":         None,
            "uv_index":    None,
            "season":      season,
            "condition":   "Không thể kết nối thời tiết",
            "weather_vector": cached_wv,
            "cache_hit":   True,
            "expires_at":  "",
            "warning":     "Flat cache miss sau server restart, OpenWeather không khả dụng",
        }

    # Fetch từ OpenWeather
    try:
        raw, wv, flat, aqi_val, wind_kmh = fetch_from_openweather(g_lat, g_lon)
        ttl     = _adaptive_ttl(flat["temperature"], aqi_val, wind_kmh)
        expires = now + timedelta(minutes=ttl)

        set_weather_cache(
            key, wv, ttl_minutes=ttl,
            grid_lat=g_lat, grid_lon=g_lon,
            temperature=flat["temperature"],
            condition=flat["condition"],
            aqi=aqi_val,
            wind_speed=wind_kmh,
            raw_data=raw,
        )
        # FIX ID-015: lưu flat vào _FLAT_CACHE
        _flat_cache_set(key, flat, expires)
        return {**flat, "weather_vector": wv, "cache_hit": False, "expires_at": expires.isoformat()}

    except Exception as e:
        season = get_current_season()
        wv = compute_weather_vector(33, 75, 12, 1008, 80, 7.5, season)
        return {
            "temperature": 33.0, "humidity": 75.0, "wind_speed": 12.0,
            "pressure": 1008.0, "aqi": 80.0, "uv_index": 7.5,
            "season": season, "condition": "Không rõ (fallback)",
            "weather_vector": wv, "cache_hit": False, "expires_at": "",
            "warning": f"OpenWeather không khả dụng: {e}",
        }
