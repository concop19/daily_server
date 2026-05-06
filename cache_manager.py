"""
cache_manager.py — L1 (in-memory) + L2 (Supabase) cache waterfall.

L1: process-local dict với TTL, mất khi restart (OK — chỉ là tốc độ).
L2: Supabase weather_cache table, persist qua restart / deploy.

Usage:
    from cache_manager import get_weather_cache, set_weather_cache, purge_expired_l1
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone

import requests

# ── Supabase config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

# ── L1: in-memory dict  {grid_key: (weather_vector_dict, expires_at_datetime)} ─
_L1: dict[str, tuple[dict, datetime]] = {}
_L1_LOCK = threading.Lock()

# ── L1 helpers ────────────────────────────────────────────────────────────────

def _l1_get(grid_key: str) -> dict | None:
    with _L1_LOCK:
        entry = _L1.get(grid_key)
    if entry is None:
        return None
    wv, exp = entry
    if datetime.now(timezone.utc) < exp:
        return wv
    # Expired — remove lazily
    with _L1_LOCK:
        _L1.pop(grid_key, None)
    return None


def _l1_set(grid_key: str, wv: dict, expires_at: datetime) -> None:
    with _L1_LOCK:
        _L1[grid_key] = (wv, expires_at)


def purge_expired_l1() -> int:
    """Xóa các entry L1 hết hạn. Gọi định kỳ nếu muốn, không bắt buộc."""
    now = datetime.now(timezone.utc)
    with _L1_LOCK:
        stale = [k for k, (_, exp) in _L1.items() if now >= exp]
        for k in stale:
            del _L1[k]
    return len(stale)

# ── L2: Supabase helpers ──────────────────────────────────────────────────────

def _l2_get(grid_key: str) -> dict | None:
    """Đọc từ Supabase weather_cache. Trả weather_vector dict hoặc None."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/weather_cache",
            params={
                "grid_key": f"eq.{grid_key}",
                "select":   "weather_vector,expires_at,hit_count",
            },
            headers=_HEADERS,
            timeout=3,
        )
        if not resp.ok:
            return None
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        raw_exp = row["expires_at"]
        exp = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= exp:
            return None          # hết hạn — miss
        wv = row["weather_vector"]
        if isinstance(wv, str):
            wv = json.loads(wv)
        # Increment hit_count async (fire-and-forget, không block)
        threading.Thread(target=_l2_inc_hit, args=(grid_key,), daemon=True).start()
        return wv
    except Exception:
        return None


def _l2_inc_hit(grid_key: str) -> None:
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/increment_cache_hit",
            json={"p_grid_key": grid_key},
            headers=_HEADERS,
            timeout=2,
        )
    except Exception:
        pass


def _l2_set(grid_key: str, wv: dict, expires_at: datetime, **meta) -> None:
    """Ghi / upsert vào Supabase weather_cache. Fire-and-forget."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    payload = {
        "grid_key":       grid_key,
        "weather_vector": wv,          # Supabase JSONB — không cần json.dumps
        "expires_at":     expires_at.isoformat(),
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "hit_count":      0,
        **meta,
    }
    threading.Thread(target=_l2_set_sync, args=(payload,), daemon=True).start()


def _l2_set_sync(payload: dict) -> None:
    try:
        # raw_data có thể là dict lớn — đảm bảo là dict thuần (JSONB)
        if "raw_data" in payload and not isinstance(payload["raw_data"], dict):
            payload.pop("raw_data", None)

        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/weather_cache",
            json=payload,
            headers={**_HEADERS, "Prefer": "resolution=merge-duplicates"},
            timeout=5,
        )
        if resp.status_code not in (200, 201):
            print(f"[cache_manager] L2 write FAILED {resp.status_code}: {resp.text[:200]}")
        else:
            print(f"[cache_manager] L2 write OK → {payload.get('grid_key')}")
    except Exception as e:
        print(f"[cache_manager] L2 write EXCEPTION: {e}")

# ── Public API ────────────────────────────────────────────────────────────────

def get_weather_cache(grid_key: str) -> dict | None:
    """
    Cache waterfall: L1 (memory) → L2 (Supabase).
    Trả weather_vector dict nếu hit, None nếu miss.
    """
    # L1 hit
    wv = _l1_get(grid_key)
    if wv is not None:
        return wv

    # L2 hit → fill L1
    wv = _l2_get(grid_key)
    if wv is not None:
        # Dùng exp gần đúng (30 phút) để fill L1 — tránh gọi thêm 1 query
        _l1_set(grid_key, wv, datetime.now(timezone.utc) + timedelta(minutes=30))
        return wv

    return None


def set_weather_cache(
    grid_key: str,
    wv: dict,
    ttl_minutes: int,
    grid_lat: float = 0.0,
    grid_lon: float = 0.0,
    temperature: float | None = None,
    condition: str | None = None,
    raw_data: dict | None = None,
    aqi: float | None = None,
    wind_speed: float | None = None,
) -> None:
    """
    Write-back vào cả L1 và L2.
    Gọi sau khi fetch từ OpenWeather thành công.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)

    # L1 — synchronous (nhanh)
    _l1_set(grid_key, wv, expires_at)

    # L2 — async background thread (không block request)
    meta = {
        "grid_lat":   grid_lat,
        "grid_lon":   grid_lon,
    }
    if temperature is not None:
        meta["temperature"] = temperature
    if condition is not None:
        meta["condition"] = condition
    if aqi is not None:
        meta["aqi"] = aqi
    if wind_speed is not None:
        meta["wind_speed"] = wind_speed
    if raw_data is not None:
        meta["raw_data"] = raw_data

    _l2_set(grid_key, wv, expires_at, **meta)
