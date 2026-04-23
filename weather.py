"""
weather.py — Xử lý thời tiết: fetch API, cache DB/memory, tính weather vector.
"""

import json
import math
import os
from datetime import datetime, timedelta, timezone

import requests

# ── Constants ────────────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
CELL_SIZE = 0.1

_WEATHER_CACHE: dict = {}  # In-memory cache (process lifetime)

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
    base = 30 if (6 <= hour < 22) else 60
    if aqi and aqi > 150:          base = min(base, 15)
    if wind_speed and wind_speed > 50: base = min(base, 15)
    if temperature and temperature > 40: base = min(base, 20)
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


# ── DB helpers ───────────────────────────────────────────────────────────────
def ensure_weather_cache_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS weather_cache (
            grid_key     TEXT PRIMARY KEY,
            grid_lat     REAL NOT NULL,
            grid_lon     REAL NOT NULL,
            cell_size    REAL NOT NULL DEFAULT 0.1,
            weather_vector TEXT NOT NULL,
            raw_data     TEXT,
            temperature  REAL,
            aqi          REAL,
            wind_speed   REAL,
            condition    TEXT,
            fetched_at   TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            hit_count    INTEGER DEFAULT 0,
            source_api   TEXT DEFAULT 'openweathermap'
        )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_weather_expires ON weather_cache(expires_at)"
    )
    db.commit()


# ── API fetch ────────────────────────────────────────────────────────────────
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


# ── Main entry point ─────────────────────────────────────────────────────────
def get_or_compute_weather(lat: float, lon: float, weather_override: dict | None,
                           db=None) -> dict:
    """
    Trả về weather_vector.
    Ưu tiên: override → in-memory cache → DB cache → OpenWeather API → hardcode fallback.
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
        _WEATHER_CACHE[key] = wv
        return wv

    if key in _WEATHER_CACHE:
        return _WEATHER_CACHE[key]

    if db is not None:
        try:
            ensure_weather_cache_table(db)
            now = datetime.now(timezone.utc)
            row = db.execute(
                "SELECT weather_vector, expires_at FROM weather_cache WHERE grid_key = ?",
                (key,)
            ).fetchone()
            if row:
                exp = datetime.fromisoformat(row["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now < exp:
                    wv = json.loads(row["weather_vector"])
                    _WEATHER_CACHE[key] = wv
                    db.execute(
                        "UPDATE weather_cache SET hit_count = hit_count + 1 WHERE grid_key = ?",
                        (key,)
                    )
                    db.commit()
                    return wv
        except Exception:
            pass

    # Hardcoded fallback
    wv = compute_weather_vector(33, 75, 12, 1008, 80, 7.5, get_current_season())
    _WEATHER_CACHE[key] = wv
    return wv


def fetch_and_cache_weather(lat: float, lon: float, db) -> dict:
    """
    Dùng cho route GET /api/weather.
    Trả full dict gồm flat fields + weather_vector + cache meta.
    """
    key, g_lat, g_lon = _grid_key(lat, lon)
    ensure_weather_cache_table(db)
    now = datetime.now(timezone.utc)

    row = db.execute(
        "SELECT weather_vector, raw_data, temperature, aqi, wind_speed, condition, "
        "expires_at, hit_count FROM weather_cache WHERE grid_key = ?",
        (key,)
    ).fetchone()

    if row:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now < exp:
            db.execute(
                "UPDATE weather_cache SET hit_count = hit_count + 1 WHERE grid_key = ?",
                (key,)
            )
            db.commit()
            wv = json.loads(row["weather_vector"])
            _WEATHER_CACHE[key] = wv
            raw_saved = json.loads(row["raw_data"] or "{}")
            flat = {
                "temperature": row["temperature"] or 30.0,
                "humidity":    float(raw_saved.get("main", {}).get("humidity", 70)),
                "wind_speed":  row["wind_speed"] or 10.0,
                "pressure":    float(raw_saved.get("main", {}).get("pressure", 1010)),
                "aqi":         row["aqi"] or 50.0,
                "uv_index":    0.0,
                "season":      get_current_season(),
                "condition":   row["condition"] or "Không rõ",
            }
            return {**flat, "weather_vector": wv,
                    "cache_hit": True, "expires_at": row["expires_at"]}

    try:
        raw, wv, flat, aqi_val, wind_kmh = fetch_from_openweather(g_lat, g_lon)
        ttl     = _adaptive_ttl(flat["temperature"], aqi_val, wind_kmh)
        expires = (now + timedelta(minutes=ttl)).isoformat()

        db.execute("""
            INSERT OR REPLACE INTO weather_cache
            (grid_key, grid_lat, grid_lon, cell_size, weather_vector, raw_data,
             temperature, aqi, wind_speed, condition, fetched_at, expires_at, hit_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)
        """, (key, g_lat, g_lon, CELL_SIZE,
              json.dumps(wv), json.dumps(raw),
              flat["temperature"], aqi_val, wind_kmh, flat["condition"],
              now.isoformat(), expires))
        db.commit()
        _WEATHER_CACHE[key] = wv
        return {**flat, "weather_vector": wv, "cache_hit": False, "expires_at": expires}

    except Exception as e:
        # Fallback: dùng row DB cũ dù hết hạn
        if row:
            wv = json.loads(row["weather_vector"])
            raw_saved = json.loads(row["raw_data"] or "{}")
            flat = {
                "temperature": row["temperature"] or 30.0,
                "humidity":    float(raw_saved.get("main", {}).get("humidity", 70)),
                "wind_speed":  row["wind_speed"] or 10.0,
                "pressure":    float(raw_saved.get("main", {}).get("pressure", 1010)),
                "aqi":         row["aqi"] or 50.0,
                "uv_index":    0.0,
                "season":      get_current_season(),
                "condition":   row["condition"] or "Không rõ",
            }
            return {**flat, "weather_vector": wv,
                    "cache_hit": True, "expires_at": row["expires_at"],
                    "warning":   f"OpenWeather lỗi, dùng cache cũ: {e}"}

        season = get_current_season()
        wv = compute_weather_vector(33, 75, 12, 1008, 80, 7.5, season)
        return {
            "temperature": 33.0, "humidity": 75.0, "wind_speed": 12.0,
            "pressure": 1008.0, "aqi": 80.0, "uv_index": 7.5,
            "season": season, "condition": "Không rõ (fallback)",
            "weather_vector": wv, "cache_hit": False, "expires_at": "",
            "warning": f"OpenWeather không khả dụng: {e}",
        }