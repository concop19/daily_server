# rate_limiter.py
import os
import requests
from datetime import datetime, timezone
from flask import g, jsonify
from functools import wraps

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}

def rate_limit(max_calls: int, window_seconds: int = 60):
    """
    Decorator: @rate_limit(10, 60) → tối đa 10 req/phút per uid.
    Dùng sliding window đơn giản: đếm row trong request_log.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            uid = getattr(g, "uid", None)
            if not uid:
                return jsonify({"error": "Unauthorized"}), 401

            since = datetime.now(timezone.utc).timestamp() - window_seconds
            since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()

            # Đếm request trong window
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/request_log",
                params={
                    "select":    "id",
                    "uid":       f"eq.{uid}",
                    "endpoint":  f"eq.{f.__name__}",
                    "logged_at": f"gte.{since_iso}",
                },
                headers={**_HEADERS, "Prefer": "count=exact", "Range": "0-0"},
                timeout=2,
            )
            count = int(resp.headers.get("Content-Range", "0/0").split("/")[-1])

            if count >= max_calls:
                return jsonify({
                    "error":       "Too many requests",
                    "retry_after": window_seconds,
                }), 429

            return f(*args, **kwargs)
        return decorated
    return decorator