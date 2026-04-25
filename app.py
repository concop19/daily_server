"""
app.py — Flask application: DB setup + HTTP routes.
Import logic từ weather.py và pipeline.py.
"""

import hashlib
import json
import os
import random as _random
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, jsonify, request,g
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

# ── App & DB setup ────────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("DB_PATH",
               r"D:\dream_project\daily_mate_code\daily_mate_all\database\recipe.db"))
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
app = Flask(__name__)
CORS(app)
init_monitoring(app) 

def get_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn
def _group_by_endpoint(rows: list) -> dict:
    """Đếm số request theo từng endpoint."""
    result = {}
    for r in rows:
        ep = r.get("endpoint") or "unknown"
        result[ep] = result.get(ep, 0) + 1
    # Sắp xếp giảm dần theo lượt gọi
    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
# app.py# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    try:
        db = get_db()
        n_dishes = db.execute("SELECT COUNT(*) FROM dishes").fetchone()[0]
        n_ingr   = db.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
        db.close()
        return jsonify({"status": "ok", "dishes": n_dishes,
                        "ingredients": n_ingr, "db_path": str(DB_PATH)})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route("/api/weather")
@require_auth
def get_weather():
    """GET /api/weather?lat=16.047&lon=108.206"""
    lat = float(request.args.get("lat", 16.047))
    lon = float(request.args.get("lon", 108.206))
    db  = get_db()
    result = fetch_and_cache_weather(lat, lon, db)
    db.close()
    status = 200
    if "warning" in result and not result.get("cache_hit"):
        status = 200  # vẫn trả 200 kèm warning
    return jsonify(result), status
@app.route("/admin/stats")
@require_auth
@require_admin
def admin_stats():
    today_iso = datetime.now(timezone.utc).replace(   # ✅ thêm dòng này
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/request_log",
        params={
            "select": "endpoint,status_code,latency_ms,logged_at,uid",
            "logged_at": f"gte.{today_iso}",
            "order": "logged_at.desc",
            "limit": "1000",
        },
        headers=_HEADERS,
    )
    rows = resp.json()
    return jsonify({
        "req_today":        len(rows),
        "active_users":     len({r["uid"] for r in rows if r["uid"]}),
        "avg_latency_ms":   round(sum(r["latency_ms"] for r in rows) / max(len(rows), 1), 1),
        "top_endpoints":    _group_by_endpoint(rows),   # group by endpoint
    })

@app.route("/api/v1/recommend", methods=["POST"])
@require_auth
@rate_limit(max_calls=10, window_seconds=60)
def recommend():
    t0   = datetime.utcnow()
    body = request.get_json(force=True)
    db   = get_db()

    cuisine_scope           = body.get("cuisine_scope", "vietnam")
    selected_nation         = body.get("selected_nation")
    dish_type_filter        = body.get("dish_type_filter", "all")
    cost_preference         = int(body.get("cost_preference", 2))
    recent_dish_ids_ordered = [str(x) for x in body.get("recent_dish_ids", [])]

    basket = body.get("market_basket", {})
    if isinstance(basket, list):
        basket = {"selected_ingredient_ids": basket, "is_skipped": len(basket) == 0}
    selected_ids   = set(basket.get("selected_ingredient_ids", []))
    is_skipped     = basket.get("is_skipped", True)
    boost_strategy = basket.get("boost_strategy", "strict")
    if is_skipped:
        selected_ids, boost_strategy = set(), "none"

    lat = body.get("lat", 16.047)
    lon = body.get("lon", 108.206)
    wv  = get_or_compute_weather(lat, lon, body.get("weather"), db=db)
    loc = resolve_location(lat, lon, db)
    pv  = compute_personal_vector(body.get("personal", {}))

    demand  = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv, db)
    profile["sodium_control_need"]   = demand["sodium_control_need"]
    profile["glycemic_control_need"] = demand["glycemic_control_need"]
    profile["cost_preference"]       = cost_preference

    season    = get_current_season()
    dish_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, dish_type_filter)
    # Sau dòng: dish_pool = filter_dishes(...)
# Thêm filter basket VÀO ĐÂY — trước khi score

    if not is_skipped and selected_ids:
        def dish_matches_basket(dish_id: int) -> bool:
            rows = db.execute("""
                SELECT di.ingredient_id
                FROM dish_ingredient di
                JOIN ingredients i ON di.ingredient_id = i.id
                WHERE di.recipe_id = ?
                AND di.is_main = 1
                AND i.category NOT IN (
              'Gia vị',
              'Dầu & Mỡ',
              'Đồ uống',
              'Thực phẩm bổ dưỡng'
          )
            """, (dish_id,)).fetchall()
            
            main_non_spice_ids = {r[0] for r in rows}
            if not main_non_spice_ids:
                return False
            
            # Ít nhất 50% nguyên liệu chính phải nằm trong basket
            overlap = len(selected_ids & main_non_spice_ids)
            return overlap / len(main_non_spice_ids) >= 0.5

        dish_pool = [d for d in dish_pool if dish_matches_basket(d["id"])]
        
        # Fallback nếu filter quá chặt → nới lỏng xuống 30%
        if len(dish_pool) < 5:
            dish_pool_relaxed = []
            for d in filter_dishes(db, cuisine_scope, selected_nation, profile, season, dish_type_filter):
                rows = db.execute("""
                    SELECT di.ingredient_id
                    FROM dish_ingredient di
                    JOIN ingredients i ON di.ingredient_id = i.id
                    WHERE di.recipe_id = ?
                    AND di.is_main = 1
                    AND LOWER(i.category) NOT IN ('gia vị', 'dầu & mỡ', 'đồ uống')
                """, (d["id"],)).fetchall()
                main_ids = {r[0] for r in rows}
                if main_ids and len(selected_ids & main_ids) / len(main_ids) >= 0.3:
                    dish_pool_relaxed.append(d)
            dish_pool = dish_pool_relaxed or dish_pool  # nếu vẫn rỗng thì giữ nguyên
    if not dish_pool:
        dish_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, "all")
    if not dish_pool:
        dish_pool = filter_dishes(db, "global", None, profile, season, "all")

    taste = resolve_taste_weight(pv, loc)
    trad_compat = loc["traditional_compatibility"]

    scores, boosts = {}, {}
    for dish in dish_pool:
        soft  = compute_soft_mult(dish, profile, season)
        avail = get_dish_availability(dish["id"], loc["food_region"], db)
        boost = compute_dish_boost(dish["id"], selected_ids, boost_strategy, db)
        scores[dish["id"]] = score_dish(
            dish, demand, soft, taste, trad_compat, avail, boost,
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

    elapsed = (datetime.utcnow() - t0).total_seconds()
    db.close()

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
    body         = request.get_json(force=True)
    session_uuid = body.get("session_uuid", "")
    dish_id      = body.get("dish_id", "")
    action       = body.get("action", "")
    rating       = body.get("rating")
    feedback_at  = body.get("feedback_at") or datetime.utcnow().isoformat()

    if not dish_id or not action:
        return jsonify({"status": "error", "detail": "dish_id và action là bắt buộc"}), 400
    if action not in ("eaten", "skipped", "rated"):
        return jsonify({"status": "error", "detail": "action phải là eaten/skipped/rated"}), 400

    db = get_db()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS session_feedback (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_uuid TEXT,
                dish_id      TEXT NOT NULL,
                action       TEXT NOT NULL,
                rating       INTEGER,
                feedback_at  TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)
        db.execute("""
            INSERT INTO session_feedback
            (session_uuid, dish_id, action, rating, feedback_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_uuid, dish_id, action, rating,
              feedback_at, datetime.utcnow().isoformat()))
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        db.close()
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route("/api/v1/challenge")
@require_auth
def get_challenge():
    """GET /api/v1/challenge?lat=16.047&lon=108.206 — Món thử thách trong ngày."""
    lat  = float(request.args.get("lat", 16.047))
    lon  = float(request.args.get("lon", 108.206))

    today    = datetime.now().strftime("%Y%m%d")
    seed_str = f"{today}:{round(lat, 1)}:{round(lon, 1)}"
    seed     = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2 ** 32)
    _random.seed(seed)

    db     = get_db()
    wv     = get_or_compute_weather(lat, lon, None, db=db)
    loc    = resolve_location(lat, lon, db)
    pv     = compute_personal_vector({})
    demand = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv, db)
    season  = get_current_season()

    dish_pool = filter_dishes(db, "vietnam", None, profile, season)
    if not dish_pool:
        dish_pool = filter_dishes(db, "global", None, profile, season)
    if not dish_pool:
        db.close()
        return jsonify({"error": "no dishes available"}), 404

    trad_compat = loc["traditional_compatibility"]
    scores = {
        d["id"]: score_dish(
            d, demand,
            compute_soft_mult(d, profile, season),
            TASTE_DEFAULTS, trad_compat,
            get_dish_availability(d["id"], loc["food_region"], db),
            0.0,
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

    db.close()
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
    db     = get_db()
    nation = request.args.get("nation")
    limit  = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
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
    db.close()
    cols = ["id", "title", "nation", "cook_time_minutes", "is_vegan", "is_vegetarian"]
    return jsonify({"dishes": [dict(zip(cols, r)) for r in rows]})


@app.route("/api/v1/dishes/<dish_id>", methods=["GET"])
def dish_detail(dish_id):
    db  = get_db()
    row = db.execute("SELECT * FROM dishes WHERE id=?", (dish_id,)).fetchone()
    if not row:
        db.close()
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
    db.close()
    return jsonify(dish)


@app.route("/api/v1/ingredients", methods=["GET"])
def list_ingredients():
    db       = get_db()
    category = request.args.get("category")
    limit    = min(int(request.args.get("limit", 50)), 200)
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
    db.close()
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
    db   = get_db()
    rows = db.execute(
        "SELECT province_name, food_region, climate_type, lat_center, lon_center "
        "FROM vn_administrative_unit ORDER BY province_name"
    ).fetchall()
    db.close()
    cols = ["province_name", "food_region", "climate_type", "lat", "lon"]
    return jsonify({"provinces": [dict(zip(cols, r)) for r in rows]})


@app.route("/api/v1/weather/simulate", methods=["POST"])
def weather_simulate():
    body = request.get_json(force=True)
    wv = compute_weather_vector(
        body.get("temperature", 30), body.get("humidity", 70),
        body.get("wind_speed",  10), body.get("pressure", 1010),
        body.get("aqi", 50),         body.get("uv_index", 6),
        body.get("season", get_current_season()),
    )
    return jsonify({"weather_vector": wv})


@app.route("/api/v1/pipeline/debug", methods=["POST"])
def pipeline_debug():
    body = request.get_json(force=True)
    db   = get_db()
    lat  = body.get("lat", 16.047)
    lon  = body.get("lon", 108.206)
    wv   = get_or_compute_weather(lat, lon, body.get("weather"), db=db)
    loc  = resolve_location(lat, lon, db)
    pv   = compute_personal_vector(body.get("personal", {}))
    demand  = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv, db)
    season  = get_current_season()
    dish_pool = filter_dishes(db, body.get("cuisine_scope", "vietnam"), None, profile, season)
    db.close()
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


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'=' * 60}")
    print("  Daily Mate — Demo Recommendation Server")
    print(f"  DB: {DB_PATH}")
    print(f"  Running at: http://localhost:5001")
    print(f"{'=' * 60}\n")
    app.run(debug=True, port=5001, host="0.0.0.0")