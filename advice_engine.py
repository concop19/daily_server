"""
advice_engine.py
================
F06 — Recommendation Explanation Engine (v2)

Thay đổi v2:
  - Thêm FitChecker: check_fit_reasons() — quyết định khía cạnh nào thực sự fit
  - Thêm _build_ingredient_source_note() — truy nguyên chỉ số từ nguyên liệu + cooking method
  - build_explanation() chỉ assemble những reason thực sự active, không bịa lý do

Import vào pipeline.py (không đổi):
    from advice_engine import build_explanation
"""

from __future__ import annotations
import json
from typing import Any

import data_store

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_json(text: str | None, default=None):
    try:
        return json.loads(text or "null") or default
    except Exception:
        return default


def _fill(template: str, **kwargs) -> str:
    result = template
    for k, v in kwargs.items():
        result = result.replace(f"{{{k}}}", str(v))
    return result


def _query_templates(db=None, context_type: str = "", trigger_dim: str = "",
                     intensity: float = 0.5) -> list[dict]:
    """Query templates từ data_store (in-memory). db parameter giữ để tương thích."""
    all_tmpl = data_store.get_all_advice_templates()
    matched = [
        t for t in all_tmpl
        if t.get("context_type") == context_type
        and t.get("trigger_dim") == trigger_dim
        and (t.get("intensity_min") or 0) <= intensity <= (t.get("intensity_max") or 1)
    ]
    matched.sort(key=lambda x: x.get("priority", 99))
    return [{"text": t["template_text"], "priority": t.get("priority", 99)} for t in matched[:3]]


def _get_best_template(db=None, context_type: str = "", trigger_dim: str = "",
                       intensity: float = 0.5, fallback: str = "", **fill_vars) -> str:
    rows = _query_templates(db, context_type, trigger_dim, intensity)
    template = rows[0]["text"] if rows else fallback
    return _fill(template, **fill_vars)


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# FIT CHECKER — Tầng mới: quyết định khía cạnh nào thực sự fit
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

# Hard-coded thresholds — dễ tune, không phụ thuộc profile
FIT_THRESHOLDS = {
    # Thời tiết
    "weather_cooling":    {"demand": "cooling_food_need",  "dish": "adj_cooling_score",   "demand_min": 0.45, "dish_min": 0.55},
    "weather_warming":    {"demand": "warming_food_need",  "dish": "adj_warming_score",    "demand_min": 0.45, "dish_min": 0.55},
    "weather_hydration":  {"demand": "hydration_need",     "dish": "adj_hydration_score",  "demand_min": 0.45, "dish_min": 0.50},
    "weather_energy":     {"demand": "electrolyte_need",   "dish": "adj_thermogenic_score","demand_min": 0.50, "dish_min": 0.55},

    # Bệnh lý — demand luôn = 1.0 khi có flag, chỉ cần check dish score
    "disease_hypertension": {"demand": "sodium_control_need",   "dish": "sodium_safety_score",  "demand_min": 0.9, "dish_min": 0.70},
    "disease_diabetes":     {"demand": "glycemic_control_need", "dish": "gl_safety_score",      "demand_min": 0.9, "dish_min": 0.65},
    "disease_gout":         {"demand": "gout_control_need",     "dish": "gout_risk_score",      "demand_min": 0.9, "dish_min": 0.70},

    # BMI
    "bmi_overweight": None,   # xử lý riêng vì cần so calorie_target
    "bmi_underweight": None,

    # Location / mùa
    "location_season": None,  # xử lý riêng vì cần parse season_suitability JSON
}

# Dimension → (adj_key, raw_key) dùng cho ingredient source note
DIM_SCORE_COLS = {
    "weather_cooling":      ("adj_cooling_score",      "dish_cooling_score",      "cooling_score"),
    "weather_warming":      ("adj_warming_score",       "dish_warming_score",      "warming_score"),
    "weather_hydration":    ("adj_hydration_score",     "dish_hydration_score",    "hydration_score"),
    "weather_energy":       ("adj_thermogenic_score",   "dish_thermogenic_score",  "thermogenic_score"),
    "disease_hypertension": ("adj_sodium_total",        "dish_sodium_total",       "sodium_density"),
    "disease_diabetes":     ("adj_glycemic_load",       "dish_glycemic_load",      "glycemic_index"),
    "disease_gout":         ("gout_risk_score",         "gout_risk_score",         None),
}


def check_fit_reasons(
    dish: dict,
    demand: dict,
    profile: dict,
    loc: dict,
    season: str,
) -> set[str]:
    """
    Trả về set các khía cạnh mà món này thực sự fit với context user.
    Chỉ dùng hard-coded thresholds — không phụ thuộc vào weights scoring.

    Ví dụ output: {"weather_cooling", "disease_hypertension", "location_season"}
    """
    reasons: set[str] = set()

    # ── 1. Weather / demand dimensions ──────────────────────────────────────
    for reason, cfg in FIT_THRESHOLDS.items():
        if cfg is None:
            continue  # xử lý riêng bên dưới
        demand_val = demand.get(cfg["demand"], 0.0)
        dish_val   = dish.get(cfg["dish"]) or dish.get(cfg["dish"].replace("adj_", "dish_")) or 0.0
        if demand_val >= cfg["demand_min"] and float(dish_val) >= cfg["dish_min"]:
            reasons.add(reason)

    # ── 2. BMI ───────────────────────────────────────────────────────────────
    bmi            = profile.get("BMI", 22.0)
    calorie_target = profile.get("calorie_target", 700)
    dish_cal       = dish.get("adj_energy_total") or dish.get("dish_energy_total") or 0
    if bmi > 25 and dish_cal and float(dish_cal) <= calorie_target * 1.1:
        reasons.add("bmi_overweight")
    if bmi < 18.5 and dish_cal and float(dish_cal) >= calorie_target * 0.9:
        reasons.add("bmi_underweight")

    # ── 3. Location / season ─────────────────────────────────────────────────
    sm = _safe_json(dish.get("season_suitability"), {})
    season_score = sm.get(season, 0.0) if isinstance(sm, dict) else 0.0
    trad_compat  = loc.get("traditional_compatibility", 0.0)
    if season_score >= 0.65 and trad_compat >= 0.75:
        reasons.add("location_season")

    return reasons


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# INGREDIENT SOURCE NOTE — Truy nguyên chỉ số từ nguyên liệu + cooking method
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

# Tên hiển thị cho từng dimension
DIM_LABEL = {
    "weather_cooling":      ("tính mát",       "cooling_score",    "điểm mát"),
    "weather_warming":      ("tính ấm",         "warming_score",    "điểm ấm"),
    "weather_hydration":    ("khả năng bù nước","hydration_score",  "điểm bù nước"),
    "weather_energy":       ("nhiệt lượng",     "thermogenic_score","điểm nhiệt"),
    "disease_hypertension": ("lượng sodium",    "sodium_density",   "mg sodium/100g"),
    "disease_diabetes":     ("chỉ số GI",       "glycemic_index",   "GI"),
    "disease_gout":         ("purine",          "purine_score",     "điểm purine"),
}

# Tên phương pháp nấu hiển thị
COOKING_METHOD_LABEL = {
    "nau_canh":    "nấu canh",
    "nau_soup":    "nấu súp",
    "chien":       "chiên",
    "xao":         "xào",
    "nuong":       "nướng",
    "hap":         "hấp",
    "luat":        "luộc",
    "kho":         "kho",
    "tron":        "trộn",
    "goi":         "gọi / ăn sống",
    "ham":         "hầm",
}

# Multiplier column tương ứng với từng dimension
DIM_MULT_COL = {
    "weather_cooling":      "mult_cooling_score",
    "weather_warming":      "mult_warming_score",
    "weather_hydration":    "mult_hydration_score",
    "weather_energy":       "mult_thermogenic_score",
    "disease_hypertension": "mult_sodium_total",
    "disease_diabetes":     "mult_glycemic_load",
    # disease_gout không có cột mult trong DB — xử lý riêng bằng PURINE_COOKING_EFFECT
}

# Ảnh hưởng của phương pháp nấu lên purine (không có trong DB → hardcoded)
# Khoa học: hấp/luộc giúp purine tan một phần vào nước → giảm lượng nạp vào cơ thể
PURINE_COOKING_EFFECT: dict[str, tuple[float, str]] = {
    "luộc":           (0.70, "luộc hòa tan nhiều purine vào nước — nên bỏ nước luộc"),
    "hấp":            (0.80, "hấp giúp một phần purine tan vào nước ngưng tụ"),
    "hap_cach_thuy":  (0.80, "hấp cách thủy giúp một phần purine tan ra ngoài"),
    "nấu canh":       (0.75, "nấu canh hòa tan purine vào nước — hạn chế uống nước lèo"),
    "nau_canh":       (0.75, "nấu canh hòa tan purine vào nước — hạn chế uống nước lèo"),
    "nau_soup":       (0.75, "nấu súp hòa tan purine vào nước dùng"),
    "hầm":            (0.70, "hầm lâu giúp phần lớn purine tan vào nước hầm"),
    "xào":            (1.00, "xào ở nhiệt độ cao không làm giảm purine đáng kể"),
    "chiên":          (1.00, "chiên không làm giảm purine"),
    "nướng":          (1.00, "nướng không làm giảm purine"),
    "kho":            (0.90, "kho giữ phần lớn purine trong thịt"),
}


def _build_ingredient_source_note(
    dish: dict,
    active_reasons: set[str],
    db=None,
) -> str | None:
    """
    Truy nguyên tại sao món có chỉ số như vậy.
    - Top-5 nguyên liệu (bỏ pantry) theo quantity_g
    - Show score từng nguyên liệu cho dimension active nhất
    - Tính weighted sum → giải thích chỉ số cuối
    - Giải thích ảnh hưởng cooking method

    Ví dụ output (gout):
      "Purine của món chủ yếu đến từ: đậu hủ (57%, purine 0.05);
       đậu non (29%, purine 0.15); thịt băm (14%, purine 0.50).
       Purine tổng hợp ≈ 0.19 → điểm an toàn gout ≈ 81%.
       Phương pháp hấp giúp một phần purine tan vào nước ngưng tụ."
    """
    PRIORITY_ORDER = [
        "disease_hypertension", "disease_diabetes", "disease_gout",
        "weather_cooling", "weather_warming", "weather_hydration", "weather_energy",
    ]
    active_dim = next((d for d in PRIORITY_ORDER if d in active_reasons), None)
    if active_dim is None:
        return None

    label_info = DIM_LABEL.get(active_dim)
    if not label_info:
        return None
    dim_display, ingr_score_col, unit_label = label_info

    dish_id = dish.get("id")
    if not dish_id:
        return None

    PANTRY = frozenset(['Dầu & Mỡ', 'Sữa & Trứng', 'Ngũ cốc & Tinh bột', 'Gia vị'])

    # Load top-5 non-pantry ingredients by quantity_g from data_store
    di_rows = data_store.get_dish_ingredient_rows(dish_id)
    enriched = []
    for row in di_rows:
        if not (row.get("quantity_g") or 0) > 0:
            continue
        ing = data_store.get_ingredient_by_id(int(row.get("ingredient_id", 0)))
        if not ing:
            continue
        cat = ing.get("ingredient_type") or ing.get("category", "")
        if cat in PANTRY:
            continue
        score_val = ing.get(ingr_score_col) if ingr_score_col else None
        enriched.append({
            "name": ing.get("name", ""),
            "quantity_g": float(row["quantity_g"]),
            "score_val": float(score_val) if score_val is not None else None,
        })
    enriched.sort(key=lambda x: x["quantity_g"], reverse=True)
    rows_data = enriched[:5]

    if not rows_data:
        return None

    total_g = sum(r["quantity_g"] for r in rows_data)
    if total_g == 0:
        return None

    # ── Xây danh sách nguyên liệu ─────────────────────────────────────────
    parts = []
    weighted_sum = 0.0
    has_scores = False

    for row_item in rows_data[:3]:
        name, qty_g, score_val = row_item["name"], row_item["quantity_g"], row_item["score_val"]
        pct = round(float(qty_g) / total_g * 100)
        weight = float(qty_g) / total_g
        if score_val is not None:
            sv = float(score_val)
            weighted_sum += sv * weight
            has_scores = True
            parts.append(f"{name} ({pct}%, {unit_label} {sv:.2f})")
        else:
            parts.append(f"{name} ({pct}%)")

    if not parts:
        return None

    ingr_str = "; ".join(parts)
    sentence = f"{dim_display.capitalize()} của món chủ yếu đến từ: {ingr_str}."

    # ── Câu tổng kết weighted calculation ────────────────────────────────
    if has_scores and len(rows_data) >= 2:
        if active_dim == "disease_gout":
            # gout_risk_score = 1 - weighted_purine → an toàn bao nhiêu %
            safety_pct = round((1.0 - weighted_sum) * 100)
            sentence += f" Purine tổng hợp ≈ {weighted_sum:.2f} → điểm an toàn gout ≈ {safety_pct}%."
        elif active_dim == "disease_hypertension":
            sentence += f" Sodium tổng hợp từ nguyên liệu ≈ {weighted_sum:.1f} mg/100g."
        elif active_dim == "disease_diabetes":
            sentence += f" Chỉ số GI tổng hợp ≈ {weighted_sum:.1f}."
        else:
            # weather dims — show weighted score
            score_pct = round(weighted_sum * 100)
            sentence += f" {dim_display.capitalize()} tổng hợp từ nguyên liệu ≈ {score_pct}%."

    # ── Cooking method note ───────────────────────────────────────────────
    method_name_raw = None
    if dish.get("cooking_method_id"):
        for cm in data_store.get_all_cooking_methods():
            if cm.get("method_id") == dish["cooking_method_id"]:
                method_name_raw = cm.get("method_name")
                break
    if active_dim == "disease_gout":
        # Dùng PURINE_COOKING_EFFECT thay vì DIM_MULT_COL
        if method_name_raw:
            effect = PURINE_COOKING_EFFECT.get(method_name_raw)
            if effect:
                mult_val, effect_desc = effect
                retained_pct = round(mult_val * 100)
                method_display = COOKING_METHOD_LABEL.get(method_name_raw, method_name_raw)
                sentence += f" Phương pháp {method_display}: {effect_desc} (≈{retained_pct}% purine còn lại)."
    else:
        # Dùng DIM_MULT_COL như cũ cho các dimension khác
        mult_col = DIM_MULT_COL.get(active_dim)
        if mult_col and method_name_raw and dish.get("cooking_method_id"):
            try:
                cm_row = next(
                    (cm for cm in data_store.get_all_cooking_methods()
                     if cm.get("method_id") == dish["cooking_method_id"]),
                    None
                )
                if cm_row and cm_row.get(mult_col) is not None:
                    method_display = COOKING_METHOD_LABEL.get(cm_row["method_name"], cm_row.get("method_name", "chế biến"))
                    mult_val = float(cm_row[mult_col])
                    if mult_val >= 0.95:
                        effect = f"giữ nguyên {round(mult_val*100)}%"
                    elif mult_val >= 0.75:
                        effect = f"giữ được {round(mult_val*100)}%"
                    else:
                        effect = f"còn lại {round(mult_val*100)}%"
                    sentence += f" Phương pháp {method_display} {effect} {dim_display} (×{mult_val:.2f})."
            except Exception:
                pass

    return sentence


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# SUB-BUILDERS (giữ nguyên từ v1, không thay đổi)
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

DEMAND_KEYS = [
    "hydration_need", "cooling_food_need", "warming_food_need",
    "infection_risk", "cold_stress_index", "electrolyte_need",
    "sodium_control_need", "glycemic_control_need",
    "gout_control_need", "ibs_control_need",
]

def _dominant_demands(demand: dict, top_k: int = 2) -> list[tuple[str, float]]:
    scored = [(k, demand.get(k, 0.0)) for k in DEMAND_KEYS]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(k, v) for k, v in scored[:top_k] if v > 0.0]


def _primary_demand(demand: dict) -> tuple[str, float]:
    tops = _dominant_demands(demand, top_k=1)
    return tops[0] if tops else ("hydration_need", 0.0)


def _build_headline(dish: dict, demand: dict, db=None) -> str:
    dish_name = dish.get("title", "Món ăn")
    tops = _dominant_demands(demand, top_k=2)
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
                           db=None) -> str:
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
    tops = _dominant_demands(demand, top_k=2)
    name = dish.get("title", "Món này")
    DIM_TEMPLATES = {
        "hydration_need": (
            "{name} có hàm lượng nước cao (điểm bù nước: {score:.0%}), giúp cơ thể duy trì độ ẩm tốt.",
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
            "{name} có lượng muối thấp ({score:.0f}mg sodium/serving) — phù hợp với người cần kiểm soát huyết áp.",
            "adj_sodium_total", "dish_sodium_total", False
        ),
        "glycemic_control_need": (
            "{name} có chỉ số đường huyết thấp (GL {score:.1f}) — giúp kiểm soát lượng đường trong máu ổn định.",
            "adj_glycemic_load", "dish_glycemic_load", False
        ),
        "gout_control_need": (
            "{name} có hàm lượng purine thấp (điểm an toàn: {score:.0%}) — phù hợp với người bị gout.",
            "gout_risk_score", None, False
        ),
        "ibs_control_need": (
            "{name} sử dụng nguyên liệu dễ tiêu hoá, thân thiện với đường ruột nhạy cảm.",
            None, None, False
        ),
    }
    parts = []
    for dim, val in tops:
        if dim not in DIM_TEMPLATES:
            continue
        tpl, adj, raw, invert = DIM_TEMPLATES[dim]
        if adj:
            dish_score = dish.get(adj, None)
            if dish_score is None and raw:
                dish_score = dish.get(raw, None)
            dish_score = float(dish_score) if dish_score is not None else 0.0
        else:
            dish_score = 0.0
        if invert and dish_score > 0:
            dish_score = 1.0 - dish_score
        parts.append(tpl.format(name=name, score=dish_score))
    return " ".join(parts) if parts else f"{name} phù hợp với nhu cầu dinh dưỡng hôm nay."


def _build_nutrition_note(dish: dict, profile: dict) -> str | None:
    parts = []
    df    = profile.get("disease_flags", {})
    sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
    gl     = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0
    cal    = dish.get("adj_energy_total")  or dish.get("dish_energy_total")  or 0
    gout_s = dish.get("gout_risk_score")

    if df.get("hypertension") and sodium:
        if sodium < 400:
            parts.append(f"Rất ít sodium ({sodium:.0f}mg/serving) — lý tưởng cho huyết áp cao.")
        elif sodium < 500:
            parts.append(f"Ít sodium ({sodium:.0f}mg/serving) — phù hợp với huyết áp cao.")
        else:
            parts.append(
                f"⚠️ Sodium ở mức {sodium:.0f}mg/serving (giới hạn 600mg) — "
                f"không nên thêm nước mắm hoặc muối khi ăn."
            )

    if df.get("diabetes") and gl:
        if gl < 7:
            parts.append(f"Chỉ số đường huyết rất thấp (GL {gl:.1f}) — lý tưởng kiểm soát đường máu.")
        elif gl < 10:
            parts.append(f"Chỉ số đường huyết thấp (GL {gl:.1f}) — an toàn cho người tiểu đường.")
        else:
            parts.append(
                f"⚠️ Glycemic load {gl:.1f} — ăn chậm, kết hợp rau xanh nhiều xơ "
                f"để giảm tốc độ hấp thụ đường."
            )

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

    if df.get("ibs"):
        parts.append(
            "Nguyên liệu dễ tiêu hoá — phù hợp đường ruột nhạy cảm. "
            "Tránh ăn quá nhanh hoặc quá no."
        )

    bmi = profile.get("BMI", 22)
    if bmi and bmi > 25 and cal:
        parts.append(f"Ít calo ({cal:.0f}kcal/serving) — hỗ trợ kiểm soát cân nặng.")
    elif bmi and bmi < 18.5 and cal:
        parts.append(f"Giàu năng lượng ({cal:.0f}kcal/serving) — bổ sung đủ dinh dưỡng.")

    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        parts.append("100% thực vật — không chứa nguyên liệu động vật.")
    elif diet == "vegetarian" and dish.get("is_vegetarian"):
        parts.append("Món chay — không có thịt, phù hợp chế độ ăn của bạn.")

    return " | ".join(parts) if parts else None


def _build_ingredient_note(boost: float, basket_ingredient_ids: set,
                            dish_id: Any, db=None) -> str | None:
    if boost <= 0.05 or not basket_ingredient_ids:
        return None

    # Lấy main ingredients của dish từ data_store, lọc theo basket_ingredient_ids
    di_rows = data_store.get_dish_ingredient_rows(dish_id)
    basket_set = set(basket_ingredient_ids)
    matched_names = []
    for row in di_rows:
        if not row.get("is_main"):
            continue
        ing_id = int(row.get("ingredient_id", 0))
        if ing_id not in basket_set:
            continue
        ing = data_store.get_ingredient_by_id(ing_id)
        if ing:
            matched_names.append(ing.get("name", ""))
        if len(matched_names) >= 4:
            break

    if not matched_names:
        return None

    ingredient_names = ", ".join(matched_names)
    if boost >= 0.75:
        dim_key  = "boost_high"
        fallback = f"Hầu hết nguyên liệu chính ({ingredient_names}) đều có trong giỏ hàng — tiện nấu ngay!"
    elif boost >= 0.40:
        dim_key  = "boost_medium"
        fallback = f"{ingredient_names} từ giỏ hàng hôm nay được dùng trong món này."
    else:
        dim_key  = "boost_low"
        fallback = f"Một số nguyên liệu bạn đã mua ({ingredient_names}) có thể dùng cho món này."

    tmpl_rows = data_store.get_advice_templates("ingredient", dim_key, "medium")
    tpl = tmpl_rows[0]["template_text"] if tmpl_rows else fallback
    return _fill(tpl, ingredient_names=ingredient_names)


def _build_seasonal_note(dish: dict, season: str, db=None) -> str | None:
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
                   season: str, db=None) -> list[str]:
    tags: list[str] = []

    def _lookup_tag(trigger_dim: str, intensity: float) -> str | None:
        rows = data_store.get_advice_templates("tag", trigger_dim, "medium")
        return rows[0]["template_text"] if rows else None

    h = demand.get("hydration_need", 0)
    if h >= 0.60:
        tags.append(_lookup_tag("hydration_high", h) or "💧 Bù nước tốt")
    elif h >= 0.30:
        tags.append(_lookup_tag("hydration_mid", h) or "💧 Bù nước")

    c = demand.get("cooling_food_need", 0)
    w = demand.get("warming_food_need", 0)
    if c >= 0.60:
        tags.append(_lookup_tag("cooling_high", c) or "🧊 Thanh nhiệt")
    elif c >= 0.30:
        tags.append(_lookup_tag("cooling_mid", c) or "🧊 Mát")
    if w >= 0.60:
        tags.append(_lookup_tag("warming_high", w) or "🔥 Giữ ấm")
    elif w >= 0.30:
        tags.append(_lookup_tag("warming_mid", w) or "🔥 Ấm")

    df     = profile.get("disease_flags", {})
    sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
    gl     = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0
    gout_s = dish.get("gout_risk_score")

    if df.get("hypertension") and sodium and sodium < 600:
        tags.append(_lookup_tag("low_sodium", 0.5) or "🫀 Ít muối")
    if df.get("diabetes") and gl and gl < 12:
        tags.append(_lookup_tag("low_gl", 0.5) or "🩸 GL thấp")
    if df.get("gout") and gout_s is not None and gout_s >= 0.7:
        tags.append(_lookup_tag("low_purine", 0.5) or "✅ Ít purine")
    if df.get("ibs"):
        tags.append(_lookup_tag("ibs_friendly", 0.5) or "🌿 Dễ tiêu")

    inf = demand.get("infection_risk", 0)
    if inf >= 0.50:
        tags.append(_lookup_tag("immunity", inf) or "🛡️ Tăng miễn dịch")

    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        tags.append(_lookup_tag("vegan_tag", 0.5) or "🌱 Thuần chay")
    elif diet == "vegetarian":
        tags.append(_lookup_tag("vegetarian_tag", 0.5) or "🥗 Chay")

    ct = dish.get("cook_time_minutes") or 999
    if ct <= 20:
        tags.append(_lookup_tag("quick_cook", 0.5) or "⚡ Nấu nhanh")
    if boost >= 0.60:
        tags.append(_lookup_tag("high_boost", boost) or "🛒 Có sẵn nguyên liệu")

    sm = _safe_json(dish.get("season_suitability"), {})
    if isinstance(sm, dict) and sm.get(season, 0) >= 0.65:
        tags.append(_lookup_tag("season_match", 0.7) or "🍃 Hợp mùa")

    seen, result = set(), []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
        if len(result) >= 5:
            break
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — build_explanation() v2
# Chỉ assemble những reasons thực sự active từ FitChecker
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

def build_explanation(
    dish: dict,
    demand: dict,
    profile: dict,
    boost: float,
    loc: dict,
    season: str,
    basket_ingredient_ids: set,
    db=None,
    temperature: float | None = None,
) -> dict:
    """
    v2: FitChecker quyết định khía cạnh nào thực sự fit trước khi build.

    Return schema (fields có thể None nếu không fit):
    {
        "headline":               str,
        "active_reasons":         list[str],   # NEW — để frontend biết lý do gì active
        "weather_reason":         str | None,  # chỉ có nếu weather dim fit
        "dish_match":             str | None,  # chỉ có nếu demand fit
        "nutrition_note":         str | None,  # chỉ có nếu bệnh / BMI fit
        "ingredient_source_note": str | None,  # NEW — truy nguyên từ nguyên liệu
        "ingredient_note":        str | None,  # giỏ hàng (giữ nguyên v1)
        "seasonal_note":          str | None,  # mùa vụ (giữ nguyên v1)
        "tags":                   list[str],
    }
    """
    _ensure_table(db)

    # ── Step 1: FitChecker ───────────────────────────────────────────────────
    active_reasons = check_fit_reasons(dish, demand, profile, loc, season)

    # ── Step 2: Headline — luôn có ──────────────────────────────────────────
    headline = _build_headline(dish, demand, db)

    # Định nghĩa nhóm reasons — dùng từ step 3 trở đi
    WEATHER_REASONS = {"weather_cooling", "weather_warming", "weather_hydration", "weather_energy"}
    DISEASE_REASONS = {"disease_hypertension", "disease_diabetes", "disease_gout"}
    BMI_REASONS     = {"bmi_overweight", "bmi_underweight"}

    # ── Step 3: Weather reason — chỉ build nếu có weather reason active ─────
    weather_reason = None
    if active_reasons & WEATHER_REASONS:
        weather_reason = _build_weather_reason(demand, temperature, db)

    # ── Step 4: Dish match — build khi có weather HOẶC disease reason active ─
    dish_match = None
    if active_reasons & (WEATHER_REASONS | DISEASE_REASONS):
        dish_match = _build_dish_match(dish, demand)

    # ── Step 5: Nutrition note — chỉ build nếu disease / BMI fit ────────────
    nutrition_note = None
    if active_reasons & (DISEASE_REASONS | BMI_REASONS):
        nutrition_note = _build_nutrition_note(dish, profile)

    # ── Step 6: Ingredient source note — NEW ────────────────────────────────
    # Build khi có ít nhất 1 reason (weather hoặc disease) để truy nguyên
    ingredient_source_note = None
    if active_reasons - {"location_season"}:   # bỏ location_season vì không có dimension rõ ràng
        ingredient_source_note = _build_ingredient_source_note(dish, active_reasons, db)

    # ── Step 7: Ingredient basket note — giữ nguyên v1 ──────────────────────
    ingredient_note = _build_ingredient_note(boost, basket_ingredient_ids, dish.get("id"), db)

    # ── Step 8: Seasonal note — chỉ build nếu location_season fit ───────────
    seasonal_note = None
    if "location_season" in active_reasons:
        seasonal_note = _build_seasonal_note(dish, season, db)

    # ── Step 9: Tags ─────────────────────────────────────────────────────────
    tags = _generate_tags(dish, demand, profile, boost, season, db)

    return {
        "headline":               headline,
        "active_reasons":         sorted(active_reasons),   # sorted để stable output
        "weather_reason":         weather_reason,
        "dish_match":             dish_match,
        "nutrition_note":         nutrition_note,
        "ingredient_source_note": ingredient_source_note,
        "ingredient_note":        ingredient_note,
        "seasonal_note":          seasonal_note,
        "tags":                   tags,
    }


def _ensure_table(db=None):
    """No-op — advice_templates loaded from JSON via data_store."""
    pass


# ── Backward-compat ───────────────────────────────────────────────────────────
def legacy_explain_list(dish: dict, demand: dict, profile: dict,
                         boost: float, loc: dict, season: str,
                         basket_ingredient_ids: set,
                         db=None,
                         temperature: float | None = None) -> list[str]:
    exp = build_explanation(dish, demand, profile, boost, loc, season,
                            basket_ingredient_ids, db, temperature)
    parts = [
        exp["weather_reason"],
        exp["dish_match"],
        exp["nutrition_note"],
        exp["ingredient_source_note"],
        exp["ingredient_note"],
        exp["seasonal_note"],
    ]
    return [p for p in parts if p][:4]
