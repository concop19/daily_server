# monitoring.py
import os
import requests
from datetime import datetime
from flask import g, request

SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_SERVICE_ROLE_KEY"]   # service_role, không dùng anon

_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",   # không trả row về, nhanh hơn
}

def _insert_log(payload: dict):
    """Ghi log bất đồng bộ để không block response."""
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/request_log",
            json=payload,
            headers=_HEADERS,
            timeout=2,
        )
    except Exception:
        pass   # log fail không được crash app chính


def init_monitoring(app):
    @app.before_request
    def _start_timer():
        g.req_start = datetime.utcnow()

    @app.after_request
    def _log_request(response):
        # Bỏ qua health check và static
        if request.endpoint in ("health", "static"):
            return response
        try:
            latency_ms = (datetime.utcnow() - g.req_start).total_seconds() * 1000
            _insert_log({
                "uid":         getattr(g, "uid", None),
                "endpoint":    request.endpoint,
                "method":      request.method,
                "status_code": response.status_code,
                "latency_ms":  round(latency_ms, 2),
                "logged_at":   datetime.utcnow().isoformat(),
            })
        except Exception:
            pass
        return response