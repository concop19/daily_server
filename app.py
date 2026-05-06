"""
app.py — Flask application: DB setup + HTTP routes.
Import logic từ weather.py và pipeline.py.
"""

import hashlib
import json
import math
import os
import random as _random
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from auth_middleware import require_auth, require_admin
from monitoring import init_monitoring
from rate_limiter import rate_limit
from weather import (
    compute_weather_vector,
    fetch_and_cache_weather,
    get_current_season,
    get_or_compute_weather,
)
from pipeline import (
    PANTRY_CATEGORIES,
    TASTE_DEFAULTS,
    build_constraint_profile,
    compute_demand,
    compute_dish_boost,
    compute_personal_vector,
    compute_soft_mult,
    filter_dishes,
    get_dish_availability,
    rank_and_explain,
    resolve_location,
    resolve_taste_weight,
    score_dish,
)

# ── App & DB setup ─────────────────────────────────────────────────────────────
# FIX ID-014: Bỏ Windows path hardcode — dùng relative fallback "recipe.db"
# kế cạnh app.py, hoạt động cả Linux lẫn Windows.
DB_PATH = Path(os.environ.get("DB_PATH", "recipe.db"))
BUNDLED_DB = Path(__file__).parent / "recipe.db"
if not DB_PATH.exists() and BUNDLED_DB.exists():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(BUNDLED_DB, DB_PATH)
    print(f"[INIT] Copied DB to {DB_PATH}")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")   # FIX ID-017

app = Flask(__name__)

# ── CORS ───────────────────────────────────────────────────────────────────────
# FIX ID-011: Bỏ supports_credentials=True khi origins="*" — theo CORS spec
# credentials + wildcard origin bị browser reject và gây CSRF risk.
# Production: thay "*" bằng domain thật (ví dụ "https://daily-mate.vercel.app").
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}, r"/admin/*": {"origins": "*"}},
    supports_credentials=False,
    allow_headers=["Authorization", "Content-Type", "Accept"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    expose_headers=["Content-Type"],
)

# FIX ID-011: Giữ lại handler OPTIONS thủ công nhưng bỏ duplicate CORS header
# để không conflict với flask-cors.
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        from flask import make_response
        res = make_response("", 204)
        res.headers["Access-Control-Allow-Origin"]  = request.headers.get("Origin", "*")
        res.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        res.headers["Access-Control-Max-Age"]       = "3600"
        return res

# FIX ID-012: Thêm security headers trên mọi response
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    # HSTS chỉ khi chạy production HTTPS — không set khi dev HTTP
    if not app.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

init_monitoring(app)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# FIX ID-006: Context manager đảm bảo db.close() luôn được gọi dù exception.
@contextmanager
def get_db_ctx():
    db = get_db()
    try:
        yield db
    finally:
        db.close()

def _group_by_endpoint(rows: list) -> dict:
    result = {}
    for r in rows:
        ep = r.get("endpoint") or "unknown"
        result[ep] = result.get(ep, 0) + 1
    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

# FIX ID-005: Helpers parse an toàn float/int với range check.
def _parse_float(val, default: float, lo: float = None, hi: float = None) -> float:
    try:
        v = float(val)
        if not math.isfinite(v):
            raise ValueError("non-finite")
        if lo is not None and v < lo:
            raise ValueError("below min")
        if hi is not None and v > hi:
            raise ValueError("above max")
        return v
    except (TypeError, ValueError):
        return default

def _parse_int(val, default: int, lo: int = None, hi: int = None) -> int:
    try:
        v = int(val)
        if lo is not None and v < lo:
            raise ValueError("below min")
        if hi is not None and v > hi:
            raise ValueError("above max")
        return v
    except (TypeError, ValueError):
        return default


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    # FIX ID-010: Không trả db_path ra ngoài — info disclosure.
    # Exception trả generic message, không leak stack trace.
    try:
        with get_db_ctx() as db:
            n_dishes = db.execute("SELECT COUNT(*) FROM dishes").fetchone()[0]
            n_ingr   = db.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
        return jsonify({"status": "ok", "dishes": n_dishes, "ingredients": n_ingr})
    except Exception:
        return jsonify({"status": "error", "detail": "Internal error"}), 500


@app.route("/api/weather")
@require_auth
def get_weather():
    """GET /api/weather?lat=16.047&lon=108.206"""
    # FIX ID-005: parse_float với range check [-90,90] / [-180,180]
    lat = _parse_float(request.args.get("lat"), 16.047, -90, 90)
    lon = _parse_float(request.args.get("lon"), 108.206, -180, 180)
    with get_db_ctx() as db:
        result = fetch_and_cache_weather(lat, lon, db)
    return jsonify(result), 200


@app.route("/admin/stats")
@require_auth
@require_admin
def admin_stats():
    # FIX ID-017: Dùng giờ Việt Nam (UTC+7) để "hôm nay" khớp với user VN.
    today_iso = (
        datetime.now(VN_TZ)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .isoformat()
    )
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/request_log",
        params={
            "select":    "endpoint,status_code,latency_ms,logged_at,uid",
            "logged_at": f"gte.{today_iso}",
            "order":     "logged_at.desc",
            "limit":     "1000",
        },
        headers=_HEADERS,
    )
    rows = resp.json()
    # FIX ID-007: Guard latency_ms None → dùng `or 0` tránh TypeError
    avg_latency = round(
        sum(r.get("latency_ms") or 0 for r in rows) / max(len(rows), 1), 1
    )
    return jsonify({
        "req_today":      len(rows),
        "active_users":   len({r["uid"] for r in rows if r.get("uid")}),
        "avg_latency_ms": avg_latency,
        "top_endpoints":  _group_by_endpoint(rows),
    })


@app.route("/api/v1/recommend", methods=["POST"])
@require_auth
@rate_limit(max_calls=10, window_seconds=60)
def recommend():
    t0   = datetime.now(timezone.utc)
    # FIX ID-008: guard None khi body rỗng / không phải JSON
    body = request.get_json(force=True) or {}

    cuisine_scope           = body.get("cuisine_scope", "vietnam")
    selected_nation         = body.get("selected_nation")
    dish_type_filter        = body.get("dish_type_filter", "all")
    # FIX ID-013: validate cost_preference range [1,3]
    cost_preference = max(1, min(3, _parse_int(body.get("cost_preference"), 2, 1, 3)))
    recent_dish_ids_ordered = [str(x) for x in body.get("recent_dish_ids", [])]

    basket = body.get("market_basket", {})
    if isinstance(basket, list):
        basket = {"selected_ingredient_ids": basket, "is_skipped": len(basket) == 0}
    selected_ids   = {int(x) for x in basket.get("selected_ingredient_ids", []) if str(x).strip().isdigit()}
    is_skipped     = basket.get("is_skipped", True)
    # FIX ID-013: validate boost_strategy enum
    boost_strategy = basket.get("boost_strategy", "strict")
    if boost_strategy not in ("strict", "none"):
        boost_strategy = "strict"
    if is_skipped:
        selected_ids, boost_strategy = set(), "none"

    lat = _parse_float(body.get("lat"), 16.047, -90, 90)
    lon = _parse_float(body.get("lon"), 108.206, -180, 180)

    # FIX ID-006: dùng get_db_ctx() để đảm bảo db.close() khi exception
    with get_db_ctx() as db:
        wv  = get_or_compute_weather(lat, lon, body.get("weather"), db=db)
        loc = resolve_location(lat, lon, db)
        pv  = compute_personal_vector(body.get("personal", {}))

        demand  = compute_demand(wv, pv, loc["climate_type"])
        profile = build_constraint_profile(pv, db)
        profile["sodium_control_need"]   = demand["sodium_control_need"]
        profile["glycemic_control_need"] = demand["glycemic_control_need"]
        profile["cost_preference"]       = cost_preference

        season            = get_current_season()
        basket_for_filter = selected_ids if (not is_skipped and selected_ids) else None
        full_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season,
                                  dish_type_filter, basket_ingredient_ids=basket_for_filter)

        if basket_for_filter and len(full_pool) == 0:
            full_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, dish_type_filter)

        dish_pool = full_pool
        if not dish_pool:
            dish_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, "all")
        if not dish_pool:
            dish_pool = filter_dishes(db, "global", None, profile, season, "all")

        taste       = resolve_taste_weight(pv, loc)
        trad_compat = loc["traditional_compatibility"]

        scores, boosts = {}, {}
        for dish in dish_pool:
            soft  = compute_soft_mult(dish, profile, season)
            avail = get_dish_availability(dish["id"], loc["food_region"], db)
            boost = compute_dish_boost(dish["id"], selected_ids, boost_strategy, db)
            scores[dish["id"]] = score_dish(
                dish, demand, soft, taste, trad_compat, avail, boost,
                profile=profile,
                recent_ids_ordered=recent_dish_ids_ordered,
            )
            boosts[dish["id"]] = boost

        _temperature = (body.get("weather", {}).get("temperature")
                        if isinstance(body.get("weather"), dict) else None)
        ranked, fallback_ids = rank_and_explain(
            scores, dish_pool, boosts, demand, profile,
            loc=loc, season=season,
            basket_ingredient_ids=selected_ids,
            db=db, temperature=_temperature,
        )

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    return jsonify({
        "status":           "ok",
        "elapsed_s":        round(elapsed, 3),
        "location":         loc,
        "weather_vector":   wv,
        "demand_snapshot":  demand,
        "cuisine_scope":    cuisine_scope,
        "dish_type_filter": dish_type_filter,
        "cost_preference":  cost_preference,
        "basket_skipped":   is_skipped,
        "dish_pool_size":   len(dish_pool),
        "ranked_dishes":    ranked,
        "page_size":        10,
        "fallback_ids":     fallback_ids,
        "generated_at":     t0.isoformat(),
    })


@app.route("/api/v1/feedback", methods=["POST"])
@require_auth
def feedback():
    """POST /api/v1/feedback  body: { session_uuid, dish_id, action, rating? }"""
    # FIX ID-008: guard None body
    body         = request.get_json(force=True) or {}
    session_uuid = body.get("session_uuid", "")
    dish_id      = body.get("dish_id", "")
    action       = body.get("action", "")
    # FIX ID-016: validate rating range [1,5], bỏ client-controlled feedback_at
    rating = body.get("rating")
    if rating is not None:
        try:
            rating = max(1, min(5, int(rating)))
        except (TypeError, ValueError):
            rating = None
    # FIX ID-016: luôn dùng server time, không tin client timestamp
    feedback_at = datetime.now(timezone.utc).isoformat()

    if not dish_id or not action:
        return jsonify({"status": "error", "detail": "dish_id và action là bắt buộc"}), 400
    if action not in ("eaten", "skipped", "rated"):
        return jsonify({"status": "error", "detail": "action phải là eaten/skipped/rated"}), 400

    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"status": "error", "detail": "Supabase chưa được cấu hình"}), 500

    payload = {
        "session_uuid": session_uuid,
        "dish_id":      str(dish_id),
        "action":       action,
        "rating":       rating,
        "feedback_at":  feedback_at,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/session_feedback",
            json=payload,
            headers={**_HEADERS, "Prefer": "return=minimal"},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            return jsonify({
                "status": "error",
                "detail": f"Supabase error {resp.status_code}",
            }), 502
        return jsonify({"status": "ok"})
    except requests.exceptions.Timeout:
        return jsonify({"status": "error", "detail": "Supabase timeout"}), 504
    except Exception:
        return jsonify({"status": "error", "detail": "Internal error"}), 500


@app.route("/api/v1/challenge")
def get_challenge():
    """GET /api/v1/challenge?lat=16.047&lon=108.206 — Món thử thách trong ngày."""
    # FIX ID-005: parse_float với range check
    lat = _parse_float(request.args.get("lat"), 16.047, -90, 90)
    lon = _parse_float(request.args.get("lon"), 108.206, -180, 180)

    today    = datetime.now().strftime("%Y%m%d")
    seed_str = f"{today}:{round(lat, 1)}:{round(lon, 1)}"
    seed     = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2 ** 32)
    _random.seed(seed)

    # FIX ID-006: context manager
    with get_db_ctx() as db:
        wv      = get_or_compute_weather(lat, lon, None, db=db)
        loc     = resolve_location(lat, lon, db)
        pv      = compute_personal_vector({})
        demand  = compute_demand(wv, pv, loc["climate_type"])
        profile = build_constraint_profile(pv, db)
        season  = get_current_season()

        dish_pool = filter_dishes(db, "vietnam", None, profile, season)
        if not dish_pool:
            dish_pool = filter_dishes(db, "global", None, profile, season)
        if not dish_pool:
            return jsonify({"error": "no dishes available"}), 404

        trad_compat = loc["traditional_compatibility"]
        scores = {
            d["id"]: score_dish(
                d, demand,
                compute_soft_mult(d, profile, season),
                TASTE_DEFAULTS, trad_compat,
                get_dish_availability(d["id"], loc["food_region"], db),
                0.0,
                profile=profile,
            )
            for d in dish_pool
        }

        weights = [max(scores.get(d["id"], 0.01), 0.01) for d in dish_pool]
        chosen  = _random.choices(dish_pool, weights=weights, k=1)[0]

    top_dim = max(
        [("hydration", demand["hydration_need"]),
         ("warming",   demand["warming_food_need"]),
         ("cooling",   demand["cooling_food_need"])],
        key=lambda x: x[1],
    )[0]
    why_map = {
        "hydration": f"Hôm nay nắng nóng, {chosen['title']} giúp bổ sung nước hiệu quả.",
        "warming":   f"Thời tiết lạnh hôm nay, {chosen['title']} ấm bụng, rất phù hợp.",
        "cooling":   f"Nhiệt độ cao, {chosen['title']} có tính mát giúp hạ nhiệt tốt.",
    }
    cook_t = chosen.get("cook_time_minutes") or 30
    diff   = "easy" if cook_t <= 20 else ("medium" if cook_t <= 45 else "hard")

    return jsonify({
        "challenge_dish": {
            "dish_id":       chosen["id"],
            "title":         chosen["title"],
            "image_url":     chosen.get("image_url", ""),
            "url":           chosen.get("url", ""),
            "nation":        chosen.get("nation", ""),
            "cook_time_min": cook_t,
            "difficulty":    diff,
            "why_today":     why_map.get(top_dim, f"{chosen['title']} phù hợp với thời tiết hôm nay."),
            "tips":          [],
            "final_score":   round(scores.get(chosen["id"], 0.5), 4),
        },
        "challenge_date": today,
        "streak":         0,
    })


@app.route("/api/v1/dishes", methods=["GET"])
def list_dishes():
    # FIX ID-005: parse_int với range check, tránh LIMIT -999
    limit  = _parse_int(request.args.get("limit"), 20, 1, 100)
    offset = _parse_int(request.args.get("offset"), 0, 0)
    nation = request.args.get("nation")
    # FIX ID-006: context manager
    with get_db_ctx() as db:
        if nation:
            rows = db.execute(
                "SELECT id,title,nation,cook_time_minutes,is_vegan,is_vegetarian "
                "FROM dishes WHERE nation=? LIMIT ? OFFSET ?",
                (nation, limit, offset)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id,title,nation,cook_time_minutes,is_vegan,is_vegetarian "
                "FROM dishes LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
    cols = ["id", "title", "nation", "cook_time_minutes", "is_vegan", "is_vegetarian"]
    return jsonify({"dishes": [dict(zip(cols, r)) for r in rows]})


@app.route("/api/v1/dishes/<dish_id>", methods=["GET"])
def dish_detail(dish_id):
    with get_db_ctx() as db:
        row = db.execute("SELECT * FROM dishes WHERE id=?", (dish_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        dish = dict(row)
        for f in ("allergen_summary", "season_suitability", "climate_suitability", "taste_profile"):
            try:
                dish[f] = json.loads(dish[f] or "null")
            except Exception:
                pass
        ingr = db.execute("""
            SELECT i.id, i.name, i.name_en, i.category, di.quantity_g, di.is_main
            FROM dish_ingredient di JOIN ingredients i ON di.ingredient_id = i.id
            WHERE di.recipe_id = ?
            ORDER BY di.is_main DESC, di.quantity_g DESC
        """, (dish_id,)).fetchall()
        dish["ingredients"] = [dict(r) for r in ingr]
    return jsonify(dish)


@app.route("/api/v1/ingredients", methods=["GET"])
def list_ingredients():
    # FIX ID-005: parse_int
    limit    = _parse_int(request.args.get("limit"), 50, 1, 200)
    category = request.args.get("category")
    with get_db_ctx() as db:
        if category:
            rows = db.execute(
                "SELECT id,name,name_en,category,is_animal_based,distribution_reach,"
                "seasonal_availability FROM ingredients WHERE category=? LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id,name,name_en,category,is_animal_based,distribution_reach,"
                "seasonal_availability FROM ingredients LIMIT ?",
                (limit,)
            ).fetchall()
    result = []
    for r in rows:
        item = {
            "id": r[0], "name": r[1], "name_en": r[2],
            "category": r[3], "is_animal_based": r[4],
            "distribution_reach": r[5],
        }
        try:
            item["seasonal_availability"] = json.loads(r[6] or "null")
        except Exception:
            item["seasonal_availability"] = None
        result.append(item)
    return jsonify({"ingredients": result})


@app.route("/api/v1/locations", methods=["GET"])
def list_locations():
    with get_db_ctx() as db:
        rows = db.execute(
            "SELECT province_name, food_region, climate_type, lat_center, lon_center "
            "FROM vn_administrative_unit ORDER BY province_name"
        ).fetchall()
    cols = ["province_name", "food_region", "climate_type", "lat", "lon"]
    return jsonify({"provinces": [dict(zip(cols, r)) for r in rows]})


@app.route("/api/v1/weather/simulate", methods=["POST"])
def weather_simulate():
    # FIX ID-008: guard None body
    body = request.get_json(force=True) or {}
    wv = compute_weather_vector(
        body.get("temperature", 30), body.get("humidity", 70),
        body.get("wind_speed",  10), body.get("pressure", 1010),
        body.get("aqi", 50),         body.get("uv_index", 6),
        body.get("season", get_current_season()),
    )
    return jsonify({"weather_vector": wv})


@app.route("/api/v1/pipeline/debug", methods=["POST"])
@require_auth   # FIX ID-009: bảo vệ endpoint lộ scoring internals
def pipeline_debug():
    # FIX ID-008: guard None body
    body = request.get_json(force=True) or {}
    # FIX ID-005: parse_float an toàn
    lat = _parse_float(body.get("lat"), 16.047, -90, 90)
    lon = _parse_float(body.get("lon"), 108.206, -180, 180)
    with get_db_ctx() as db:
        wv   = get_or_compute_weather(lat, lon, body.get("weather"), db=db)
        loc  = resolve_location(lat, lon, db)
        pv   = compute_personal_vector(body.get("personal", {}))
        demand  = compute_demand(wv, pv, loc["climate_type"])
        profile = build_constraint_profile(pv, db)
        season  = get_current_season()
        dish_pool = filter_dishes(db, body.get("cuisine_scope", "vietnam"), None, profile, season)
    return jsonify({
        "weather_vector":    wv,
        "location_vector":   loc,
        "personal_vector":   {
            "BMI":           pv["BMI"],
            "energy_need":   pv["energy_need"],
            "disease_flags": pv["disease_flags"],
            "taste_weight":  pv["taste_weight"],
        },
        "physiological_demand": demand,
        "constraint_profile":   profile,
        "dish_pool_count":      len(dish_pool),
        "sample_dishes":        [d["title"] for d in dish_pool[:5]],
    })


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'=' * 60}")
    print("  Daily Mate — Demo Recommendation Server")
    print(f"  DB: {DB_PATH}")
    print(f"  Running at: http://localhost:5001")
    print(f"{'=' * 60}\n")
    app.run(debug=True, port=5001, host="0.0.0.0")
