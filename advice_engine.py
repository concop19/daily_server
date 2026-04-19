"""
advice_engine.py
================
F06 — Recommendation Explanation Engine

Import vào server.py:
    from advice_engine import build_explanation

Thay thế hàm _explain() cũ bằng:
    explanation = build_explanation(dish, demand, profile, boost,
                                    loc, season, basket_ids, db)
"""

from __future__ import annotations
import json
import sqlite3
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_json(text: str | None, default=None):
    try:
        return json.loads(text or "null") or default
    except Exception:
        return default


def _fill(template: str, **kwargs) -> str:
    """Điền biến {key} vào template, bỏ qua key không tồn tại."""
    try:
        return template.format(**kwargs)
    except KeyError:
        # Thay thế từng key một, bỏ qua key thiếu
        result = template
        for k, v in kwargs.items():
            result = result.replace(f"{{{k}}}", str(v))
        return result


def _query_templates(db: sqlite3.Connection, context_type: str, trigger_dim: str,
                     intensity: float) -> list[dict]:
    """
    Lấy các template phù hợp với context_type + trigger_dim + intensity,
    sắp xếp theo priority tăng dần (1 = cao nhất).
    """
    rows = db.execute(
        """
        SELECT template_text, priority
        FROM   advice_templates
        WHERE  context_type = ?
          AND  trigger_dim  = ?
          AND  intensity_min <= ?
          AND  intensity_max >= ?
        ORDER BY priority ASC
        LIMIT 3
        """,
        (context_type, trigger_dim, intensity, intensity),
    ).fetchall()
    return [{"text": r[0], "priority": r[1]} for r in rows]


def _get_best_template(db: sqlite3.Connection, context_type: str, trigger_dim: str,
                       intensity: float, fallback: str, **fill_vars) -> str:
    """
    Lấy template tốt nhất (priority thấp nhất) và điền biến.
    Nếu không có template trong DB → dùng fallback.
    """
    rows = _query_templates(db, context_type, trigger_dim, intensity)
    template = rows[0]["text"] if rows else fallback
    return _fill(template, **fill_vars)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-builders
# ─────────────────────────────────────────────────────────────────────────────

def _dominant_demand(demand: dict) -> tuple[str, float]:
    """Trả (tên dimension, giá trị) của demand cao nhất."""
    keys = ["hydration_need", "cooling_food_need", "warming_food_need",
            "infection_risk", "cold_stress_index", "electrolyte_need"]
    best_k, best_v = "hydration_need", 0.0
    for k in keys:
        v = demand.get(k, 0.0)
        if v > best_v:
            best_v, best_k = v, k
    return best_k, best_v


def _build_headline(dish: dict, demand: dict, db: sqlite3.Connection) -> str:
    dim, val = _dominant_demand(demand)
    dish_name = dish.get("title", "Món ăn")

    headline = _get_best_template(
        db, "headline", dim, val,
        fallback=f"{dish_name} — phù hợp với điều kiện hôm nay",
        dish_name=dish_name,
    )

    # Nếu val quá thấp (< 0.3), fallback về headline "balanced"
    if val < 0.3:
        headline = _get_best_template(
            db, "headline", "balanced", 0.5,
            fallback=f"{dish_name} — cân bằng dinh dưỡng hôm nay",
            dish_name=dish_name,
        )
    return headline


def _build_weather_reason(demand: dict, temperature: float | None,
                           db: sqlite3.Connection) -> str:
    dim, val = _dominant_demand(demand)
    temp_str = f"{temperature:.0f}" if temperature else "?"

    fallbacks = {
        "hydration_need":    f"Hôm nay {temp_str}°C, cơ thể cần bù nước nhiều hơn bình thường.",
        "cooling_food_need": f"Nhiệt độ {temp_str}°C cao — nên ưu tiên món có tính mát.",
        "warming_food_need": f"Trời lạnh {temp_str}°C — món ăn ấm sẽ giúp bạn dễ chịu hơn.",
        "infection_risk":    "Thời tiết giao mùa dễ ốm — tăng cường miễn dịch qua bữa ăn.",
        "cold_stress_index": f"Gió lạnh và nhiệt độ {temp_str}°C — cơ thể cần bổ sung đủ năng lượng.",
    }

    return _get_best_template(
        db, "weather", dim, val,
        fallback=fallbacks.get(dim, f"Thời tiết hôm nay {temp_str}°C — chọn món phù hợp cơ thể."),
        temperature=temp_str,
    )


def _build_dish_match(dish: dict, demand: dict) -> str:
    """Câu mô tả tại sao dish khớp với demand."""
    dim, val = _dominant_demand(demand)
    name = dish.get("title", "Món này")

    # Lấy điểm dish tương ứng dimension
    dim_to_score = {
        "hydration_need":    ("adj_hydration_score",   "dish_hydration_score"),
        "cooling_food_need": ("adj_cooling_score",     "dish_cooling_score"),
        "warming_food_need": ("adj_warming_score",     "dish_warming_score"),
        "infection_risk":    ("adj_thermogenic_score", "dish_thermogenic_score"),
        "cold_stress_index": ("adj_warming_score",     "dish_warming_score"),
    }
    adj, raw = dim_to_score.get(dim, ("adj_hydration_score", "dish_hydration_score"))
    dish_score = dish.get(adj) or dish.get(raw) or 0.0

    templates = {
        "hydration_need":    "{name} có hàm lượng nước cao (điểm bù nước: {score:.0%}), giúp cơ thể duy trì độ ẩm tốt.",
        "cooling_food_need": "{name} có tính mát, giúp hạ nhiệt tự nhiên từ bên trong (điểm mát: {score:.0%}).",
        "warming_food_need": "{name} có tính ấm, phù hợp giữ nhiệt cơ thể trong thời tiết lạnh (điểm ấm: {score:.0%}).",
        "infection_risk":    "{name} giàu vi chất và chất chống oxy hoá, hỗ trợ tăng cường miễn dịch.",
        "cold_stress_index": "{name} cung cấp năng lượng ổn định, giúp cơ thể chống chịu gió lạnh.",
    }
    tpl = templates.get(dim, "{name} phù hợp với nhu cầu dinh dưỡng hôm nay.")
    return _fill(tpl, name=name, score=float(dish_score))


def _build_nutrition_note(dish: dict, profile: dict) -> str | None:
    """Trả chuỗi lưu ý dinh dưỡng nếu có disease_flags, None nếu không cần."""
    parts = []
    df = profile.get("disease_flags", {})

    sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
    gl     = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0
    cal    = dish.get("adj_energy_total") or dish.get("dish_energy_total") or 0

    if df.get("hypertension"):
        if sodium and sodium < 500:
            parts.append(f"Ít sodium ({sodium:.0f}mg/serving) — phù hợp với huyết áp cao.")
        elif sodium:
            parts.append(f"Sodium ở mức trung bình ({sodium:.0f}mg) — ăn kèm nhiều rau để cân bằng.")

    if df.get("diabetes"):
        if gl and gl < 10:
            parts.append(f"Chỉ số đường huyết thấp (GL {gl:.1f}) — lý tưởng kiểm soát đường trong máu.")
        elif gl:
            parts.append(f"Glycemic load {gl:.1f} — ăn chậm và kết hợp rau xanh.")

    if df.get("gout"):
        parts.append("Hàm lượng purine thấp, phù hợp với người bị gout.")

    if df.get("ibs"):
        parts.append("Nguyên liệu dễ tiêu hoá, thân thiện với đường ruột nhạy cảm.")

    # BMI và năng lượng
    bmi = profile.get("BMI", 22)
    if bmi and bmi > 25 and cal:
        parts.append(f"Ít calo ({cal:.0f}kcal/serving) — hỗ trợ kiểm soát cân nặng.")
    elif bmi and bmi < 18.5 and cal:
        parts.append(f"Giàu năng lượng ({cal:.0f}kcal/serving) — bổ sung đủ dinh dưỡng.")

    # Diet type
    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        parts.append("100% thực vật — không chứa nguyên liệu động vật.")
    elif diet == "vegetarian" and dish.get("is_vegetarian"):
        parts.append("Món chay — không có thịt, phù hợp chế độ ăn của bạn.")

    return " | ".join(parts) if parts else None


def _build_ingredient_note(boost: float, basket_ingredient_ids: set,
                            dish_id: Any, db: sqlite3.Connection) -> str | None:
    """Nêu tên nguyên liệu cụ thể từ giỏ hàng nếu boost > 0."""
    if boost <= 0.05 or not basket_ingredient_ids:
        return None

    # Lấy tên nguyên liệu chính của dish có trong basket
    rows = db.execute(
        """
        SELECT i.name
        FROM   dish_ingredient di
        JOIN   ingredients i ON di.ingredient_id = i.id
        WHERE  di.recipe_id = ?
          AND  di.is_main   = 1
          AND  di.ingredient_id IN ({})
        ORDER BY di.quantity_g DESC
        LIMIT 4
        """.format(",".join("?" * len(basket_ingredient_ids))),
        [dish_id, *list(basket_ingredient_ids)],
    ).fetchall()

    if not rows:
        return None

    names = [r[0] for r in rows]
    ingredient_names = ", ".join(names)

    if boost >= 0.75:
        dim_key = "boost_high"
        fallback = f"Hầu hết nguyên liệu chính ({ingredient_names}) đều có trong giỏ hàng — tiện nấu ngay!"
    elif boost >= 0.40:
        dim_key = "boost_medium"
        fallback = f"{ingredient_names} từ giỏ hàng hôm nay được dùng trong món này."
    else:
        dim_key = "boost_low"
        fallback = f"Một số nguyên liệu bạn đã mua ({ingredient_names}) có thể dùng cho món này."

    rows_tpl = db.execute(
        "SELECT template_text FROM advice_templates "
        "WHERE context_type='ingredient' AND trigger_dim=? LIMIT 1",
        (dim_key,)
    ).fetchone()
    tpl = rows_tpl[0] if rows_tpl else fallback
    return _fill(tpl, ingredient_names=ingredient_names)


def _build_seasonal_note(dish: dict, season: str,
                          db: sqlite3.Connection) -> str | None:
    """Thêm ghi chú mùa vụ nếu season_suitability cao."""
    sm = _safe_json(dish.get("season_suitability"), {})
    score = sm.get(season, 0.0) if isinstance(sm, dict) else 0.0
    if score < 0.55:
        return None

    dish_name = dish.get("title", "Món này")

    # Cố gắng lấy tên nguyên liệu chính
    main_ingredient = dish_name  # default

    return _get_best_template(
        db, "season", season, score,
        fallback=f"{dish_name} rất hợp với thời tiết {season} hiện tại.",
        dish_name=dish_name,
        main_ingredient=main_ingredient,
    )


def _generate_tags(dish: dict, demand: dict, profile: dict, boost: float,
                   season: str, db: sqlite3.Connection) -> list[str]:
    """Tạo danh sách hashtag phù hợp."""
    tags: list[str] = []

    def _lookup_tag(trigger_dim: str, intensity: float) -> str | None:
        row = db.execute(
            "SELECT template_text FROM advice_templates "
            "WHERE context_type='tag' AND trigger_dim=? "
            "  AND intensity_min<=? AND intensity_max>=? "
            "ORDER BY priority ASC LIMIT 1",
            (trigger_dim, intensity, intensity)
        ).fetchone()
        return row[0] if row else None

    # Hydration
    h = demand.get("hydration_need", 0)
    if h >= 0.60:
        t = _lookup_tag("hydration_high", h)
        if t: tags.append(t)
    elif h >= 0.30:
        t = _lookup_tag("hydration_mid", h)
        if t: tags.append(t)

    # Cooling / Warming
    c = demand.get("cooling_food_need", 0)
    w = demand.get("warming_food_need", 0)
    if c >= 0.60:
        t = _lookup_tag("cooling_high", c)
        if t: tags.append(t)
    elif c >= 0.30:
        t = _lookup_tag("cooling_mid", c)
        if t: tags.append(t)

    if w >= 0.60:
        t = _lookup_tag("warming_high", w)
        if t: tags.append(t)
    elif w >= 0.30:
        t = _lookup_tag("warming_mid", w)
        if t: tags.append(t)

    # Disease flags
    df = profile.get("disease_flags", {})
    sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
    gl     = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0

    if df.get("hypertension") and sodium and sodium < 600:
        t = _lookup_tag("low_sodium", 0.5)
        if t: tags.append(t)
    if df.get("diabetes") and gl and gl < 12:
        t = _lookup_tag("low_gl", 0.5)
        if t: tags.append(t)

    # Immunity
    inf = demand.get("infection_risk", 0)
    if inf >= 0.50:
        t = _lookup_tag("immunity", inf)
        if t: tags.append(t)

    # Diet type
    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        t = _lookup_tag("vegan_tag", 0.5)
        if t: tags.append(t)
    elif diet == "vegetarian":
        t = _lookup_tag("vegetarian_tag", 0.5)
        if t: tags.append(t)

    # Quick cook
    ct = dish.get("cook_time_minutes") or 999
    if ct <= 20:
        t = _lookup_tag("quick_cook", 0.5)
        if t: tags.append(t)

    # Ingredient boost
    if boost >= 0.60:
        t = _lookup_tag("high_boost", boost)
        if t: tags.append(t)

    # Season match
    sm = _safe_json(dish.get("season_suitability"), {})
    if isinstance(sm, dict) and sm.get(season, 0) >= 0.65:
        t = _lookup_tag("season_match", 0.7)
        if t: tags.append(t)

    # Giới hạn 5 tags, không trùng
    seen, result = set(), []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
        if len(result) >= 5:
            break
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_explanation(
    dish: dict,
    demand: dict,
    profile: dict,
    boost: float,
    loc: dict,
    season: str,
    basket_ingredient_ids: set,
    db: sqlite3.Connection,
    temperature: float | None = None,
) -> dict:
    """
    Xây dựng explanation object đầy đủ cho một món ăn được recommend.

    Parameters
    ----------
    dish                  : dict từ filter_dishes (có tất cả adj_* scores)
    demand                : dict từ compute_demand
    profile               : dict từ build_constraint_profile (có disease_flags, BMI, diet_type)
    boost                 : float 0-1, kết quả compute_dish_boost
    loc                   : dict từ resolve_location
    season                : str 'summer'|'winter'|'spring'|'autumn'
    basket_ingredient_ids : set of ingredient IDs người dùng đã chọn
    db                    : sqlite3.Connection đang mở
    temperature           : float nhiệt độ thực tế (°C), nếu có

    Returns
    -------
    dict với keys: headline, weather_reason, dish_match,
                   nutrition_note, ingredient_note, seasonal_note, tags
    """

    # Đảm bảo bảng tồn tại (không crash nếu chưa seed)
    _ensure_table(db)

    headline       = _build_headline(dish, demand, db)
    weather_reason = _build_weather_reason(demand, temperature, db)
    dish_match     = _build_dish_match(dish, demand)
    nutrition_note = _build_nutrition_note(dish, profile)
    ingredient_note = _build_ingredient_note(boost, basket_ingredient_ids, dish["id"], db)
    seasonal_note  = _build_seasonal_note(dish, season, db)
    tags           = _generate_tags(dish, demand, profile, boost, season, db)

    return {
        "headline":        headline,
        "weather_reason":  weather_reason,
        "dish_match":      dish_match,
        "nutrition_note":  nutrition_note,    # None nếu không có gì đặc biệt
        "ingredient_note": ingredient_note,   # None nếu basket trống
        "seasonal_note":   seasonal_note,     # None nếu mùa không phù hợp đặc biệt
        "tags":            tags,
    }


def _ensure_table(db: sqlite3.Connection):
    """Tạo bảng advice_templates nếu chưa có (phòng khi chưa chạy seed)."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS advice_templates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            context_type    TEXT NOT NULL,
            trigger_dim     TEXT NOT NULL,
            intensity_min   REAL NOT NULL DEFAULT 0.0,
            intensity_max   REAL NOT NULL DEFAULT 1.0,
            template_text   TEXT NOT NULL,
            priority        INTEGER NOT NULL DEFAULT 5,
            lang            TEXT NOT NULL DEFAULT 'vi',
            notes           TEXT
        )
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible replacement cho _explain() cũ trong server.py
# ─────────────────────────────────────────────────────────────────────────────

def legacy_explain_list(dish: dict, demand: dict, profile: dict,
                         boost: float, loc: dict, season: str,
                         basket_ingredient_ids: set,
                         db: sqlite3.Connection,
                         temperature: float | None = None) -> list[str]:
    """
    Trả về list[str] giống _explain() cũ — dùng để không phá vỡ
    các endpoint chưa được nâng cấp.
    """
    exp = build_explanation(dish, demand, profile, boost, loc, season,
                            basket_ingredient_ids, db, temperature)
    parts = []
    if exp["weather_reason"]:
        parts.append(exp["weather_reason"])
    if exp["dish_match"]:
        parts.append(exp["dish_match"])
    if exp["nutrition_note"]:
        parts.append(exp["nutrition_note"])
    if exp["ingredient_note"]:
        parts.append(exp["ingredient_note"])
    if exp["seasonal_note"]:
        parts.append(exp["seasonal_note"])
    return [p for p in parts if p][:4]
