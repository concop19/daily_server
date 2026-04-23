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
    "sedentary":        1.2,
    "lightly_active":   1.375,
    "moderately_active":1.55,
    "very_active":      1.725,
}

TASTE_DEFAULTS = {
    "spicy": 0.5, "sweet": 0.5, "sour": 0.4,
    "umami": 0.6, "salty": 0.4, "bitter": 0.2, "astringent": 0.1,
}

ALLERGY_CATEGORY_MAP: dict[str, set[str]] = {
    "seafood": {"seafood", "marine invertebrates", "aquatic vegetables", "halophytes", "seaweed"},
    "dairy":   {"dairy", "dairy/poultry"},
    "nut":     {"nut_seed"},
    "gluten":  {"grain", "grains", "processed", "processed meat"},
    "egg":     {"egg", "dairy/poultry"},
    "soy":     {"soy products", "legume"},
    "meat":    {"meat", "processed meat", "protein"},
    "pork":    {"meat", "processed meat"},
}

CLIMATE_MODIFIER = {
    "tropical":         {"warming": 0.8, "cooling": 1.2, "hydration": 1.1},
    "subtropical":      {"warming": 1.2, "cooling": 0.8, "hydration": 0.9},
    "tropical_monsoon": {"warming": 0.9, "cooling": 1.1, "hydration": 1.2},
    "highland":         {"warming": 1.3, "cooling": 0.7, "hydration": 0.9},
    "temperate":        {"warming": 1.1, "cooling": 0.9, "hydration": 1.0},
}


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
            "province":                 closest["province_name"],
            "food_region":              closest["food_region"],
            "climate_type":             closest["climate_type"] or "tropical",
            "regional_flavor":          closest["regional_flavor"] or "",
            "cuisine_culture":          closest["cuisine_culture"] or "",
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
        "glycemic_control_need": 1.0 if df.get("diabetes")     else 0.0,
        "sodium_control_need":   1.0 if df.get("hypertension") else 0.0,
        "warming_food_need":     round(w,  4),
        "cooling_food_need":     round(c,  4),
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
    df = pv["disease_flags"]
    raw_allergies = pv.get("allergies", [])
    allergy_categories = [x for x in raw_allergies if isinstance(x, str) and not x.isdigit()]

    return {
        "allergy_blacklist":      allergy_categories,
        "allergy_ingredient_ids": resolve_allergy_ingredient_ids(raw_allergies, db),
        "diet_type":              pv.get("diet_type", "omnivore"),
        "sodium_limit_mg":        600.0  if df.get("hypertension") else 1500.0,
        "glycemic_load_limit":    10.0   if df.get("diabetes")     else 25.0,
        "calorie_target":         round(pv["energy_need"] * 0.35, 0),
        "max_prep_time":          pv.get("max_prep_time", 60),
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
    max_time = profile.get("max_prep_time", 60)
    hard_ceiling = None if max_time >= 999 else max_time + 10

    if cuisine_scope == "vietnam":
        nation_sql, nation_params = "AND LOWER(d.nation) = 'vietnam'", {}
    elif cuisine_scope == "specific_nation" and selected_nation:
        nation_sql, nation_params = "AND d.nation = :nation", {"nation": selected_nation}
    else:
        nation_sql, nation_params = "", {}

    if dish_type_filter == "soup":
        type_sql = "AND cm.method_name = 'nau_canh'"
    elif dish_type_filter == "main_dish":
        type_sql = "AND (cm.method_name IS NULL OR cm.method_name != 'nau_canh')"
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
               d.adj_glycemic_load,     d.dish_glycemic_load
        FROM dishes d
        LEFT JOIN cooking_methods cm ON d.cooking_method_id = cm.method_id
        WHERE 1=1 {nation_sql} {type_sql} LIMIT 2000
    """
    rows = db.execute(sql, nation_params).fetchall()
    cols = [
        "id", "title", "nation", "cook_time_minutes", "cooking_method_id", "image_url", "url",
        "is_vegan", "is_vegetarian", "allergen_summary", "taste_profile",
        "season_suitability", "total_weight_g",
        "adj_hydration_score", "dish_hydration_score",
        "adj_thermogenic_score", "dish_thermogenic_score",
        "adj_warming_score", "dish_warming_score",
        "adj_cooling_score", "dish_cooling_score",
        "adj_satiety_score", "dish_satiety_score",
        "adj_energy_total", "dish_energy_total",
        "adj_sodium_total", "dish_sodium_total",
        "adj_glycemic_load", "dish_glycemic_load",
    ]
    dishes = [dict(zip(cols, r)) for r in rows]
    dish_ingredient_map = _get_dish_ingredient_ids([d["id"] for d in dishes], db)

    allergy_ing_ids = profile.get("allergy_ingredient_ids", set())
    allergy_groups  = set(profile.get("allergy_blacklist", []))

    passed = []
    for d in dishes:
        if hard_ceiling is not None:
            ct = d.get("cook_time_minutes") or 0
            if ct > hard_ceiling:
                continue
        if allergy_ing_ids and (dish_ingredient_map.get(d["id"], set()) & allergy_ing_ids):
            continue
        if allergy_groups:
            try:
                allergens = set(json.loads(d.get("allergen_summary") or "[]"))
            except Exception:
                allergens = set()
            if allergens & allergy_groups:
                continue
        sodium = d.get("adj_sodium_total") or d.get("dish_sodium_total") or 0
        if sodium and sodium > profile["sodium_limit_mg"]:
            continue
        gl = d.get("adj_glycemic_load") or d.get("dish_glycemic_load") or 0
        if gl and gl > profile["glycemic_load_limit"]:
            continue
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


def score_dish(dish: dict, demand: dict, soft_mult: float, taste_weight: dict,
               trad_compat: float, dish_avail: float, ingredient_boost: float,
               recent_ids_ordered: list | None = None) -> float:
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
            demand.get(d, 0) * _dv(dish, a, r) * soft_mult for d, a, r in DIMS
        ) / demand_sum
    else:
        raw_score = 0.0

    season = get_current_season()
    try:
        sm = json.loads(dish.get("season_suitability") or "{}")
        season_s = sm.get(season, 0.6)
    except Exception:
        season_s = 0.6

    weight_sum = sum(taste_weight.values()) or 1.0
    try:
        tp = json.loads(dish.get("taste_profile") or "{}")
    except Exception:
        tp = {}
    taste_b = sum(taste_weight.get(t, 0) * tp.get(t, 0) for t in taste_weight) / weight_sum

    loc_bonus = trad_compat * season_s * dish_avail
    boost = ingredient_boost if ingredient_boost > 0 else 0.0
    final = (0.65 * raw_score + 0.15 * taste_b + 0.10 * loc_bonus + 0.10 * boost)

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

        result.append({
            "rank":            rank,
            "dish_id":         did,
            "title":           dish.get("title", ""),
            "image_url":       dish.get("image_url", ""),
            "url":             dish.get("url", ""),
            "nation":          dish.get("nation", ""),
            "final_score":     scores[did],
            "score_breakdown": {
                "hydration": demand["hydration_need"],
                "warming":   demand["warming_food_need"],
                "cooling":   demand["cooling_food_need"],
                "boost":     boost,
            },
            "ingredient_boost":   boost,
            "cook_time_min":      dish.get("cook_time_minutes"),
            "serving_suggestion": _serving_hint(dish),
            "explanation":        explanation_obj,
        })

    return result, sorted_ids[top_k: top_k + 5]