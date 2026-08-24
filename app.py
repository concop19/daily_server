"""
app.py — Flask application: DB setup + HTTP routes.
Import logic từ weather.py và pipeline.py.
"""

import hashlib
import hmac
import json
import math
import os
import random as _random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, g
from flask_cors import CORS

load_dotenv()

import ingredient_video_store
from ingredient_video_utils import is_valid_youtube_url, slugify_vietnamese

from localization import (
    disclaimer,
    language_from_request,
    localize_dish,
    localize_ingredient,
    localize_ingredient_row,
    localize_questions,
    localize_ranked_dishes,
    localize_province,
    normalize_language,
    question_label,
)

from auth_middleware import require_auth, require_admin
from monitoring import init_monitoring
from rate_limiter import rate_limit
from fcm_service import send_push_notification
from notification_scheduler import init_scheduler
import data_store
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
# from rag.nutrition_context import NutritionContextBuilder (Lazy loaded in _get_rag_context_builder)
from rag.health_qa import (
    QUESTION_SPECS,
    build_answer,
    get_question_specs,
    source_summaries,
)
from rag.answer_generator import generate_nutrition_answer

# ── App & DataStore setup ──────────────────────────────────────────────────────
# Load tất cả JSON data vào memory khi server start
data_store.load_all()
print(f"[INIT] DataStore ready: {data_store.get_stats()}")

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
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}, r"/admin/*": {"origins": "*"}},
    supports_credentials=False,
    allow_headers=["Authorization", "Content-Type", "Accept", "Accept-Language", "X-Ingredient-Video-Key"],
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
        res.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, Accept-Language, X-Ingredient-Video-Key"
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

_rag_context_builder = None


def _get_rag_context_builder():
    """Load the Jina model lazily so normal API startup stays lightweight."""
    global _rag_context_builder
    if _rag_context_builder is None:
        from rag.nutrition_context import NutritionContextBuilder
        _rag_context_builder = NutritionContextBuilder()
    return _rag_context_builder


# ── Helpers ────────────────────────────────────────────────────────────────────

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
    try:
        stats = data_store.get_stats()
        return jsonify({"status": "ok", "dishes": stats["dishes"], "ingredients": stats["ingredients"]})
    except Exception:
        return jsonify({"status": "error", "detail": "Internal error"}), 500


@app.route("/api/v1/nutrition-rag/query", methods=["POST"])
def nutrition_rag_query():
    """Development endpoint: return grounded retrieval context, not LLM text."""
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "").strip()
    dish_id = payload.get("dish_id")

    if not query:
        return jsonify({"error": "query là bắt buộc"}), 400
    if len(query) > 500:
        return jsonify({"error": "query tối đa 500 ký tự"}), 400
    try:
        dish_id = int(dish_id)
    except (TypeError, ValueError):
        return jsonify({"error": "dish_id phải là số nguyên"}), 400

    try:
        context = _get_rag_context_builder().build(dish_id, query, n_results=5)
        raw_evidence = context["evidence"]
        evidence = []
        for index, chunk_id in enumerate(raw_evidence.get("ids", [[]])[0]):
            evidence.append({
                "rank": index + 1,
                "chunk_id": chunk_id,
                "content": raw_evidence.get("documents", [[]])[0][index],
                "metadata": raw_evidence.get("metadatas", [[]])[0][index],
                "distance": raw_evidence.get("distances", [[]])[0][index],
            })
        context["evidence"] = evidence
        return jsonify(context), 200
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        app.logger.exception("Nutrition RAG query failed")
        return jsonify({"error": "Không thể truy vấn Nutrition RAG"}), 500


@app.route("/api/v1/dishes/<dish_id>/health-question", methods=["POST"])
@require_auth
@rate_limit(max_calls=20, window_seconds=60)
def dish_health_question(dish_id):
    """Answer one fixed dish-health question using dish data plus Nutrition RAG."""
    try:
        dish_id = int(dish_id)
    except (TypeError, ValueError):
        return jsonify({"error": "dish_id phải là số nguyên"}), 400

    payload = request.get_json(silent=True) or {}
    language = normalize_language(
        payload.get("language")
        or payload.get("lang")
        or language_from_request(request)
    )
    question_id = str(payload.get("question_id") or "").strip()
    show_sources = bool(payload.get("show_sources", False))
    profile = payload.get("profile") or {}
    spec = QUESTION_SPECS.get(question_id)
    if not spec:
        return jsonify({"error": "question_id không hợp lệ"}), 400

    dish = data_store.get_dish_by_id(dish_id)
    if not dish:
        return jsonify({"error": "not found"}), 404

    try:
        context = _get_rag_context_builder().build_for_question(
            dish_id=dish_id,
            question_id=question_id,
            language=language,
            query=spec["query"],
            n_results=5,
        )
        ingredients = [
            localize_ingredient_row(row, language)
            for row in data_store.get_ingredients_for_dish(dish_id)
        ]
        raw_evidence = context.get("evidence", [])
        evidence = []
        if isinstance(raw_evidence, dict):
            ids = raw_evidence.get("ids", [[]])[0]
            docs = raw_evidence.get("documents", [[]])[0]
            metadatas = raw_evidence.get("metadatas", [[]])[0]
            distances = raw_evidence.get("distances", [[]])[0]
            evidence = [
                {
                    "chunk_id": ids[index],
                    "content": docs[index],
                    "metadata": metadatas[index],
                    "distance": distances[index],
                }
                for index in range(len(ids))
            ]
        else:
            evidence = raw_evidence
        metrics = {
            field: dish.get(field)
            for field in spec["fields"]
            if dish.get(field) is not None
        }
        try:
            answer = generate_nutrition_answer(
                question=question_label(question_id, spec["label"], language),
                context={
                    **context,
                    "dish": {**localize_dish(context["dish"], language), "ingredients": ingredients},
                    "evidence": evidence,
                },
                profile=profile,
                language=language,
            )
            answer_mode = "ai_rag"
        except Exception as exc:
            app.logger.warning("AI answer unavailable, using grounded fallback: %s", exc)
            answer = build_answer(question_id, dish, ingredients, language=language)
            answer_mode = "grounded_fallback"

        response = {
            "dish_id": dish_id,
            "title": localize_dish(dish, language).get("title"),
            "question_id": question_id,
            "question": question_label(question_id, spec["label"], language),
            "answer": answer,
            "answer_mode": answer_mode,
            "language": language,
            "metrics": metrics,
            "serving_size": context["dish"]["serving_size"],
            "disclaimer": disclaimer(language),
        }
        if show_sources:
            response["sources"] = source_summaries(evidence)
        return jsonify(response), 200
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception:
        app.logger.exception("Dish health question failed")
        return jsonify({"error": "Không thể trả lời câu hỏi dinh dưỡng"}), 500


@app.route("/api/v1/dishes/<dish_id>/health-questions", methods=["POST"])
@require_auth
def dish_health_questions(dish_id):
    """Return personalized question buttons for the active mobile profile."""
    try:
        dish_id = int(dish_id)
    except (TypeError, ValueError):
        return jsonify({"error": "dish_id phải là số nguyên"}), 400
    dish = data_store.get_dish_by_id(dish_id)
    if not dish:
        return jsonify({"error": "not found"}), 404
    language = language_from_request(request)
    payload = request.get_json(silent=True) or {}
    profile = payload.get("profile") or {}
    recommendation_context = payload.get("recommendation_context") or {}
    questions = localize_questions(get_question_specs(dish, profile, recommendation_context), language)
    return jsonify({
        "dish_id": dish_id,
        "primary_questions": questions[:4],
        "more_questions": questions[4:11],
        "questions": questions[:11],
        "total": len(questions[:11]),
        "language": language,
    }), 200


@app.route("/api/weather")
@require_auth
def get_weather():
    lat = _parse_float(request.args.get("lat"), 16.047, -90, 90)
    lon = _parse_float(request.args.get("lon"), 108.206, -180, 180)
    result = fetch_and_cache_weather(lat, lon)
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
    language = language_from_request(request)
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

    # ── Phân trang: đọc page / page_size từ body ──────────────────────────────
    page      = max(1, _parse_int(body.get("page"), 1, lo=1))
    page_size = max(1, min(20, _parse_int(body.get("page_size"), 10, lo=1, hi=20)))

    wv  = get_or_compute_weather(lat, lon, body.get("weather"))
    loc = resolve_location(lat, lon)
    pv  = compute_personal_vector(body.get("personal", {}))

    demand  = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv)
    profile["sodium_control_need"]   = demand["sodium_control_need"]
    profile["glycemic_control_need"] = demand["glycemic_control_need"]
    profile["cost_preference"]       = cost_preference

    season            = get_current_season()
    basket_for_filter = selected_ids if (not is_skipped and selected_ids) else None
    full_pool = filter_dishes(None, cuisine_scope, selected_nation, profile, season,
                              dish_type_filter, basket_ingredient_ids=basket_for_filter)

    # ── Basket small-pool logic ────────────────────────────────────────────────
    BASKET_SMALL_POOL_THRESHOLD = 10
    basket_warning = None

    if basket_for_filter and 0 < len(full_pool) < BASKET_SMALL_POOL_THRESHOLD:
        basket_warning = {
            "type":  "small_basket_pool",
            "count": len(full_pool),
            "message": (
                f"Chỉ tìm thấy {len(full_pool)} món từ nguyên liệu bạn đã chọn. "
                "Những món này đúng với giỏ nguyên liệu của bạn, nhưng có thể chưa "
                "được lọc đầy đủ theo tình trạng sức khỏe cá nhân. "
                "Để đảm bảo an toàn, bạn nên tìm kiếm thêm trên Google hoặc "
                "các nền tảng y tế để xác nhận món ăn phù hợp với sức khỏe của bạn."
            ),
            "health_params_shown": True,
        }
    elif basket_for_filter and len(full_pool) == 0:
        full_pool = filter_dishes(None, cuisine_scope, selected_nation, profile, season, dish_type_filter)

    dish_pool = full_pool
    if not dish_pool:
        dish_pool = filter_dishes(None, cuisine_scope, selected_nation, profile, season, "all")
    if not dish_pool:
        dish_pool = filter_dishes(None, "global", None, profile, season, "all")

    taste       = resolve_taste_weight(pv, loc)
    trad_compat = loc["traditional_compatibility"]

    scores, boosts = {}, {}
    for dish in dish_pool:
        soft  = compute_soft_mult(dish, profile, season)
        avail = get_dish_availability(dish["id"], loc["food_region"])
        boost = compute_dish_boost(dish["id"], selected_ids, boost_strategy)
        scores[dish["id"]] = score_dish(
            dish, demand, soft, taste, trad_compat, avail, boost,
            profile=profile,
            recent_ids_ordered=recent_dish_ids_ordered,
        )
        boosts[dish["id"]] = boost

    _temperature = (body.get("weather", {}).get("temperature")
                    if isinstance(body.get("weather"), dict) else None)
    ranked, fallback_ids, total_dishes, total_pages, has_next_page = rank_and_explain(
        scores, dish_pool, boosts, demand, profile,
        page=page,
        page_size=page_size,
        loc=loc, season=season,
        basket_ingredient_ids=selected_ids,
        temperature=_temperature,
        language=language,
    )
    ranked = localize_ranked_dishes(ranked, language)

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
        "basket_warning":   basket_warning,   # None bình thường, object khi pool < 10
        "dish_pool_size":   len(dish_pool),
        "ranked_dishes":    ranked,
        "language":         language,
        # ── Pagination fields ──────────────────────────────────────────────
        "page":             page,
        "page_size":        page_size,
        "total_dishes":     total_dishes,
        "total_pages":      total_pages,
        "has_next_page":    has_next_page,
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
    language = language_from_request(request)
    lat = _parse_float(request.args.get("lat"), 16.047, -90, 90)
    lon = _parse_float(request.args.get("lon"), 108.206, -180, 180)

    today    = datetime.now().strftime("%Y%m%d")
    seed_str = f"{today}:{round(lat, 1)}:{round(lon, 1)}"
    seed     = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2 ** 32)
    _random.seed(seed)

    # FIX ID-006: context manager
    wv      = get_or_compute_weather(lat, lon, None)
    loc     = resolve_location(lat, lon)
    pv      = compute_personal_vector({})
    demand  = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv)
    season  = get_current_season()

    dish_pool = filter_dishes(None, "vietnam", None, profile, season)
    if not dish_pool:
        dish_pool = filter_dishes(None, "global", None, profile, season)
    if not dish_pool:
        return jsonify({"error": "no dishes available"}), 404

    trad_compat = loc["traditional_compatibility"]
    scores = {
        d["id"]: score_dish(
            d, demand,
            compute_soft_mult(d, profile, season),
            TASTE_DEFAULTS, trad_compat,
            get_dish_availability(d["id"], loc["food_region"]),
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
    display_chosen = localize_dish(chosen, language)
    if language == "en":
        why_map = {
            "hydration": f"It is hot today, and {display_chosen['title']} helps replenish fluids.",
            "warming":   f"The weather is cold today, and {display_chosen['title']} is warm and comforting.",
            "cooling":   f"Temperatures are high, and {display_chosen['title']} has a cooling effect.",
        }
        default_why = f"{display_chosen['title']} fits today's weather."
    else:
        why_map = {
            "hydration": f"Hôm nay nắng nóng, {display_chosen['title']} giúp bổ sung nước hiệu quả.",
            "warming":   f"Thời tiết lạnh hôm nay, {display_chosen['title']} ấm bụng, rất phù hợp.",
            "cooling":   f"Nhiệt độ cao, {display_chosen['title']} có tính mát giúp hạ nhiệt tốt.",
        }
        default_why = f"{display_chosen['title']} phù hợp với thời tiết hôm nay."
    cook_t = chosen.get("cook_time_minutes") or 30
    diff   = "easy" if cook_t <= 20 else ("medium" if cook_t <= 45 else "hard")

    return jsonify({
        "challenge_dish": {
            "dish_id":       chosen["id"],
            "title":         display_chosen["title"],
            "image_url":     chosen.get("image_url", ""),
            "url":           chosen.get("url", ""),
            "nation":        chosen.get("nation", ""),
            "cook_time_min": cook_t,
            "difficulty":    diff,
            "why_today":     why_map.get(top_dim, default_why),
            "tips":          [],
            "final_score":   round(scores.get(chosen["id"], 0.5), 4),
        },
        "challenge_date": today,
        "streak":         0,
        "language":       language,
    })


@app.route("/api/v1/dishes", methods=["GET"])
def list_dishes():
    # FIX ID-005: parse_int với range check, tránh LIMIT -999
    limit  = _parse_int(request.args.get("limit"), 20, 1, 100)
    offset = _parse_int(request.args.get("offset"), 0, 0)
    nation = request.args.get("nation")

    all_dishes = data_store.get_all_dishes()
    if nation:
        all_dishes = [d for d in all_dishes if d.get("nation") == nation]

    language = language_from_request(request)
    page_dishes = all_dishes[offset: offset + limit]
    cols = ["id", "title", "nation", "cook_time_minutes", "is_vegan", "is_vegetarian"]
    return jsonify({"dishes": [{k: localize_dish(d, language).get(k) for k in cols} for d in page_dishes], "language": language})


@app.route("/api/v1/dishes/<dish_id>", methods=["GET"])
def dish_detail(dish_id):
    language = language_from_request(request)
    source_dish = data_store.get_dish_by_id(int(dish_id))
    if not source_dish:
        return jsonify({"error": "not found"}), 404

    dish = localize_dish(source_dish, language)
    for f in ("allergen_summary", "season_suitability", "climate_suitability", "taste_profile"):
        v = dish.get(f)
        if isinstance(v, str):
            try:
                dish[f] = json.loads(v or "null")
            except Exception:
                pass

    ingr_rows = [
        localize_ingredient_row(row, language)
        for row in data_store.get_ingredients_for_dish(int(dish_id))
    ]
    dish["ingredients"] = [
        {
            "id":         r.get("ingredient_id"),
            "name":       r.get("name", ""),
            "name_en":    r.get("ing_name_en", ""),
            "category":   r.get("category", ""),
            "quantity_g": r.get("quantity_g"),
            "is_main":    r.get("is_main"),
        }
        for r in sorted(ingr_rows,
                        key=lambda x: (-bool(x.get("is_main")), -(x.get("quantity_g") or 0)))
    ]
    dish["health_questions"] = localize_questions(get_question_specs(source_dish), language)
    dish["serving_size"] = "toàn bộ công thức món ăn"
    if language == "en":
        dish["serving_size"] = "the full recipe"
    dish["language"] = language
    return jsonify(dish)


@app.route("/api/v1/ingredients", methods=["GET"])
def list_ingredients():
    # FIX ID-005: parse_int
    limit    = _parse_int(request.args.get("limit"), 50, 1, 200)
    category = request.args.get("category")

    language = language_from_request(request)
    all_ingredients = data_store.get_all_ingredients()
    if category:
        all_ingredients = [
            i for i in all_ingredients
            if i.get("category") == category
            or localize_ingredient(i, language).get("category") == category
        ]
    all_ingredients = all_ingredients[:limit]

    result = []
    for i in all_ingredients:
        localized = localize_ingredient(i, language)
        item = {
            "id":                 i.get("id"),
            "name":               localized.get("name", ""),
            "name_en":            i.get("name_en", ""),
            "category":           localized.get("category", ""),
            "is_animal_based":    i.get("is_animal_based"),
            "distribution_reach": i.get("distribution_reach", ""),
        }
        sa = i.get("seasonal_availability")
        if isinstance(sa, str):
            try:
                sa = json.loads(sa or "null")
            except Exception:
                sa = None
        item["seasonal_availability"] = sa
        result.append(item)
    return jsonify({"ingredients": result, "language": language})


@app.route("/api/v1/locations", methods=["GET"])
def list_locations():
    language = language_from_request(request)
    rows = data_store.get_all_provinces()
    provinces = [localize_province(r, language) for r in sorted(rows, key=lambda x: x.get("province_name", ""))]
    return jsonify({"provinces": provinces, "language": language})



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
@require_auth
def pipeline_debug():
    # FIX ID-008: guard None body
    body = request.get_json(force=True) or {}
    # FIX ID-005: parse_float an toàn
    lat = _parse_float(body.get("lat"), 16.047, -90, 90)
    lon = _parse_float(body.get("lon"), 108.206, -180, 180)
    wv   = get_or_compute_weather(lat, lon, body.get("weather"))
    loc  = resolve_location(lat, lon)
    pv   = compute_personal_vector(body.get("personal", {}))
    demand  = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv)
    season  = get_current_season()
    dish_pool = filter_dishes(None, body.get("cuisine_scope", "vietnam"), None, profile, season)
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


# ── Push Notification Endpoints ───────────────────────────────────────────────

@app.route("/api/v1/device/register", methods=["POST"])
def register_device():
    """
    Mobile gọi khi khởi động để lưu FCM/Expo push token.
    Body: { device_id, fcm_token, lat?, lon?, province? }
    """
    body = request.get_json(force=True) or {}
    device_id = body.get("device_id", "").strip()
    fcm_token  = body.get("fcm_token",  "").strip()

    if not device_id or not fcm_token:
        return jsonify({"error": "device_id và fcm_token là bắt buộc"}), 400

    lat = _parse_float(body.get("lat"), None, -90, 90)
    lon = _parse_float(body.get("lon"), None, -180, 180)

    data_store.upsert_device_token(
        device_id=device_id,
        fcm_token=fcm_token,
        lat=lat,
        lon=lon,
        province=body.get("province"),
    )
    return jsonify({"status": "ok"}), 200


@app.route("/api/v1/device/location", methods=["PUT"])
def update_device_location():
    """
    Cập nhật vị trí GPS của device (gọi khi user cho phép location).
    Body: { device_id, lat, lon, province? }
    """
    body = request.get_json(force=True) or {}
    device_id = body.get("device_id", "").strip()
    if not device_id:
        return jsonify({"error": "device_id là bắt buộc"}), 400

    lat = _parse_float(body.get("lat"), None, -90, 90)
    lon = _parse_float(body.get("lon"), None, -180, 180)

    # Kiểm tra device tồn tại trước khi update
    existing = [t for t in data_store.get_all_device_tokens() if t.get("device_id") == device_id]
    if not existing:
        return jsonify({"error": "device không tồn tại"}), 404

    data_store.upsert_device_token(
        device_id=device_id,
        fcm_token=existing[0].get("fcm_token", ""),
        lat=lat,
        lon=lon,
        province=body.get("province"),
    )
    return jsonify({"status": "ok"}), 200


@app.route("/api/v1/device/test-push", methods=["POST"])
def test_push():
    """
    Gửi test notification ngay lập tức — chỉ dùng khi dev/test.
    Body: { fcm_token } hoặc { device_id }
    """
    body = request.get_json(force=True) or {}
    fcm_token = body.get("fcm_token", "").strip()

    if not fcm_token and body.get("device_id"):
        tokens = data_store.get_all_device_tokens()
        match  = next((t for t in tokens if t.get("device_id") == body["device_id"]), None)
        if match:
            fcm_token = match.get("fcm_token", "")

    if not fcm_token:
        return jsonify({"error": "fcm_token hoặc device_id hợp lệ là bắt buộc"}), 400

    ok = send_push_notification(
        fcm_token,
        title="🍽️ Test từ Daily Mate",
        body="Push notification đang hoạt động! 🎉",
        data={"screen": "MealReminder", "mealId": "lunch"},
    )
    if ok is True:
        return jsonify({"sent": True}), 200
    elif ok == "invalid_token":
        return jsonify({"sent": False, "detail": "Token không hợp lệ hoặc đã hết hạn"}), 400
    else:
        return jsonify({"sent": False, "detail": "Gửi thất bại, kiểm tra log server"}), 500


# ── Ingredient Videos (Admin CRUD via Secret Key & Public for Mobile) ─────────

@app.route("/api/v1/ingredient-videos", methods=["POST"])
def add_or_update_ingredient_video():
    """
    POST /api/v1/ingredient-videos
    Header:
        X-Ingredient-Video-Key: <INGREDIENT_VIDEO_ADMIN_KEY>
        Content-Type: application/json
    Body:
        {
            "ingredient_name": "Cà chua",
            "video_url": "https://www.youtube.com/watch?v=abc123xyz",
            "category": "Rau củ"  # Optional
        }
    """
    admin_key = os.environ.get("INGREDIENT_VIDEO_ADMIN_KEY", "").strip()
    client_key = request.headers.get("X-Ingredient-Video-Key", "").strip()

    if not admin_key or not client_key or not hmac.compare_digest(client_key, admin_key):
        return jsonify({"success": False, "error": "invalid ingredient video key"}), 401

    body = request.get_json(silent=True) or {}
    ingredient_name = str(body.get("ingredient_name") or "").strip()
    video_url = str(body.get("video_url") or "").strip()
    category = body.get("category")
    if isinstance(category, str):
        category = category.strip() or None
    else:
        category = None

    if not ingredient_name:
        return jsonify({"success": False, "error": "ingredient_name is required"}), 400

    if not video_url:
        return jsonify({"success": False, "error": "video_url is required"}), 400

    if not is_valid_youtube_url(video_url):
        return jsonify({"success": False, "error": "video_url must be a valid YouTube URL"}), 400

    slug = slugify_vietnamese(ingredient_name)
    if not slug:
        return jsonify({"success": False, "error": "unable to generate valid slug from ingredient_name"}), 400

    # Auto-infer category from existing ingredients if omitted
    if not category:
        for ing in data_store.get_all_ingredients():
            if slugify_vietnamese(ing.get("name", "")) == slug:
                category = ing.get("category") or ing.get("ingredient_type")
                break

    saved_item = ingredient_video_store.upsert_ingredient_video(
        ingredient_name=ingredient_name,
        video_url=video_url,
        category=category,
        slug=slug,
    )

    return jsonify({
        "success": True,
        "item": {
            "ingredient_name": saved_item.get("ingredient_name", ingredient_name),
            "slug":            saved_item.get("slug", slug),
            "video_url":       saved_item.get("video_url", video_url),
            "category":        saved_item.get("category"),
        },
    }), 200


@app.route("/api/v1/ingredient-videos", methods=["GET"])
def get_ingredient_videos():
    """
    GET /api/v1/ingredient-videos
    Public endpoint for mobile app.
    Optional query params: category, search/q
    """
    category = request.args.get("category")
    search = request.args.get("search") or request.args.get("q")

    items = ingredient_video_store.get_ingredient_videos(category=category, search=search)
    return jsonify({
        "items": items,
        "total": len(items),
    }), 200


# ── Recommend function dùng bởi scheduler ────────────────────────────────────

def _recommend_for_device(device: dict, meal_type: str):
    """
    Chạy recommendation pipeline cho 1 device, trả về top dish dict hoặc None.
    device: dict với keys device_id, fcm_token, lat, lon
    meal_type: 'lunch' | 'dinner'
    """
    try:
        lat = float(device.get("lat") or 16.047)
        lon = float(device.get("lon") or 108.206)

        wv  = get_or_compute_weather(lat, lon, None)
        loc = resolve_location(lat, lon)
        pv  = compute_personal_vector({})

        demand  = compute_demand(wv, pv, loc["climate_type"])
        profile = build_constraint_profile(pv)
        profile["sodium_control_need"]   = demand["sodium_control_need"]
        profile["glycemic_control_need"] = demand["glycemic_control_need"]
        profile["cost_preference"]       = 2

        season    = get_current_season()
        dish_pool = filter_dishes(None, "vietnam", None, profile, season, "all")
        if not dish_pool:
            dish_pool = filter_dishes(None, "global", None, profile, season, "all")
        if not dish_pool:
            return None

        taste       = resolve_taste_weight(pv, loc)
        trad_compat = loc["traditional_compatibility"]

        scores = {
            d["id"]: score_dish(
                d, demand,
                compute_soft_mult(d, profile, season),
                taste, trad_compat,
                get_dish_availability(d["id"], loc["food_region"]),
                0.0,
                profile=profile,
            )
            for d in dish_pool
        }

        ranked, _, _, _, _ = rank_and_explain(
            scores, dish_pool, {d["id"]: 0.0 for d in dish_pool},
            demand, profile,
            loc=loc, season=season,
            basket_ingredient_ids=set(),
            language="vi",
        )
        return ranked[0] if ranked else None

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[Push] _recommend_for_device failed: {e}")
        return None

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    stats = data_store.get_stats()
    print(f"\n{'=' * 60}")
    print("  Daily Mate — Demo Recommendation Server")
    print(f"  DataStore: {stats['dishes']} dishes, {stats['ingredients']} ingredients")
    print(f"  Running at: http://localhost:5001")
    print(f"{'=' * 60}\n")

    # Khởi động push notification scheduler nếu được bật
    if os.environ.get("ENABLE_PUSH_SCHEDULER", "false").lower() == "true":
        init_scheduler(_recommend_for_device)
        print("[Push] Scheduler started — 8 notification slots/day active")

    app.run(debug=True, port=5001, host="0.0.0.0")
