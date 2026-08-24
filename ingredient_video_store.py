"""
ingredient_video_store.py — Supabase Data Access Layer for Ingredient Videos.
Primary storage: Supabase PostgreSQL (PostgREST table `ingredient_videos`)
Fallback & Cache: In-memory list + data/ingredient_videos.json
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from ingredient_video_utils import slugify_vietnamese

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FALLBACK_FILE = DATA_DIR / "ingredient_videos.json"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

# Local cache & fallback state
_local_videos: list[dict[str, Any]] = []
_local_lock = threading.Lock()
_loaded = False


def _load_local():
    global _local_videos, _loaded
    with _local_lock:
        if _loaded:
            return
        if FALLBACK_FILE.exists():
            try:
                raw = json.loads(FALLBACK_FILE.read_text(encoding="utf-8"))
                _local_videos = raw.get("data", [])
            except Exception as e:
                logger.warning(f"[IngredientVideoStore] Failed reading fallback file: {e}")
                _local_videos = []
        else:
            _local_videos = []
        _loaded = True


def _persist_local():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "table": "ingredient_videos",
            "count": len(_local_videos),
            "data": _local_videos,
        }
        FALLBACK_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"[IngredientVideoStore] Failed saving local fallback: {e}")


def _upsert_local(item: dict[str, Any]):
    _load_local()
    with _local_lock:
        slug = item["slug"]
        for idx, existing in enumerate(_local_videos):
            if existing.get("slug") == slug:
                _local_videos[idx].update(item)
                _persist_local()
                return _local_videos[idx]
        _local_videos.append(item)
        _persist_local()
        return item


def _get_local_list(category: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
    _load_local()
    with _local_lock:
        items = list(_local_videos)

    if category:
        items = [i for i in items if (i.get("category") or "").lower() == category.lower()]
    if search:
        s = slugify_vietnamese(search)
        items = [i for i in items if s in slugify_vietnamese(i.get("ingredient_name", ""))]

    items.sort(key=lambda x: str(x.get("ingredient_name", "")).lower())
    return [
        {
            "ingredient_name": i.get("ingredient_name", ""),
            "slug":            i.get("slug", ""),
            "video_url":       i.get("video_url", ""),
            "category":        i.get("category"),
        }
        for i in items
        if i.get("video_url")
    ]


def upsert_ingredient_video(
    ingredient_name: str,
    video_url: str,
    category: str | None = None,
    slug: str | None = None,
) -> dict[str, Any]:
    """
    Upsert ingredient video to Supabase with slug as unique conflict target.
    Falls back to local in-memory/JSON store if Supabase is unavailable.
    """
    if not slug:
        slug = slugify_vietnamese(ingredient_name)

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "ingredient_name": ingredient_name.strip(),
        "slug":            slug,
        "video_url":       video_url.strip(),
        "category":        category.strip() if category else None,
        "updated_at":      now_iso,
    }

    # Always update local cache for fast lookup & resilience
    _upsert_local(record)

    # Supabase PostgREST upsert
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/ingredient_videos?on_conflict=slug",
                headers={
                    **_HEADERS,
                    "Prefer": "resolution=merge-duplicates,return=representation",
                },
                json=record,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                if rows and isinstance(rows, list):
                    saved = rows[0]
                    return {
                        "ingredient_name": saved.get("ingredient_name"),
                        "slug":            saved.get("slug"),
                        "video_url":       saved.get("video_url"),
                        "category":        saved.get("category"),
                    }
            else:
                logger.warning(
                    f"[IngredientVideoStore] Supabase upsert status {resp.status_code}: {resp.text[:150]}"
                )
        except Exception as e:
            logger.warning(f"[IngredientVideoStore] Supabase upsert error, used local store: {e}")

    return {
        "ingredient_name": record["ingredient_name"],
        "slug":            record["slug"],
        "video_url":       record["video_url"],
        "category":        record["category"],
    }


def get_ingredient_videos(
    category: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve list of ingredient videos ordered by ingredient_name.
    Only returns records with non-empty video_url.
    """
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            params = {
                "select": "ingredient_name,slug,video_url,category",
                "order":  "ingredient_name.asc",
            }
            if category:
                params["category"] = f"eq.{category}"

            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/ingredient_videos",
                headers=_HEADERS,
                params=params,
                timeout=5,
            )
            if resp.status_code == 200:
                rows = resp.json()
                valid = [
                    {
                        "ingredient_name": r.get("ingredient_name", ""),
                        "slug":            r.get("slug", ""),
                        "video_url":       r.get("video_url", ""),
                        "category":        r.get("category"),
                    }
                    for r in rows
                    if r.get("video_url")
                ]
                if search:
                    s = slugify_vietnamese(search)
                    valid = [i for i in valid if s in slugify_vietnamese(i.get("ingredient_name", ""))]
                return valid
            else:
                logger.warning(
                    f"[IngredientVideoStore] Supabase fetch status {resp.status_code}: {resp.text[:150]}"
                )
        except Exception as e:
            logger.warning(f"[IngredientVideoStore] Supabase fetch error, fallback to local: {e}")

    return _get_local_list(category=category, search=search)
