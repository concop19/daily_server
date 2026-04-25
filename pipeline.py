"""
pipeline.py — Logic gợi ý món: location, personal, demand, constraint, filter, score, rank.
"""

import json
import math

from weather import compute_weather_vector, get_current_season

try:
    from advice_engine import build_explanation
    _HAS_ADVICE_ENGINE = True
except ImportError:
    _HAS_ADVICE_ENGINE = False

# ── Constants ────────────────────────────────────────────────────────────────
ACTIVITY_MULT = {
    "sedentary":         1.2,
    "lightly_active":    1.375,
    "moderately_active": 1.55,
    "very_active":       1.725,
}

TASTE_DEFAULTS = {
    "spicy": 0.5, "sweet": 0.5, "sour": 0.4,
    "umami": 0.6, "salty": 0.4, "bitter": 0.2, "astringent": 0.1,
}

ALLERGY_CATEGORY_MAP: dict[str, set[str]] = {
    "seafood":   {"Hải sản"},
    "meat":      {"Thịt"},
    "dairy":     {"Sữa & Trứng"},
    "egg":       {"Sữa & Trứng"},
    "nut":       {"Đậu & Hạt"},
    "gluten":    {"Ngũ cốc & Tinh bột", "Đã chế biến"},
    "soy":       {"Đậu & Hạt", "Đã chế biến"},
    "pork":      {"Thịt"},
    "fish":      {"Hải sản"},
    "shellfish": {"Hải sản"},
    "wheat":     {"Ngũ cốc & Tinh bột"},
}

# Purine risk theo (category, source_type) — dùng cho gout_risk_score
# 1.0 = nguy hiểm cao nhất, 0.0 = an toàn
GOUT_PURINE_RISK: dict[tuple[str, str], float] = {
    ("Hải sản",    "aquatic_coast"):  1.0,   # tôm, cua, mực
    ("Hải sản",    "processed"):      0.7,   # hải sản chế biến
    ("Thịt",       "livestock"):      0.7,   # thịt đỏ, nội tạng
    ("Thịt",       "processed"):      0.6,   # xúc xích, thịt hộp
    ("Hải sản",    "aquatic_inland"): 0.4,   # cá nước ngọt
    ("Thịt",       "aquatic_inland"): 0.4,   # ếch, ba ba
    ("Đã chế biến","processed"):      0.3,   # unknown mixed
    ("Đậu & Hạt",  "farm_local"):     0.2,   # đậu tươi
    ("Đậu & Hạt",  "processed"):      0.2,   # đậu chế biến
    # Tất cả còn lại: 0.0 (Rau củ, Trái cây, Ngũ cốc, Sữa & Trứng,
    #                       Gia vị, Dầu & Mỡ, Thực phẩm bổ dưỡng, Đồ uống)
}

CLIMATE_MODIFIER = {
    "tropical":         {"warming": 0.8, "cooling": 1.2, "hydration": 1.1},
    "subtropical":      {"warming": 1.2, "cooling": 0.8, "hydration": 0.9},
    "tropical_monsoon": {"warming": 0.9, "cooling": 1.1, "hydration": 1.2},
    "highland":         {"warming": 1.3, "cooling": 0.7, "hydration": 0.9},
    "temperate":        {"warming": 1.1, "cooling": 0.9, "hydration": 1.0},
}

# Sodium limit theo hypertension (mg/serving)
SODIUM_LIMIT_HYPERTENSION = 600.0
SODIUM_LIMIT_NORMAL        = 1500.0

# Glycemic load limit
GL_LIMIT_DIABETES = 10.0
GL_LIMIT_NORMAL   = 25.0


# ── STEP 02 — Location ───────────────────────────────────────────────────────
def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def resolve_location(lat: float, lon: float, db) -> dict:
    rows = db.execute("""
        SELECT province_name, food_region, lat_center, lon_center,
               climate_type, regional_flavor, cuisine_culture
        FROM vn_administrative_unit
        WHERE lat_center IS NOT NULL AND lon_center IS NOT NULL
    """).fetchall()

    closest, min_dist = None, float("inf")
    for r in rows:
        d = _haversine(lat, lon, r["lat_center"], r["lon_center"])
        if d < min_dist:
            min_dist, closest = d, r

    if closest:
        return {
            "province":                  closest["province_name"],
            "food_region":               closest["food_region"],
            "climate_type":              closest["climate_type"] or "tropical",
            "regional_flavor":           closest["regional_flavor"] or "",
            "cuisine_culture":           closest["cuisine_culture"] or "",
            "traditional_compatibility": 0.9,
        }
    return {
        "province": "Unknown", "food_region": "mien_nam",
        "climate_type": "tropical", "regional_flavor": "", "cuisine_culture": "",
        "traditional_compatibility": 0.7,
    }


def get_dish_availability(recipe_id: int, food_region: str, db) -> float:
    rows = db.execute("""
        SELECT i.distribution_reach, di.quantity_g
        FROM dish_ingredient di
        JOIN ingredients i ON di.ingredient_id = i.id
        WHERE di.recipe_id = ? AND di.is_main = 1
          AND di.quantity_g > 0 AND i.distribution_reach IS NOT NULL
    """, (recipe_id,)).fetchall()

    if not rows:
        return 1.0
    total = sum(r["quantity_g"] for r in rows)
    if total == 0:
        return 1.0

    weighted = 0.0
    for r in rows:
        sr = db.execute(
            "SELECT availability_score FROM ingredient_availability_matrix "
            "WHERE distribution_reach=? AND food_region=?",
            (r["distribution_reach"], food_region)
        ).fetchone()
        score = sr["availability_score"] if sr else 0.8
        weighted += score * r["quantity_g"]
    return round(weighted / total, 4)


# ── STEP 03 — Personal vector ────────────────────────────────────────────────
def compute_personal_vector(p: dict) -> dict:
    age    = p.get("age", 28)
    gender = p.get("gender", "female")
    height = p.get("height", 160.0)
    weight = p.get("weight", 55.0)
    h_m    = height / 100
    bmi    = round(weight / (h_m ** 2), 2)
    bmr    = (10 * weight + 6.25 * height - 5 * age + 5
              if gender == "male"
              else 10 * weight + 6.25 * height - 5 * age - 161)
    mult = ACTIVITY_MULT.get(p.get("activity_level", "moderately_active"), 1.55)
    tdee = round(bmr * mult, 2)

    health = p.get("health_condition", [])
    disease_flags = {
        "hypertension": "hypertension" in health,
        "diabetes":     "diabetes"     in health,
        "gout":         "gout"         in health,
        "ibs":          "ibs"          in health,
    }

    raw_prefs    = p.get("taste_preference", [])
    taste_weight = dict(TASTE_DEFAULTS)
    for t in raw_prefs:
        if t in taste_weight:
            taste_weight[t] = min(1.0, taste_weight[t] + 0.3)

    return {
        "BMI":                  bmi,
        "bmr":                  round(bmr, 2),
        "activity_level_mult":  mult,
        "energy_need":          tdee,
        "disease_flags":        disease_flags,
        "taste_weight":         taste_weight,
        "has_taste_preference": len(raw_prefs) > 0,
        "diet_type":            p.get("diet_type", "omnivore"),
        "allergies":            p.get("allergies", []),
        "max_prep_time":        int(p.get("max_prep_time", 60)),
    }


# ── STEP 04 — Physiological demand ──────────────────────────────────────────
def compute_demand(wv: dict, pv: dict, climate_type: str) -> dict:
    act_n = (pv["activity_level_mult"] - 1.2) / (1.9 - 1.2)
    h  = min(1.0, 0.5 * wv["dehydration_risk"] + 0.3 * wv["heat_stress_index"] + 0.2 * act_n)
    e  = min(1.0, 0.6 * h + 0.4 * act_n)
    th = max(wv["heat_stress_index"], wv["cold_stress_index"])
    en = pv["energy_need"] * (1 - 0.1 * wv["heat_stress_index"] + 0.1 * wv["cold_stress_index"])
    w  = min(1.0, 0.6 * wv["cold_stress_index"] + 0.4 * (1 - wv["heat_stress_index"]))
    c  = min(1.0, 0.6 * wv["heat_stress_index"] + 0.4 * (1 - wv["cold_stress_index"]))
    mod = CLIMATE_MODIFIER.get(climate_type, {"warming": 1.0, "cooling": 1.0, "hydration": 1.0})
    h = min(1.0, h * mod["hydration"])
    w = min(1.0, w * mod["warming"])
    c = min(1.0, c * mod["cooling"])
    df = pv["disease_flags"]
    return {
        "hydration_need":        round(h,  4),
        "electrolyte_need":      round(e,  4),
        "thermoregulation_need": round(th, 4),
        "energy_need":           round(en, 2),
        "warming_food_need":     round(w,  4),
        "cooling_food_need":     round(c,  4),
        # Disease control needs — dùng trong explanation, không dùng trong DIMS scoring
        "sodium_control_need":   1.0 if df.get("hypertension") else 0.0,
        "glycemic_control_need": 1.0 if df.get("diabetes")     else 0.0,
        "gout_control_need":     1.0 if df.get("gout")         else 0.0,
        "ibs_control_need":      1.0 if df.get("ibs")          else 0.0,
    }


# ── STEP 05 — Constraint profile ─────────────────────────────────────────────
def resolve_allergy_ingredient_ids(allergies: list, db) -> set[int]:
    if not allergies:
        return set()
    explicit_ids = {int(x) for x in allergies
                    if isinstance(x, int) or (isinstance(x, str) and x.isdigit())}
    category_groups = {x for x in allergies if isinstance(x, str) and not x.isdigit()}

    blocked_categories: set[str] = set()
    for group in category_groups:
        blocked_categories.update(ALLERGY_CATEGORY_MAP.get(group.lower().strip(), set()))

    db_ids = set()
    if blocked_categories:
        placeholders = ",".join("?" * len(blocked_categories))
        rows = db.execute(
            f"SELECT id FROM ingredients WHERE category IN ({placeholders})",
            list(blocked_categories)
        ).fetchall()
        db_ids = {r[0] for r in rows}

    return explicit_ids | db_ids


def build_constraint_profile(pv: dict, db) -> dict:
    df  = pv["disease_flags"]
    raw_allergies = list(pv.get("allergies", []))
    allergy_categories = [x for x in raw_allergies if isinstance(x, str) and not x.isdigit()]

    # Gout → thêm blacklist shellfish + hải sản ven biển vào allergy
    # (hard filter bổ sung, ngoài gout_risk_score dùng trong scoring)
    if df.get("gout") and "shellfish" not in allergy_categories:
        allergy_categories.append("shellfish")

    return {
        "allergy_blacklist":      allergy_categories,
        "allergy_ingredient_ids": resolve_allergy_ingredient_ids(raw_allergies, db),
        "diet_type":              pv.get("diet_type", "omnivore"),
        "sodium_limit_mg":        SODIUM_LIMIT_HYPERTENSION if df.get("hypertension") else SODIUM_LIMIT_NORMAL,
        "glycemic_load_limit":    GL_LIMIT_DIABETES         if df.get("diabetes")     else GL_LIMIT_NORMAL,
        "calorie_target":         round(pv["energy_need"] * 0.35, 0),
        "max_prep_time":          pv.get("max_prep_time", 60),
        "disease_flags":          df,
    }


# ── STEP 06 — Filter ─────────────────────────────────────────────────────────
def _get_dish_ingredient_ids(recipe_ids: list, db) -> dict[int, set[int]]:
    if not recipe_ids:
        return {}
    placeholders = ",".join("?" * len(recipe_ids))
    rows = db.execute(
        f"SELECT recipe_id, ingredient_id FROM dish_ingredient "
        f"WHERE recipe_id IN ({placeholders})",
        recipe_ids
    ).fetchall()
    result: dict[int, set[int]] = {}
    for recipe_id, ing_id in rows:
        result.setdefault(recipe_id, set()).add(ing_id)
    return result


def filter_dishes(db, cuisine_scope: str, selected_nation: str | None,
                  profile: dict, current_season: str,
                  dish_type_filter: str = "all") -> list[dict]:
    max_time    = profile.get("max_prep_time", 60)
    hard_ceiling = None if max_time >= 999 else max_time + 10

    if cuisine_scope == "vietnam":
        nation_sql, nation_params = "AND LOWER(d.nation) = 'vietnam'", {}
    elif cuisine_scope == "specific_nation" and selected_nation:
        nation_sql, nation_params = "AND d.nation = :nation", {"nation": selected_nation}
    else:
        nation_sql, nation_params = "", {}

    if dish_type_filter == "soup":
        type_sql = "AND (cm.method_name = 'nau_canh' OR cm.method_name = 'nau_soup')"
    elif dish_type_filter == "main_dish":
        type_sql = "AND (cm.method_name IS NULL OR cm.method_name NOT IN ('nau_canh','nau_soup'))"
    else:
        type_sql = ""

    sql = f"""
        SELECT d.id, d.title, d.nation, d.cook_time_minutes, d.cooking_method_id,
               d.image_url, d.url, d.is_vegan, d.is_vegetarian, d.allergen_summary,
               d.taste_profile, d.season_suitability, d.total_weight_g,
               d.adj_hydration_score,   d.dish_hydration_score,
               d.adj_thermogenic_score, d.dish_thermogenic_score,
               d.adj_warming_score,     d.dish_warming_score,
               d.adj_cooling_score,     d.dish_cooling_score,
               d.adj_satiety_score,     d.dish_satiety_score,
               d.adj_energy_total,      d.dish_energy_total,
               d.adj_sodium_total,      d.dish_sodium_total,
               d.adj_glycemic_load,     d.dish_glycemic_load,
               d.sodium_safety_score,
               d.gl_safety_score,
               d.gout_risk_score,
               d.cost_level
        FROM dishes d
        LEFT JOIN cooking_methods cm ON d.cooking_method_id = cm.method_id
        WHERE 1=1 {nation_sql} {type_sql} LIMIT 2000
    """
    rows = db.execute(sql, nation_params).fetchall()
    cols = [
        "id", "title", "nation", "cook_time_minutes", "cooking_method_id", "image_url", "url",
        "is_vegan", "is_vegetarian", "allergen_summary", "taste_profile",
        "season_suitability", "total_weight_g",
        "adj_hydration_score",   "dish_hydration_score",
        "adj_thermogenic_score", "dish_thermogenic_score",
        "adj_warming_score",     "dish_warming_score",
        "adj_cooling_score",     "dish_cooling_score",
        "adj_satiety_score",     "dish_satiety_score",
        "adj_energy_total",      "dish_energy_total",
        "adj_sodium_total",      "dish_sodium_total",
        "adj_glycemic_load",     "dish_glycemic_load",
        "sodium_safety_score",
        "gl_safety_score",
        "gout_risk_score",
        "cost_level",
    ]
    dishes = [dict(zip(cols, r)) for r in rows]
    dish_ingredient_map = _get_dish_ingredient_ids([d["id"] for d in dishes], db)

    allergy_ing_ids = profile.get("allergy_ingredient_ids", set())
    allergy_groups  = set(profile.get("allergy_blacklist", []))
    df              = profile.get("disease_flags", {})

    passed = []
    for d in dishes:
        # ── Prep time ──────────────────────────────────────────────────────
        if hard_ceiling is not None:
            ct = d.get("cook_time_minutes") or 0
            if ct > hard_ceiling:
                continue

        # ── Allergy ingredient ID ──────────────────────────────────────────
        if allergy_ing_ids and (dish_ingredient_map.get(d["id"], set()) & allergy_ing_ids):
            continue

        # ── Allergy group (allergen_summary) ──────────────────────────────
        if allergy_groups:
            try:
                allergens = set(json.loads(d.get("allergen_summary") or "[]"))
            except Exception:
                allergens = set()
            if allergens & allergy_groups:
                continue

        # ── Sodium hard filter (hypertension) ─────────────────────────────
        sodium = d.get("adj_sodium_total") or d.get("dish_sodium_total") or 0
        if sodium and sodium > profile["sodium_limit_mg"]:
            continue

        # ── Glycemic load hard filter (diabetes) ──────────────────────────
        gl = d.get("adj_glycemic_load") or d.get("dish_glycemic_load") or 0
        if gl and gl > profile["glycemic_load_limit"]:
            continue

        # ── Gout hard filter — loại món gout_risk_score quá thấp ──────────
        if df.get("gout"):
            gout_score = d.get("gout_risk_score")
            if gout_score is not None and gout_score < 0.3:
                continue   # risk quá cao → loại hẳn

        # ── Diet type ──────────────────────────────────────────────────────
        if profile["diet_type"] == "vegan" and not d.get("is_vegan"):
            continue
        if profile["diet_type"] == "vegetarian" and not d.get("is_vegetarian"):
            continue

        passed.append(d)
    return passed


# ── STEP 07 — Taste weight ───────────────────────────────────────────────────
def resolve_taste_weight(pv: dict, loc: dict) -> dict:
    if pv.get("has_taste_preference"):
        return pv["taste_weight"]

    regional_flavor = loc.get("regional_flavor")
    if regional_flavor:
        try:
            flavor_dict = (json.loads(regional_flavor)
                           if isinstance(regional_flavor, str)
                           else regional_flavor)
            valid_keys = {"sweet", "sour", "salty", "bitter", "umami", "spicy", "astringent"}
            if any(k in valid_keys for k in flavor_dict):
                result = dict(TASTE_DEFAULTS)
                result.update({k: v for k, v in flavor_dict.items() if k in valid_keys})
                return result
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    return dict(TASTE_DEFAULTS)


# ── STEP 08 — Score ──────────────────────────────────────────────────────────
def _dv(dish, adj, raw=None):
    v = dish.get(adj)
    if v is not None: return float(v)
    if raw:
        v = dish.get(raw)
        if v is not None: return float(v)
    return 0.0


def compute_soft_mult(dish: dict, profile: dict, current_season: str) -> float:
    mult = 1.0
    prep = dish.get("cook_time_minutes") or 0
    if prep > profile["max_prep_time"]:
        excess = (prep - profile["max_prep_time"]) // 5
        mult = max(0.1, mult - 0.1 * excess)

    try:
        sm = json.loads(dish.get("season_suitability") or "{}")
        if sm.get(current_season, 0.5) < 0.4:
            mult *= 0.85
    except Exception:
        pass

    cost_pref = profile.get("cost_preference", 2)
    dish_cost = dish.get("cost_level") or 2
    if cost_pref == 1:
        if dish_cost == 3:   mult *= 0.40
        elif dish_cost == 2: mult *= 0.85
    elif cost_pref == 2:
        if dish_cost == 3:   mult *= 0.75

    return round(mult, 4)


def compute_dish_boost(recipe_id: int, selected_set: set, boost_strategy: str, db) -> float:
    if not selected_set or boost_strategy == "none":
        return 0.0
    rows = db.execute(
        "SELECT ingredient_id FROM dish_ingredient WHERE recipe_id=? AND is_main=1",
        (recipe_id,)
    ).fetchall()
    main_ids = {r[0] for r in rows if r[0]}
    if not main_ids:
        return 0.0
    coverage = len(selected_set & main_ids) / len(main_ids)
    if boost_strategy == "strict":
        return round(coverage, 4) if coverage >= 0.5 else 0.0
    return round(coverage, 4)


def _compute_disease_score(dish: dict, profile: dict) -> float | None:
    """
    Tính disease score tổng hợp từ các pre-computed safety scores trong DB.
    Trả về None nếu user không có bệnh nào.

    Scoring:
      hypertension → sodium_safety_score  (1.0=ít muối, 0.0=nhiều muối)
      diabetes     → gl_safety_score      (1.0=GL thấp, 0.0=GL cao)
      gout         → gout_risk_score      (1.0=an toàn, 0.0=nguy hiểm)

    Fallback khi cột NULL: 0.5 (neutral)
    """
    df = profile.get("disease_flags", {})
    scores = []

    if df.get("hypertension"):
        s = dish.get("sodium_safety_score")
        if s is None:
            # fallback: tính từ adj_sodium_total nếu cột chưa được populate
            sodium = dish.get("adj_sodium_total") or dish.get("dish_sodium_total") or 0
            s = max(0.0, 1.0 - sodium / SODIUM_LIMIT_HYPERTENSION) if sodium else 0.5
        scores.append(float(s))

    if df.get("diabetes"):
        s = dish.get("gl_safety_score")
        if s is None:
            gl = dish.get("adj_glycemic_load") or dish.get("dish_glycemic_load") or 0
            s = max(0.0, 1.0 - gl / GL_LIMIT_DIABETES) if gl else 0.5
        scores.append(float(s))

    if df.get("gout"):
        s = dish.get("gout_risk_score")
        scores.append(float(s) if s is not None else 0.5)

    if not scores:
        return None
    return sum(scores) / len(scores)


def score_dish(dish: dict, demand: dict, soft_mult: float, taste_weight: dict,
               trad_compat: float, dish_avail: float, ingredient_boost: float,
               profile: dict | None = None,
               recent_ids_ordered: list | None = None) -> float:
    """
    Tính điểm cuối cho một món ăn.

    Weight mặc định (không có bệnh):
      65% demand_score + 15% taste_score + 10% loc_bonus + 10% ingredient_boost

    Weight khi có bệnh:
      50% demand_score + 15% disease_score + 15% taste_score + 10% loc_bonus + 10% ingredient_boost
    """
    DIMS = [
        ("hydration_need",        "adj_hydration_score",   "dish_hydration_score"),
        ("electrolyte_need",      "adj_hydration_score",   None),
        ("thermoregulation_need", "adj_thermogenic_score", "dish_thermogenic_score"),
        ("warming_food_need",     "adj_warming_score",     "dish_warming_score"),
        ("cooling_food_need",     "adj_cooling_score",     "dish_cooling_score"),
    ]
    demand_sum = sum(demand.get(d, 0) for d, _, _ in DIMS)
    if demand_sum > 0:
        raw_score = sum(
            demand.get(d, 0) * _dv(dish, a, r) for d, a, r in DIMS
        ) / demand_sum
    else:
        raw_score = 0.0

    # Taste score
    weight_sum = sum(taste_weight.values()) or 1.0
    try:
        tp = json.loads(dish.get("taste_profile") or "{}")
    except Exception:
        tp = {}
    taste_b = sum(taste_weight.get(t, 0) * tp.get(t, 0) for t in taste_weight) / weight_sum

    # Season score cho loc_bonus
    season = get_current_season()
    try:
        sm = json.loads(dish.get("season_suitability") or "{}")
        season_s = sm.get(season, 0.6)
    except Exception:
        season_s = 0.6

    loc_bonus = trad_compat * season_s * dish_avail
    boost     = ingredient_boost if ingredient_boost > 0 else 0.0

    # ── Disease scoring ──────────────────────────────────────────────────────
    disease_score = _compute_disease_score(dish, profile or {})

    if disease_score is not None:
        # Có bệnh: demand nhường 15% cho disease
        final = (
            0.50 * raw_score
            + 0.15 * disease_score
            + 0.15 * taste_b
            + 0.10 * loc_bonus
            + 0.10 * boost
        )
    else:
        # Không có bệnh: weight gốc
        final = (
            0.65 * raw_score
            + 0.15 * taste_b
            + 0.10 * loc_bonus
            + 0.10 * boost
        )

    # Áp soft_mult sau khi tổng hợp
    final *= soft_mult

    # ── Repetition decay ─────────────────────────────────────────────────────
    if recent_ids_ordered:
        dish_id_str = str(dish.get("id", ""))
        REPETITION_DECAY = {0: 0.5, 1: 0.65, 2: 0.8}
        try:
            pos = recent_ids_ordered.index(dish_id_str)
            final *= REPETITION_DECAY.get(pos, 0.85)
        except ValueError:
            pass

    return max(0.0, min(1.0, round(final, 6)))


# ── STEP 09 — Rank + Explain ─────────────────────────────────────────────────
def _serving_hint(dish: dict) -> str:
    w = dish.get("adj_warming_score") or dish.get("dish_warming_score") or 0
    c = dish.get("adj_cooling_score") or dish.get("dish_cooling_score") or 0
    if w and w > 0.7: return "Ăn nóng để phát huy tác dụng giữ ấm"
    if c and c > 0.7: return "Ăn kèm nước dừa tươi hoặc thêm đá"
    return ""


def _fallback_explanation(dish: dict) -> dict:
    return {
        "headline":        dish.get("title", ""),
        "weather_reason":  None,
        "dish_match":      None,
        "nutrition_note":  None,
        "ingredient_note": None,
        "seasonal_note":   None,
        "tags":            [],
    }


def rank_and_explain(scores: dict, dish_pool: list, boosts: dict, demand: dict,
                     profile: dict, top_k: int = 20,
                     loc: dict | None = None, season: str | None = None,
                     basket_ingredient_ids: set | None = None,
                     db=None, temperature=None) -> tuple[list, list]:
    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    dish_map   = {d["id"]: d for d in dish_pool}
    _loc    = loc    or {"traditional_compatibility": 0.8}
    _season = season or get_current_season()
    _basket = basket_ingredient_ids or set()

    result = []
    for rank, did in enumerate(sorted_ids[:top_k], 1):
        dish  = dish_map.get(did, {})
        boost = boosts.get(did, 0.0)

        if db is not None and _HAS_ADVICE_ENGINE:
            try:
                explanation_obj = build_explanation(
                    dish=dish, demand=demand, profile=profile, boost=boost,
                    loc=_loc, season=_season, basket_ingredient_ids=_basket,
                    db=db, temperature=temperature,
                )
                
            except Exception:
                explanation_obj = _fallback_explanation(dish)
        else:
            explanation_obj = _fallback_explanation(dish)

        df = profile.get("disease_flags", {})
        result.append({
            "rank":            rank,
            "dish_id":         did,
            "title":           dish.get("title", ""),
            "image_url":       dish.get("image_url", ""),
            "url":             dish.get("url", ""),
            "nation":          dish.get("nation", ""),
            "final_score":     scores[did],
            "score_breakdown": {
                "hydration":      demand["hydration_need"],
                "warming":        demand["warming_food_need"],
                "cooling":        demand["cooling_food_need"],
                "boost":          boost,
                # Disease scores để debug / hiển thị UI
                "sodium_safety":  dish.get("sodium_safety_score") if df.get("hypertension") else None,
                "gl_safety":      dish.get("gl_safety_score")     if df.get("diabetes")     else None,
                "gout_safety":    dish.get("gout_risk_score")     if df.get("gout")         else None,
            },
            "ingredient_boost":   boost,
            "cook_time_min":      dish.get("cook_time_minutes"),
            "serving_suggestion": _serving_hint(dish),
            "explanation":        explanation_obj,
        })

    return result, sorted_ids[top_k: top_k + 5]


# ── SQL helper — chạy 1 lần để populate các safety score columns ─────────────
POPULATE_SAFETY_SCORES_SQL = """
-- 1. Thêm các cột nếu chưa có
ALTER TABLE dishes ADD COLUMN IF NOT EXISTS sodium_safety_score REAL DEFAULT NULL;
ALTER TABLE dishes ADD COLUMN IF NOT EXISTS gl_safety_score     REAL DEFAULT NULL;
ALTER TABLE dishes ADD COLUMN IF NOT EXISTS gout_risk_score     REAL DEFAULT NULL;

-- 2. sodium_safety_score (hypertension)
UPDATE dishes
SET sodium_safety_score = MAX(0.0, 1.0 - (
    COALESCE(adj_sodium_total, dish_sodium_total, 0) / 600.0
));

-- 3. gl_safety_score (diabetes)
UPDATE dishes
SET gl_safety_score = MAX(0.0, 1.0 - (
    COALESCE(adj_glycemic_load, dish_glycemic_load, 0) / 10.0
));

-- 4. gout_risk_score — weighted purine risk từ nguyên liệu chính
UPDATE dishes
SET gout_risk_score = (
    SELECT ROUND(MAX(0.0, 1.0 - SUM(
        CASE
            WHEN i.category = 'Hải sản'     AND i.source_type = 'aquatic_coast'  THEN 1.0
            WHEN i.category = 'Hải sản'     AND i.source_type = 'processed'      THEN 0.7
            WHEN i.category = 'Thịt'        AND i.source_type = 'livestock'      THEN 0.7
            WHEN i.category = 'Thịt'        AND i.source_type = 'processed'      THEN 0.6
            WHEN i.category = 'Hải sản'     AND i.source_type = 'aquatic_inland' THEN 0.4
            WHEN i.category = 'Thịt'        AND i.source_type = 'aquatic_inland' THEN 0.4
            WHEN i.category = 'Đã chế biến' AND i.source_type = 'processed'      THEN 0.3
            WHEN i.category = 'Đậu & Hạt'  AND i.source_type IN ('farm_local','processed') THEN 0.2
            ELSE 0.0
        END * (di.quantity_g / total.total_g)
    )), 4)
    FROM dish_ingredient di
    JOIN ingredients i ON di.ingredient_id = i.id
    JOIN (
        SELECT recipe_id, SUM(quantity_g) AS total_g
        FROM dish_ingredient
        WHERE is_main = 1 AND quantity_g > 0
        GROUP BY recipe_id
    ) total ON di.recipe_id = total.recipe_id
    WHERE di.recipe_id = dishes.id
      AND di.is_main   = 1
      AND di.quantity_g > 0
)
WHERE id IN (SELECT DISTINCT recipe_id FROM dish_ingredient);
"""