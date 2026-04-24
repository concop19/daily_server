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
    result = template
    for k, v in kwargs.items():
        result = result.replace(f"{{{k}}}", str(v))
    return result


def _query_templates(db: sqlite3.Connection, context_type: str, trigger_dim: str,
                     intensity: float) -> list[dict]:
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
    rows = _query_templates(db, context_type, trigger_dim, intensity)
    template = rows[0]["text"] if rows else fallback
    return _fill(template, **fill_vars)


# ─────────────────────────────────────────────────────────────────────────────
# Dominant demand — trả về top-2 để handle comorbidity
# ─────────────────────────────────────────────────────────────────────────────

DEMAND_KEYS = [
    "hydration_need", "cooling_food_need", "warming_food_need",
    "infection_risk", "cold_stress_index", "electrolyte_need",
    "sodium_control_need",
    "glycemic_control_need",
    "gout_control_need",
    "ibs_control_need",
]

def _dominant_demands(demand: dict, top_k: int = 2) -> list[tuple[str, float]]:
    """Trả về top_k dimension có giá trị cao nhất."""
    scored = [(k, demand.get(k, 0.0)) for k in DEMAND_KEYS]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(k, v) for k, v in scored[:top_k] if v > 0.0]


def _primary_demand(demand: dict) -> tuple[str, float]:
    """Dimension quan trọng nhất — dùng cho weather_reason và headline."""
    tops = _dominant_demands(demand, top_k=1)
    return tops[0] if tops else ("hydration_need", 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Sub-builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_headline(dish: dict, demand: dict, db: sqlite3.Connection) -> str:
    dish_name = dish.get("title", "Món ăn")
    tops = _dominant_demands(demand, top_k=2)

    # Nếu dimension đầu là disease control → dùng headline bệnh
    DISEASE_HEADLINES = {
        "sodium_control_need":   f"{dish_name} — ít muối, thân thiện với huyết áp cao",
        "glycemic_control_need": f"{dish_name} — chỉ số đường huyết thấp, an toàn cho người tiểu đường",
        "gout_control_need":     f"{dish_name} — ít purine, phù hợp người bị gout",
        "ibs_control_need":      f"{dish_name} — dễ tiêu hoá, thân thiện đường ruột nhạy cảm",
    }
    if tops and tops[0][0] in DISEASE_HEADLINES and tops[0][1] >= 1.0:
        return DISEASE_HEADLINES[tops[0][0]]

    dim, val = tops[0] if tops else ("hydration_need", 0.0)
    headline = _get_best_template(
        db, "headline", dim, val,
        fallback=f"{dish_name} — phù hợp với điều kiện hôm nay",
        dish_name=dish_name,
    )
    if val < 0.3:
        headline = _get_best_template(
            db, "headline", "balanced", 0.5,
            fallback=f"{dish_name} — cân bằng dinh dưỡng hôm nay",
            dish_name=dish_name,
        )
    return headline


def _build_weather_reason(demand: dict, temperature: float | None,
                           db: sqlite3.Connection) -> str:
    # Weather reason dùng dimension thời tiết, không dùng disease dimension
    WEATHER_DIMS = {
        "hydration_need", "cooling_food_need", "warming_food_need",
        "infection_risk", "cold_stress_index", "electrolyte_need",
    }
    weather_tops = [
        (k, v) for k, v in _dominant_demands(demand, top_k=4)
        if k in WEATHER_DIMS
    ]
    dim, val = weather_tops[0] if weather_tops else ("hydration_need", 0.0)
    temp_str = f"{temperature:.0f}" if temperature else "?"

    fallbacks = {
        "hydration_need":    f"Hôm nay {temp_str}°C, cơ thể cần bù nước nhiều hơn bình thường.",
        "cooling_food_need": f"Nhiệt độ {temp_str}°C cao — nên ưu tiên món có tính mát.",
        "warming_food_need": f"Trời lạnh {temp_str}°C — món ăn ấm sẽ giúp bạn dễ chịu hơn.",
        "infection_risk":    "Thời tiết giao mùa dễ ốm — tăng cường miễn dịch qua bữa ăn.",
        "cold_stress_index": f"Gió lạnh và nhiệt độ {temp_str}°C — cơ thể cần bổ sung đủ năng lượng.",
        "electrolyte_need":  f"Thời tiết {temp_str}°C, hoạt động nhiều — cần bổ sung điện giải.",
    }
    return _get_best_template(
        db, "weather", dim, val,
        fallback=fallbacks.get(dim, f"Thời tiết hôm nay {temp_str}°C — chọn món phù hợp cơ thể."),
        temperature=temp_str,
    )

def _build_dish_match(dish: dict, demand: dict) -> str:
    """Câu mô tả tại sao dish khớp với demand — handle cả disease dimensions."""
    tops = _dominant_demands(demand, top_k=2)
    name = dish.get("title", "Món này")

    # (template, adj_key, raw_key, invert)
    # invert=True  → score là risk score, cần đổi thành safety: 1 - score
    # invert=False → dùng score trực tiếp
    DIM_TEMPLATES = {
        "hydration_need": (
            "{name} có hàm lượng nước cao (điểm bù nước: {score:.0%}), "
            "giúp cơ thể duy trì độ ẩm tốt.",
            "adj_hydration_score", "dish_hydration_score", False
        ),
        "cooling_food_need": (
            "{name} có tính mát, giúp hạ nhiệt tự nhiên từ bên trong (điểm mát: {score:.0%}).",
            "adj_cooling_score", "dish_cooling_score", False
        ),
        "warming_food_need": (
            "{name} có tính ấm, phù hợp giữ nhiệt cơ thể trong thời tiết lạnh (điểm ấm: {score:.0%}).",
            "adj_warming_score", "dish_warming_score", False
        ),
        "infection_risk": (
            "{name} giàu vi chất và chất chống oxy hoá, hỗ trợ tăng cường miễn dịch.",
            "adj_thermogenic_score", "dish_thermogenic_score", False
        ),
        "cold_stress_index": (
            "{name} cung cấp năng lượng ổn định, giúp cơ thể chống chịu gió lạnh.",
            "adj_warming_score", "dish_warming_score", False
        ),
        "sodium_control_need": (
            "{name} có lượng muối thấp ({score:.0f}mg sodium/serving) — "
            "phù hợp với người cần kiểm soát huyết áp.",
            "adj_sodium_total", "dish_sodium_total", False
        ),
        "glycemic_control_need": (
            "{name} có chỉ số đường huyết thấp (GL {score:.1f}) — "
            "giúp kiểm soát lượng đường trong máu ổn định.",
            "adj_glycemic_load", "dish_glycemic_load", False
        ),
        "gout_control_need": (
            "{name} có hàm lượng purine thấp (điểm an toàn: {score:.0%}) — "
            "phù hợp với người bị gout.",
            "gout_risk_score", None, False     # risk → invert thành safety
        ),
        "ibs_control_need": (
            "{name} sử dụng nguyên liệu dễ tiêu hoá, "
            "thân thiện với đường ruột nhạy cảm.",
            None, None, False
        ),
    }

    parts = []
    for dim, val in tops:
        if dim not in DIM_TEMPLATES:
            continue

        tpl, adj, raw, invert = DIM_TEMPLATES[dim]

        # Lấy score — dùng .get(key, None) thay vì `or` để không nuốt float 0.0
        if adj:
            dish_score = dish.get(adj, None)
            if dish_score is None and raw:
                dish_score = dish.get(raw, None)
            dish_score = float(dish_score) if dish_score is not None else 0.0
        else:
            dish_score = 0.0

        # Invert risk score → safety score (chỉ khi có giá trị thực)
        if invert and dish_score > 0:
            dish_score = 1.0 - dish_score

        parts.append(tpl.format(name=name, score=dish_score))

    return " ".join(parts) if parts else f"{name} phù hợp với nhu cầu dinh dưỡng hôm nay."
def _build_nutrition_note(dish: dict, profile: dict) -> str | None:
    """Lưu ý dinh dưỡng theo disease_flags — bao gồm cả warning khi gần threshold."""
    parts = []
    df    = profile.get("disease_flags", {})

    sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
    gl     = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0
    cal    = dish.get("adj_energy_total")  or dish.get("dish_energy_total")  or 0
    gout_s = dish.get("gout_risk_score")

    # ── Hypertension ──────────────────────────────────────────────────────────
    if df.get("hypertension") and sodium:
        if sodium < 400:
            parts.append(f"Rất ít sodium ({sodium:.0f}mg/serving) — lý tưởng cho huyết áp cao.")
        elif sodium < 500:
            parts.append(f"Ít sodium ({sodium:.0f}mg/serving) — phù hợp với huyết áp cao.")
        else:
            # 500-600mg: gần threshold → warning
            parts.append(
                f"⚠️ Sodium ở mức {sodium:.0f}mg/serving (giới hạn 600mg) — "
                f"không nên thêm nước mắm hoặc muối khi ăn."
            )

    # ── Diabetes ──────────────────────────────────────────────────────────────
    if df.get("diabetes") and gl:
        if gl < 7:
            parts.append(f"Chỉ số đường huyết rất thấp (GL {gl:.1f}) — lý tưởng kiểm soát đường máu.")
        elif gl < 10:
            parts.append(f"Chỉ số đường huyết thấp (GL {gl:.1f}) — an toàn cho người tiểu đường.")
        else:
            # 10-25: gần threshold → ăn kèm rau
            parts.append(
                f"⚠️ Glycemic load {gl:.1f} — ăn chậm, kết hợp rau xanh nhiều xơ "
                f"để giảm tốc độ hấp thụ đường."
            )

    # ── Gout ──────────────────────────────────────────────────────────────────
    if df.get("gout"):
        if gout_s is not None:
            if gout_s >= 0.8:
                parts.append("Hàm lượng purine rất thấp — hoàn toàn phù hợp với người bị gout.")
            elif gout_s >= 0.5:
                parts.append(
                    "Purine ở mức trung bình — ăn lượng vừa phải, "
                    "uống nhiều nước để hỗ trợ thải acid uric."
                )
            else:
                parts.append(
                    "⚠️ Món này có thể chứa purine ở mức trung bình — "
                    "hạn chế khẩu phần và theo dõi phản ứng cơ thể."
                )
        else:
            parts.append("Ưu tiên rau củ và ngũ cốc — hạn chế hải sản và nội tạng.")

    # ── IBS ───────────────────────────────────────────────────────────────────
    if df.get("ibs"):
        parts.append(
            "Nguyên liệu dễ tiêu hoá — phù hợp đường ruột nhạy cảm. "
            "Tránh ăn quá nhanh hoặc quá no."
        )

    # ── BMI ───────────────────────────────────────────────────────────────────
    bmi = profile.get("BMI", 22)
    if bmi and bmi > 25 and cal:
        parts.append(f"Ít calo ({cal:.0f}kcal/serving) — hỗ trợ kiểm soát cân nặng.")
    elif bmi and bmi < 18.5 and cal:
        parts.append(f"Giàu năng lượng ({cal:.0f}kcal/serving) — bổ sung đủ dinh dưỡng.")

    # ── Diet type ─────────────────────────────────────────────────────────────
    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        parts.append("100% thực vật — không chứa nguyên liệu động vật.")
    elif diet == "vegetarian" and dish.get("is_vegetarian"):
        parts.append("Món chay — không có thịt, phù hợp chế độ ăn của bạn.")

    return " | ".join(parts) if parts else None


def _build_ingredient_note(boost: float, basket_ingredient_ids: set,
                            dish_id: Any, db: sqlite3.Connection) -> str | None:
    if boost <= 0.05 or not basket_ingredient_ids:
        return None

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
    sm = _safe_json(dish.get("season_suitability"), {})
    score = sm.get(season, 0.0) if isinstance(sm, dict) else 0.0
    if score < 0.55:
        return None
    dish_name = dish.get("title", "Món này")
    return _get_best_template(
        db, "season", season, score,
        fallback=f"{dish_name} rất hợp với thời tiết {season} hiện tại.",
        dish_name=dish_name,
        main_ingredient=dish_name,
    )


def _generate_tags(dish: dict, demand: dict, profile: dict, boost: float,
                   season: str, db: sqlite3.Connection) -> list[str]:
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
        t = _lookup_tag("hydration_high", h) or "💧 Bù nước tốt"
        tags.append(t)
    elif h >= 0.30:
        t = _lookup_tag("hydration_mid", h) or "💧 Bù nước"
        tags.append(t)

    # Cooling / Warming
    c = demand.get("cooling_food_need", 0)
    w = demand.get("warming_food_need", 0)
    if c >= 0.60:
        t = _lookup_tag("cooling_high", c) or "🧊 Thanh nhiệt"
        tags.append(t)
    elif c >= 0.30:
        t = _lookup_tag("cooling_mid", c) or "🧊 Mát"
        tags.append(t)
    if w >= 0.60:
        t = _lookup_tag("warming_high", w) or "🔥 Giữ ấm"
        tags.append(t)
    elif w >= 0.30:
        t = _lookup_tag("warming_mid", w) or "🔥 Ấm"
        tags.append(t)

    # Disease tags
    df     = profile.get("disease_flags", {})
    sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
    gl     = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0
    gout_s = dish.get("gout_risk_score")

    if df.get("hypertension") and sodium and sodium < 600:
        t = _lookup_tag("low_sodium", 0.5) or "🫀 Ít muối"
        tags.append(t)

    if df.get("diabetes") and gl and gl < 12:
        t = _lookup_tag("low_gl", 0.5) or "🩸 GL thấp"
        tags.append(t)

    if df.get("gout") and gout_s is not None and gout_s >= 0.7:
        t = _lookup_tag("low_purine", 0.5) or "✅ Ít purine"
        tags.append(t)

    if df.get("ibs"):
        t = _lookup_tag("ibs_friendly", 0.5) or "🌿 Dễ tiêu"
        tags.append(t)

    # Immunity
    inf = demand.get("infection_risk", 0)
    if inf >= 0.50:
        t = _lookup_tag("immunity", inf) or "🛡️ Tăng miễn dịch"
        tags.append(t)

    # Diet type
    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        t = _lookup_tag("vegan_tag", 0.5) or "🌱 Thuần chay"
        tags.append(t)
    elif diet == "vegetarian":
        t = _lookup_tag("vegetarian_tag", 0.5) or "🥗 Chay"
        tags.append(t)

    # Quick cook
    ct = dish.get("cook_time_minutes") or 999
    if ct <= 20:
        t = _lookup_tag("quick_cook", 0.5) or "⚡ Nấu nhanh"
        tags.append(t)

    # Ingredient boost
    if boost >= 0.60:
        t = _lookup_tag("high_boost", boost) or "🛒 Có sẵn nguyên liệu"
        tags.append(t)

    # Season match
    sm = _safe_json(dish.get("season_suitability"), {})
    if isinstance(sm, dict) and sm.get(season, 0) >= 0.65:
        t = _lookup_tag("season_match", 0.7) or "🍃 Hợp mùa"
        tags.append(t)

    # Dedup + giới hạn 5 tags
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
    _ensure_table(db)

    # Cache _dominant_demands — dùng chung cho tất cả sub-builders
    headline        = _build_headline(dish, demand, db)
    weather_reason  = _build_weather_reason(demand, temperature, db)
    dish_match      = _build_dish_match(dish, demand)
    nutrition_note  = _build_nutrition_note(dish, profile)
    ingredient_note = _build_ingredient_note(boost, basket_ingredient_ids, dish["id"], db)
    seasonal_note   = _build_seasonal_note(dish, season, db)
    tags            = _generate_tags(dish, demand, profile, boost, season, db)

    return {
        "headline":        headline,
        "weather_reason":  weather_reason,
        "dish_match":      dish_match,
        "nutrition_note":  nutrition_note,
        "ingredient_note": ingredient_note,
        "seasonal_note":   seasonal_note,
        "tags":            tags,
    }


def _ensure_table(db: sqlite3.Connection):
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
# Backward-compatible
# ─────────────────────────────────────────────────────────────────────────────

def legacy_explain_list(dish: dict, demand: dict, profile: dict,
                         boost: float, loc: dict, season: str,
                         basket_ingredient_ids: set,
                         db: sqlite3.Connection,
                         temperature: float | None = None) -> list[str]:
    exp = build_explanation(dish, demand, profile, boost, loc, season,
                            basket_ingredient_ids, db, temperature)
    parts = [
        exp["weather_reason"],
        exp["dish_match"],
        exp["nutrition_note"],
        exp["ingredient_note"],
        exp["seasonal_note"],
    ]
    return [p for p in parts if p][:4]