import sqlite3, json, math, os, sys
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from advice_engine import build_explanation, legacy_explain_list
DB_PATH = Path(os.environ.get("DB_PATH", r"D:\dream_project\daily_mate_code\daily_mate_all\demo_server\recipe.db"))
app = Flask(__name__)
CORS(app)

# ── DB ───────────────────────────────────────────────────────────────────────
def get_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# ── STEP 01 — Weather ────────────────────────────────────────────────────────
_WEATHER_CACHE: dict = {}
CELL_SIZE = 0.1
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# Condition code → mô tả tiếng Việt ngắn gọn (từ OW icon/description)
_OW_CONDITION_VI = {
    "thunderstorm": "Giông bão", "drizzle": "Mưa phùn", "rain": "Mưa",
    "snow": "Tuyết", "mist": "Sương mù", "fog": "Sương dày",
    "haze": "Mờ sương", "clear": "Trời quang", "clouds": "Có mây",
}

def _grid_key(lat: float, lon: float):
    g_lat = round(round(lat / CELL_SIZE) * CELL_SIZE, 1)
    g_lon = round(round(lon / CELL_SIZE) * CELL_SIZE, 1)
    return f"{g_lat}:{g_lon}", g_lat, g_lon

def _adaptive_ttl(temperature, aqi, wind_speed) -> int:
    """Trả về TTL tính bằng phút. Thời tiết cực đoan → TTL ngắn hơn."""
    hour = datetime.now().hour
    base = 30 if (6 <= hour < 22) else 60
    if aqi and aqi > 150:       base = min(base, 15)
    if wind_speed and wind_speed > 50: base = min(base, 15)
    if temperature and temperature > 40: base = min(base, 20)
    return base

def _ensure_weather_cache_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS weather_cache (
            grid_key     TEXT PRIMARY KEY,
            grid_lat     REAL NOT NULL,
            grid_lon     REAL NOT NULL,
            cell_size    REAL NOT NULL DEFAULT 0.1,
            weather_vector TEXT NOT NULL,
            raw_data     TEXT,
            temperature  REAL,
            aqi          REAL,
            wind_speed   REAL,
            condition    TEXT,
            fetched_at   TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            hit_count    INTEGER DEFAULT 0,
            source_api   TEXT DEFAULT 'openweathermap'
        )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_weather_expires ON weather_cache(expires_at)"
    )
    db.commit()

def _ow_condition_vi(raw: dict) -> str:
    """Lấy mô tả điều kiện thời tiết ngắn gọn bằng tiếng Việt."""
    try:
        main = raw["weather"][0]["main"].lower()
        return _OW_CONDITION_VI.get(main, raw["weather"][0]["description"].capitalize())
    except Exception:
        return "Không rõ"

def fetch_from_openweather(lat: float, lon: float) -> tuple:
    """Gọi OpenWeather + Air Pollution API. Trả (raw, wv, flat_fields)."""
    if not OPENWEATHER_API_KEY:
        raise ValueError("OPENWEATHER_API_KEY chưa được set")

    # --- Current weather ---
    ow_resp = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"},
        timeout=6,
    )
    ow_resp.raise_for_status()
    raw = ow_resp.json()

    temp     = float(raw["main"]["temp"])
    humidity = float(raw["main"]["humidity"])
    wind_ms  = float(raw["wind"].get("speed", 0))
    wind_kmh = round(wind_ms * 3.6, 1)
    pressure = float(raw["main"]["pressure"])
    uv_index = 0.0                           # OW free tier không có UV trong endpoint này

    # --- Air Pollution (miễn phí, cùng key) ---
    aqi_val = 50.0
    try:
        ap_resp = requests.get(
            "https://api.openweathermap.org/data/2.5/air_pollution",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
            timeout=5,
        )
        if ap_resp.ok:
            aqi_index = ap_resp.json()["list"][0]["main"]["aqi"]  # 1-5 scale
            aqi_val = float({1: 25, 2: 60, 3: 100, 4: 160, 5: 220}.get(aqi_index, 50))
    except Exception:
        pass

    season = _get_current_season()
    wv = compute_weather_vector(temp, humidity, wind_kmh, pressure, aqi_val, uv_index, season)

    condition_vi = _ow_condition_vi(raw)

    flat = {
        "temperature": round(temp, 1),
        "humidity":    round(humidity, 1),
        "wind_speed":  wind_kmh,
        "pressure":    round(pressure, 1),
        "aqi":         round(aqi_val, 1),
        "uv_index":    uv_index,
        "season":      season,
        "condition":   condition_vi,
    }
    return raw, wv, flat, aqi_val, wind_kmh

def _norm(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))

def compute_weather_vector(t, humidity, wind, pressure, aqi, uv, season):
    tn   = _norm(t,        10.0, 42.0)
    hn   = _norm(humidity, 20.0, 100.0)
    wn   = _norm(wind,     0.0,  80.0)
    aqin = _norm(aqi,      0.0,  300.0)
    uvn  = _norm(uv,       0.0,  11.0)
    pn   = _norm(pressure, 980.0, 1020.0)

    heat_stress = min(1.0, 0.6*tn + 0.4*hn)
    cold_stress = min(1.0, max(0.0, 1.0-tn)*0.7 + wn*0.3)
    dehydration = min(1.0, 0.5*heat_stress + 0.3*wn + 0.2*aqin)
    season_ox   = 0.8 if season == "summer" else 0.3
    oxidative   = min(1.0, 0.4*uvn + 0.3*aqin + 0.3*season_ox)
    infection   = min(1.0, 0.4*(1-pn) + 0.6*aqin)
    season_im   = 0.8 if season in ("spring","autumn") else 0.2
    immune_load = min(1.0, 0.4*aqin + 0.3*infection + 0.3*season_im)

    return {
        "heat_stress_index":     round(heat_stress, 4),
        "dehydration_risk":      round(dehydration, 4),
        "cold_stress_index":     round(cold_stress, 4),
        "oxidative_stress_risk": round(oxidative,   4),
        "infection_risk":        round(infection,   4),
        "immune_load":           round(immune_load, 4),
    }

def get_or_compute_weather(lat, lon, weather_override: dict | None) -> dict:
    # Nếu client truyền lên weather_vector sẵn (từ /api/weather response), dùng thẳng
    if weather_override and "weather_vector" in weather_override:
        return weather_override["weather_vector"]

    key, g_lat, g_lon = _grid_key(lat, lon)

    # Client truyền raw fields thủ công (override không có weather_vector)
    if weather_override:
        wv = compute_weather_vector(
            weather_override.get("temperature", 30),
            weather_override.get("humidity",    70),
            weather_override.get("wind_speed",  10),
            weather_override.get("pressure",    1010),
            weather_override.get("aqi",         50),
            weather_override.get("uv_index",    6),
            weather_override.get("season",      _get_current_season()),
        )
        _WEATHER_CACHE[key] = wv
        return wv

    # In-memory cache (process lifetime)
    if key in _WEATHER_CACHE:
        return _WEATHER_CACHE[key]

    # DB cache
    try:
        db = get_db()
        _ensure_weather_cache_table(db)
        now = datetime.now(timezone.utc)
        row = db.execute(
            "SELECT weather_vector, expires_at FROM weather_cache WHERE grid_key = ?",
            (key,)
        ).fetchone()
        if row:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now < exp:
                wv = json.loads(row["weather_vector"])
                _WEATHER_CACHE[key] = wv
                db.execute("UPDATE weather_cache SET hit_count = hit_count + 1 WHERE grid_key = ?", (key,))
                db.commit()
                db.close()
                return wv
        db.close()
    except Exception:
        pass

    # Hardcoded fallback (khi không có API key hoặc DB lỗi)
    wv = compute_weather_vector(33, 75, 12, 1008, 80, 7.5, _get_current_season())
    _WEATHER_CACHE[key] = wv
    return wv

# ── STEP 02 — Location ───────────────────────────────────────────────────────
def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def resolve_location(lat, lon, db) -> dict:
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
            "province":                closest["province_name"],
            "food_region":             closest["food_region"],
            "climate_type":            closest["climate_type"] or "tropical",
            "regional_flavor":         closest["regional_flavor"] or "",
            "cuisine_culture":         closest["cuisine_culture"] or "",
            "traditional_compatibility": 0.9,
        }
    return {
        "province": "Unknown", "food_region": "mien_nam",
        "climate_type": "tropical", "regional_flavor": "", "cuisine_culture": "",
        "traditional_compatibility": 0.7,
    }

def get_dish_availability(recipe_id, food_region, db) -> float:
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

# ── STEP 03 — Personal ───────────────────────────────────────────────────────
ACTIVITY_MULT = {
    "sedentary": 1.2, "lightly_active": 1.375,
    "moderately_active": 1.55, "very_active": 1.725,
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

def compute_personal_vector(p: dict) -> dict:
    age    = p.get("age", 28)
    gender = p.get("gender", "female")
    height = p.get("height", 160.0)
    weight = p.get("weight", 55.0)
    h_m    = height / 100
    bmi    = round(weight / (h_m**2), 2)
    bmr    = (10*weight + 6.25*height - 5*age + 5
              if gender == "male"
              else 10*weight + 6.25*height - 5*age - 161)
    mult   = ACTIVITY_MULT.get(p.get("activity_level", "moderately_active"), 1.55)
    tdee   = round(bmr * mult, 2)

    health = p.get("health_condition", [])
    disease_flags = {
        "hypertension": "hypertension" in health,
        "diabetes":     "diabetes" in health,
        "gout":         "gout" in health,
        "ibs":          "ibs" in health,
    }
    raw_prefs    = p.get("taste_preference", [])
    taste_weight = dict(TASTE_DEFAULTS)
    for t in raw_prefs:
        if t in taste_weight:
            taste_weight[t] = min(1.0, taste_weight[t] + 0.3)
    return {
        "BMI": bmi, "bmr": round(bmr, 2),
        "activity_level_mult":  mult,
        "energy_need":          tdee,
        "disease_flags":        disease_flags,
        "taste_weight":         taste_weight,
        "has_taste_preference": len(raw_prefs) > 0,
        "diet_type":     p.get("diet_type", "omnivore"),
        "allergies":     p.get("allergies", []),
        "max_prep_time": int(p.get("max_prep_time", 60)),   # F02
    }

# ── STEP 04 — Demand ─────────────────────────────────────────────────────────
CLIMATE_MODIFIER = {
    "tropical":         {"warming":0.8, "cooling":1.2, "hydration":1.1},
    "subtropical":      {"warming":1.2, "cooling":0.8, "hydration":0.9},
    "tropical_monsoon": {"warming":0.9, "cooling":1.1, "hydration":1.2},
    "highland":         {"warming":1.3, "cooling":0.7, "hydration":0.9},
    "temperate":        {"warming":1.1, "cooling":0.9, "hydration":1.0},
}

def compute_demand(wv: dict, pv: dict, climate_type: str) -> dict:
    act_n = (pv["activity_level_mult"] - 1.2) / (1.9 - 1.2)
    h  = min(1.0, 0.5*wv["dehydration_risk"] + 0.3*wv["heat_stress_index"] + 0.2*act_n)
    e  = min(1.0, 0.6*h + 0.4*act_n)
    th = max(wv["heat_stress_index"], wv["cold_stress_index"])
    en = pv["energy_need"] * (1 - 0.1*wv["heat_stress_index"] + 0.1*wv["cold_stress_index"])
    w  = min(1.0, 0.6*wv["cold_stress_index"] + 0.4*(1 - wv["heat_stress_index"]))
    c  = min(1.0, 0.6*wv["heat_stress_index"] + 0.4*(1 - wv["cold_stress_index"]))
    mod = CLIMATE_MODIFIER.get(climate_type, {"warming":1.0,"cooling":1.0,"hydration":1.0})
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

# ── STEP 05 — Constraint + Allergy ──────────────────────────────────────────
def resolve_allergy_ingredient_ids(allergies: list, db) -> set[int]:
    if not allergies:
        return set()

    # Tách riêng ID (int hoặc chuỗi số) và Category (chuỗi chữ)
    explicit_ids = {int(x) for x in allergies if isinstance(x, int) or (isinstance(x, str) and x.isdigit())}
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

    # Gộp chung ID truyền vào trực tiếp và ID tra cứu được từ DB
    return explicit_ids | db_ids

def build_constraint_profile(pv: dict, db) -> dict:
    df = pv["disease_flags"]
    raw_allergies = pv.get("allergies", [])

    # Chỉ giữ lại các category (kiểu chuỗi) cho vòng check dự phòng
    allergy_categories = [x for x in raw_allergies if isinstance(x, str) and not x.isdigit()]

    return {
        "allergy_blacklist":      allergy_categories,
        "allergy_ingredient_ids": resolve_allergy_ingredient_ids(raw_allergies, db),
        "diet_type":              pv.get("diet_type", "omnivore"),
        "sodium_limit_mg":        600.0 if df.get("hypertension") else 1500.0,
        "glycemic_load_limit":    10.0  if df.get("diabetes")     else 25.0,
        "calorie_target":         round(pv["energy_need"] * 0.35, 0),
        "max_prep_time":          pv.get("max_prep_time", 60),   # F02: từ personal payload
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

def filter_dishes(db, cuisine_scope, selected_nation, profile, current_season,
                  dish_type_filter: str = "all") -> list[dict]:
    # F10: hard time ceiling = max_prep_time + 10 phút (999 = không giới hạn)
    max_time    = profile.get("max_prep_time", 60)
    hard_ceiling = None if max_time >= 999 else max_time + 10
    if cuisine_scope == "vietnam":
        nation_sql, nation_params = "AND LOWER(d.nation) = 'vietnam'", {}
    elif cuisine_scope == "specific_nation" and selected_nation:
        nation_sql, nation_params = "AND d.nation = :nation", {"nation": selected_nation}
    else:
        nation_sql, nation_params = "", {}

    # ── Dish type filter (soup / main_dish / all) ───────────────────────────
    if dish_type_filter == "soup":
        type_sql = "AND cm.method_name = 'nau_canh'"
    elif dish_type_filter == "main_dish":
        type_sql = "AND (cm.method_name IS NULL OR cm.method_name != 'nau_canh')"
    else:
        type_sql = ""

    sql = f"""
        SELECT d.id, d.title, d.nation, d.cook_time_minutes, d.cooking_method_id,d.image_url,d.url,
               d.is_vegan, d.is_vegetarian, d.allergen_summary,
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
        "id","title","nation","cook_time_minutes","cooking_method_id","image_url","url",
        "is_vegan","is_vegetarian","allergen_summary","taste_profile",
        "season_suitability","total_weight_g",
        "adj_hydration_score","dish_hydration_score",
        "adj_thermogenic_score","dish_thermogenic_score",
        "adj_warming_score","dish_warming_score",
        "adj_cooling_score","dish_cooling_score",
        "adj_satiety_score","dish_satiety_score",
        "adj_energy_total","dish_energy_total",
        "adj_sodium_total","dish_sodium_total",
        "adj_glycemic_load","dish_glycemic_load",
    ]
    dishes = [dict(zip(cols, r)) for r in rows]
    dish_ingredient_map = _get_dish_ingredient_ids([d["id"] for d in dishes], db)

    allergy_ing_ids = profile.get("allergy_ingredient_ids", set())
    allergy_groups  = set(profile.get("allergy_blacklist", []))

    passed = []
    for d in dishes:
        # F10: hard ceiling — loại cứng món vượt quá max_prep_time + 10p
        if hard_ceiling is not None:
            ct = d.get("cook_time_minutes") or 0
            if ct > hard_ceiling:
                continue

        if allergy_ing_ids and (dish_ingredient_map.get(d["id"], set()) & allergy_ing_ids):
            continue

        # 2. Chặn dự phòng dựa trên allergen_summary của món (không dùng khối else nữa)
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
    """User pref → regional_flavor JSON dict → TASTE_DEFAULTS."""
    if pv.get("has_taste_preference"):
        return pv["taste_weight"]

    regional_flavor = loc.get("regional_flavor")
    if regional_flavor:
        try:
            flavor_dict = (json.loads(regional_flavor)
                           if isinstance(regional_flavor, str)
                           else regional_flavor)
            valid_keys = {"sweet","sour","salty","bitter","umami","spicy","astringent"}
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

def compute_soft_mult(dish, profile, current_season) -> float:
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

    # F03: cost_preference penalty
    # cost_pref=1 (tiết kiệm): penalty món đắt (cost_level=3)
    # cost_pref=2 (vừa phải):  penalty nhẹ món đắt
    # cost_pref=3 (thoải mái): không penalty
    # NULL cost_level → mặc định về 2, không bị penalty
    cost_pref = profile.get("cost_preference", 2)
    dish_cost = dish.get("cost_level") or 2   # NULL → 2

    if cost_pref == 1:
        if dish_cost == 3:
            mult *= 0.4   # penalty mạnh món đắt
        elif dish_cost == 2:
            mult *= 0.85  # penalty nhẹ món trung bình
        # dish_cost == 1 → không penalty
    elif cost_pref == 2:
        if dish_cost == 3:
            mult *= 0.75  # penalty nhẹ món đắt
        # dish_cost <= 2 → không penalty
    # cost_pref == 3 → không penalty bất kỳ món nào

    return round(mult, 4)

def compute_taste_bonus(dish, taste_weight) -> float:
    try:
        tp = json.loads(dish.get("taste_profile") or "{}")
    except Exception:
        tp = {}
    return sum(taste_weight.get(t, 0) * tp.get(t, 0) for t in taste_weight)

def compute_dish_boost(recipe_id, selected_set, boost_strategy, db) -> float:
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
def score_dish(dish, demand, soft_mult, taste_weight, trad_compat,
               dish_avail, ingredient_boost,
               recent_ids_ordered: list | None = None) -> float:
    DIMS = [
        ("hydration_need",        "adj_hydration_score",   "dish_hydration_score"),
        ("electrolyte_need",      "adj_hydration_score",   None),
        ("thermoregulation_need", "adj_thermogenic_score", "dish_thermogenic_score"),
        ("warming_food_need",     "adj_warming_score",     "dish_warming_score"),
        ("cooling_food_need",     "adj_cooling_score",     "dish_cooling_score"),
    ]

    # FIX 1: chuẩn hoá raw_score — chia cho tổng demand thay vì để là tổng thô
    demand_sum = sum(demand.get(d, 0) for d, _, _ in DIMS)
    if demand_sum > 0:
        raw_score = sum(
            demand.get(d, 0) * _dv(dish, a, r) * soft_mult
            for d, a, r in DIMS
        ) / demand_sum          # → luôn trong [0, 1]
    else:
        raw_score = 0.0

    season = _get_current_season()
    try:
        sm = json.loads(dish.get("season_suitability") or "{}")
        season_s = sm.get(season, 0.6)
    except Exception:
        season_s = 0.6

    # FIX 2: chuẩn hoá taste_bonus — dùng trung bình có trọng số thay vì tổng
    taste_keys = list(taste_weight.keys())
    weight_sum = sum(taste_weight.values()) or 1.0
    try:
        tp = json.loads(dish.get("taste_profile") or "{}")
    except Exception:
        tp = {}
    taste_b = sum(taste_weight.get(t, 0) * tp.get(t, 0) for t in taste_keys) / weight_sum
    # → luôn trong [0, 1]

    loc_bonus = trad_compat * season_s * dish_avail  # đã trong [0, 1]

    boost = ingredient_boost if ingredient_boost > 0 else 0.0
    final = (0.65 * raw_score
           + 0.15 * taste_b
           + 0.10 * loc_bonus
           + 0.10 * boost)

    # F04: Anti-repetition penalty
    if recent_ids_ordered:
        dish_id_str = str(dish.get("id", ""))
        REPETITION_DECAY = {0: 0.5, 1: 0.65, 2: 0.8}
        try:
            pos = recent_ids_ordered.index(dish_id_str)
            penalty = REPETITION_DECAY.get(pos, 0.85)
            final *= penalty
        except ValueError:
            pass  # món không trong danh sách recent → không penalty

    return max(0.0, min(1.0, round(final, 6)))

# ── STEP 09 — Rank + Explain ─────────────────────────────────────────────────
def rank_and_explain(scores, dish_pool, boosts, demand, profile, top_k=20,
                     loc=None, season=None, basket_ingredient_ids=None,
                     db=None, temperature=None):
    """
    F06: explanation nâng cấp — gọi build_explanation() từ advice_engine.
    Các tham số mới (loc, season, basket_ingredient_ids, db, temperature)
    là optional để tương thích ngược.
    """
    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    dish_map   = {d["id"]: d for d in dish_pool}
    _loc    = loc    or {"traditional_compatibility": 0.8}
    _season = season or _get_current_season()
    _basket = basket_ingredient_ids or set()

    result = []
    for rank, did in enumerate(sorted_ids[:top_k], 1):
        dish  = dish_map.get(did, {})
        boost = boosts.get(did, 0.0)

        # F06: build rich explanation
        if db is not None:
            try:
                explanation_obj = build_explanation(
                    dish=dish,
                    demand=demand,
                    profile=profile,
                    boost=boost,
                    loc=_loc,
                    season=_season,
                    basket_ingredient_ids=_basket,
                    db=db,
                    temperature=temperature,
                )
            except Exception:
                # Fallback về legacy nếu advice_engine gặp lỗi bất ngờ
                explanation_obj = {
                    "headline":        dish.get("title", ""),
                    "weather_reason":  None,
                    "dish_match":      None,
                    "nutrition_note":  None,
                    "ingredient_note": None,
                    "seasonal_note":   None,
                    "tags":            [],
                }
        else:
            explanation_obj = {
                "headline":        dish.get("title", ""),
                "weather_reason":  None,
                "dish_match":      None,
                "nutrition_note":  None,
                "ingredient_note": None,
                "seasonal_note":   None,
                "tags":            [],
            }

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
            "explanation":        explanation_obj,     # F06: dict thay vì list[str]
        })
    return result, sorted_ids[top_k:top_k+5]

def _serving_hint(dish) -> str:
    w = dish.get("adj_warming_score") or dish.get("dish_warming_score") or 0
    c = dish.get("adj_cooling_score") or dish.get("dish_cooling_score") or 0
    if w and w > 0.7: return "Ăn nóng để phát huy tác dụng giữ ấm"
    if c and c > 0.7: return "Ăn kèm nước dừa tươi hoặc thêm đá"
    return ""

def _explain(dish, demand, profile, boost) -> list[str]:
    parts = []
    top = sorted(
        [("hydration", demand["hydration_need"]),
         ("warming",   demand["warming_food_need"]),
         ("cooling",   demand["cooling_food_need"])],
        key=lambda x: x[1], reverse=True
    )
    ctx = {
        "hydration": "Hôm nay nắng nóng, cơ thể dễ mất nước.",
        "warming":   "Thời tiết lạnh — bữa ăn ấm nóng sẽ giúp bạn cảm thấy dễ chịu hơn.",
        "cooling":   "Nhiệt độ cao hôm nay, món mát giúp hạ nhiệt hiệu quả.",
    }
    dish_tpl = {
        "hydration": "{n} có hàm lượng nước cao, bù đắp lượng nước cơ thể đang thiếu.",
        "warming":   "{n} có tính ấm, phù hợp giữ nhiệt trong thời tiết này.",
        "cooling":   "{n} có tính mát, giúp làm dịu cơ thể.",
    }
    if top:
        dim0 = top[0][0]
        parts.append(ctx.get(dim0, ""))
        parts.append(dish_tpl.get(dim0, "").format(n=dish.get("title", "Món này")))
    if profile.get("diet_type") == "vegan":
        parts.append("Không chứa nguyên liệu động vật.")
    if boost > 0:
        parts.append(f"Có {int(boost*100)}% nguyên liệu bạn đã mua hôm nay.")
    return [p for p in parts if p][:4]

# ── Helpers ──────────────────────────────────────────────────────────────────
def _get_current_season() -> str:
    m = datetime.now().month
    if m in (12,1,2): return "winter"
    if m in (3,4,5):  return "spring"
    if m in (6,7,8):  return "summer"
    return "autumn"

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/api/weather")
def get_weather():
    """
    GET /api/weather?lat=16.047&lon=108.206
    Trả flat object chứa raw weather fields + weather_vector + cache meta.
    Client (HomeScreen) đọc: .temperature .humidity .wind_speed .aqi .condition .weather_vector
    """
    lat = float(request.args.get("lat", 16.047))
    lon = float(request.args.get("lon", 108.206))
    key, g_lat, g_lon = _grid_key(lat, lon)

    db  = get_db()
    _ensure_weather_cache_table(db)
    now = datetime.now(timezone.utc)

    # --- DB cache check ---
    row = db.execute(
        "SELECT weather_vector, raw_data, temperature, aqi, wind_speed, condition, expires_at, hit_count "
        "FROM weather_cache WHERE grid_key = ?", (key,)
    ).fetchone()

    if row:
        exp = datetime.fromisoformat(row["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now < exp:
            db.execute("UPDATE weather_cache SET hit_count = hit_count + 1 WHERE grid_key = ?", (key,))
            db.commit()
            wv = json.loads(row["weather_vector"])
            _WEATHER_CACHE[key] = wv
            # Khôi phục flat fields từ raw_data đã lưu
            raw_saved = json.loads(row["raw_data"] or "{}")
            flat = {
                "temperature": row["temperature"] or 30.0,
                "humidity":    float(raw_saved.get("main", {}).get("humidity", 70)),
                "wind_speed":  row["wind_speed"] or 10.0,
                "pressure":    float(raw_saved.get("main", {}).get("pressure", 1010)),
                "aqi":         row["aqi"] or 50.0,
                "uv_index":    0.0,
                "season":      _get_current_season(),
                "condition":   row["condition"] or "Không rõ",
            }
            db.close()
            return jsonify({**flat, "weather_vector": wv,
                            "cache_hit": True, "expires_at": row["expires_at"]})

    # --- Cache miss → gọi OpenWeather ---
    try:
        raw, wv, flat, aqi_val, wind_kmh = fetch_from_openweather(g_lat, g_lon)
        ttl      = _adaptive_ttl(flat["temperature"], aqi_val, wind_kmh)
        expires  = (now + timedelta(minutes=ttl)).isoformat()

        db.execute("""
            INSERT OR REPLACE INTO weather_cache
            (grid_key, grid_lat, grid_lon, cell_size, weather_vector, raw_data,
             temperature, aqi, wind_speed, condition, fetched_at, expires_at, hit_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)
        """, (key, g_lat, g_lon, CELL_SIZE,
              json.dumps(wv), json.dumps(raw),
              flat["temperature"], aqi_val, wind_kmh, flat["condition"],
              now.isoformat(), expires))
        db.commit()
        db.close()
        _WEATHER_CACHE[key] = wv
        return jsonify({**flat, "weather_vector": wv, "cache_hit": False, "expires_at": expires})

    except Exception as e:
        # Fallback: dùng row DB cũ dù hết hạn, hoặc hardcode
        if row:
            wv  = json.loads(row["weather_vector"])
            raw_saved = json.loads(row["raw_data"] or "{}")
            flat = {
                "temperature": row["temperature"] or 30.0,
                "humidity":    float(raw_saved.get("main", {}).get("humidity", 70)),
                "wind_speed":  row["wind_speed"] or 10.0,
                "pressure":    float(raw_saved.get("main", {}).get("pressure", 1010)),
                "aqi":         row["aqi"] or 50.0,
                "uv_index":    0.0,
                "season":      _get_current_season(),
                "condition":   row["condition"] or "Không rõ",
            }
            db.close()
            return jsonify({**flat, "weather_vector": wv,
                            "cache_hit": True, "expires_at": row["expires_at"],
                            "warning": f"OpenWeather lỗi, dùng cache cũ: {e}"})
        db.close()
        # Absolute fallback: hardcoded hanoi summer
        season = _get_current_season()
        wv = compute_weather_vector(33, 75, 12, 1008, 80, 7.5, season)
        return jsonify({
            "temperature": 33.0, "humidity": 75.0, "wind_speed": 12.0,
            "pressure": 1008.0, "aqi": 80.0, "uv_index": 7.5,
            "season": season, "condition": "Không rõ (fallback)",
            "weather_vector": wv, "cache_hit": False, "expires_at": "",
            "warning": f"OpenWeather không khả dụng: {e}",
        }), 200


@app.route("/api/v1/feedback", methods=["POST"])
def feedback():
    """
    POST /api/v1/feedback
    Body: { session_uuid, dish_id, action, rating?, feedback_at? }
    action: "eaten" | "skipped" | "rated"
    """
    body = request.get_json(force=True)
    session_uuid = body.get("session_uuid", "")
    dish_id      = body.get("dish_id", "")
    action       = body.get("action", "")
    rating       = body.get("rating")          # nullable
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
            INSERT INTO session_feedback (session_uuid, dish_id, action, rating, feedback_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_uuid, dish_id, action, rating, feedback_at, datetime.utcnow().isoformat()))
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        db.close()
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route("/health")
def health():
    try:
        db = get_db()
        n_dishes = db.execute("SELECT COUNT(*) FROM dishes").fetchone()[0]
        n_ingr   = db.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
        db.close()
        return jsonify({"status":"ok","dishes":n_dishes,"ingredients":n_ingr,
                        "db_path": str(DB_PATH)})
    except Exception as e:
        return jsonify({"status":"error","detail":str(e)}), 500

@app.route("/api/v1/recommend", methods=["POST"])
def recommend():
    t0   = datetime.utcnow()
    body = request.get_json(force=True)
    db   = get_db()

    cuisine_scope     = body.get("cuisine_scope", "vietnam")
    selected_nation   = body.get("selected_nation")
    dish_type_filter  = body.get("dish_type_filter", "all")   # "soup" | "main_dish" | "all"
    cost_preference   = int(body.get("cost_preference", 2))   # F03: 1|2|3
    # F04: Anti-repetition — danh sách dish_id (string) gần nhất, ordered gần → xa
    recent_dish_ids_ordered = [str(x) for x in body.get("recent_dish_ids", [])]
    basket = body.get("market_basket", {})
# Nếu client gửi list thay vì dict → coi như skipped
    if isinstance(basket, list):
      
      basket = {"selected_ingredient_ids": basket, "is_skipped": len(basket) == 0}
    selected_ids    = set(basket.get("selected_ingredient_ids", []))
    is_skipped      = basket.get("is_skipped", True)
    boost_strategy  = basket.get("boost_strategy", "strict")
    if is_skipped:
        selected_ids, boost_strategy = set(), "none"

    lat = body.get("lat", 16.047)
    lon = body.get("lon", 108.206)
    wv  = get_or_compute_weather(lat, lon, body.get("weather"))
    loc = resolve_location(lat, lon, db)
    pv  = compute_personal_vector(body.get("personal", {}))

    demand  = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv, db)
    profile["sodium_control_need"]   = demand["sodium_control_need"]
    profile["glycemic_control_need"] = demand["glycemic_control_need"]
    profile["cost_preference"]       = cost_preference   # F03

    season    = _get_current_season()
    dish_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, dish_type_filter)
    if not dish_pool:
        # fallback: nới lỏng dish_type trước, sau đó nới cuisine
        dish_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, "all")
    if not dish_pool:
        dish_pool = filter_dishes(db, "global", None, profile, season, "all")

    task = resolve_taste_weight(pv, loc)

    scores, boosts = {}, {}
    trad_compat = loc["traditional_compatibility"]
    for dish in dish_pool:
        soft  = compute_soft_mult(dish, profile, season)
        avail = get_dish_availability(dish["id"], loc["food_region"], db)
        boost = compute_dish_boost(dish["id"], selected_ids, boost_strategy, db)
        scores[dish["id"]] = score_dish(
            dish, demand, soft, task, trad_compat, avail, boost,
            recent_ids_ordered=recent_dish_ids_ordered  # F04
        )
        boosts[dish["id"]] = boost

    # F06: truyền thêm context cho explanation engine
    _temperature = body.get("weather", {}).get("temperature") if isinstance(body.get("weather"), dict) else None
    ranked, fallback_ids = rank_and_explain(
        scores, dish_pool, boosts, demand, profile,
        loc=loc,
        season=season,
        basket_ingredient_ids=selected_ids,
        db=db,
        temperature=_temperature,
    )
    elapsed = (datetime.utcnow() - t0).total_seconds()
    db.close()

    return jsonify({
        "status":          "ok",
        "elapsed_s":       round(elapsed, 3),
        "location":        loc,
        "weather_vector":  wv,
        "demand_snapshot": demand,
        "cuisine_scope":   cuisine_scope,
        "dish_type_filter": dish_type_filter,
        "cost_preference": cost_preference,
        "basket_skipped":  is_skipped,
        "dish_pool_size":  len(dish_pool),
        "ranked_dishes":   ranked,
        "page_size":       10,   # F04: client hiển thị 10 đầu, "Xem thêm" → 20
        "fallback_ids":    fallback_ids,
        "generated_at":    t0.isoformat(),
    })

@app.route("/api/v1/dishes", methods=["GET"])
def list_dishes():
    db     = get_db()
    nation = request.args.get("nation")
    limit  = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    rows   = db.execute(
        ("SELECT id,title,nation,cook_time_minutes,is_vegan,is_vegetarian "
         "FROM dishes WHERE nation=? LIMIT ? OFFSET ?" if nation else
         "SELECT id,title,nation,cook_time_minutes,is_vegan,is_vegetarian "
         "FROM dishes LIMIT ? OFFSET ?"),
        (nation, limit, offset) if nation else (limit, offset)
    ).fetchall()
    db.close()
    cols = ["id","title","nation","cook_time_minutes","is_vegan","is_vegetarian"]
    return jsonify({"dishes": [dict(zip(cols, r)) for r in rows]})

@app.route("/api/v1/dishes/<dish_id>", methods=["GET"])
def dish_detail(dish_id):
    db  = get_db()
    row = db.execute("SELECT * FROM dishes WHERE id=?", (dish_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error":"not found"}), 404
    dish = dict(row)
    for f in ("allergen_summary","season_suitability","climate_suitability","taste_profile"):
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
    rows     = db.execute(
        ("SELECT id,name,name_en,category,is_animal_based,distribution_reach,seasonal_availability "
         "FROM ingredients WHERE category=? LIMIT ?" if category else
         "SELECT id,name,name_en,category,is_animal_based,distribution_reach,seasonal_availability "
         "FROM ingredients LIMIT ?"),
        (category, limit) if category else (limit,)
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

@app.route("/api/v1/pipeline/debug", methods=["POST"])
def pipeline_debug():
    body = request.get_json(force=True)
    db   = get_db()
    lat  = body.get("lat", 16.047)
    lon  = body.get("lon", 108.206)
    wv   = get_or_compute_weather(lat, lon, body.get("weather"))
    loc  = resolve_location(lat, lon, db)
    pv   = compute_personal_vector(body.get("personal", {}))
    demand    = compute_demand(wv, pv, loc["climate_type"])
    profile   = build_constraint_profile(pv, db)   # ← fix: thêm db
    season    = _get_current_season()
    dish_pool = filter_dishes(db, body.get("cuisine_scope","vietnam"), None, profile, season)
    db.close()
    return jsonify({
        "weather_vector":    wv,
        "location_vector":   loc,
        "personal_vector":   {
            "BMI": pv["BMI"], "energy_need": pv["energy_need"],
            "disease_flags":  pv["disease_flags"],
            "taste_weight":   pv["taste_weight"],
        },
        "physiological_demand": demand,
        "constraint_profile":   profile,
        "dish_pool_count":      len(dish_pool),
        "sample_dishes":        [d["title"] for d in dish_pool[:5]],
    })

@app.route("/api/v1/weather/simulate", methods=["POST"])
def weather_simulate():
    body = request.get_json(force=True)
    wv = compute_weather_vector(
        body.get("temperature", 30), body.get("humidity", 70),
        body.get("wind_speed",  10), body.get("pressure", 1010),
        body.get("aqi", 50),         body.get("uv_index", 6),
        body.get("season", _get_current_season()),
    )
    return jsonify({"weather_vector": wv})

@app.route("/api/v1/challenge")
def get_challenge():
    """
    GET /api/v1/challenge?lat=16.047&lon=108.206
    Trả món thử thách trong ngày. Seed theo ngày + vị trí → deterministic.
    """
    import hashlib, random as _random

    lat  = float(request.args.get("lat", 16.047))
    lon  = float(request.args.get("lon", 108.206))

    today     = datetime.now().strftime("%Y%m%d")
    seed_str  = f"{today}:{round(lat, 1)}:{round(lon, 1)}"
    seed      = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
    _random.seed(seed)

    db     = get_db()
    wv     = get_or_compute_weather(lat, lon, None)
    loc    = resolve_location(lat, lon, db)
    pv     = compute_personal_vector({})
    demand = compute_demand(wv, pv, loc["climate_type"])
    profile = build_constraint_profile(pv, db)
    season  = _get_current_season()

    dish_pool = filter_dishes(db, "vietnam", None, profile, season)
    if not dish_pool:
        dish_pool = filter_dishes(db, "global", None, profile, season)
    if not dish_pool:
        db.close()
        return jsonify({"error": "no dishes available"}), 404

    trad_compat = loc["traditional_compatibility"]
    scores = {}
    for dish in dish_pool:
        soft  = compute_soft_mult(dish, profile, season)
        avail = get_dish_availability(dish["id"], loc["food_region"], db)
        scores[dish["id"]] = score_dish(dish, demand, soft, TASTE_DEFAULTS, trad_compat, avail, 0.0)

    weights = [max(scores.get(d["id"], 0.01), 0.01) for d in dish_pool]
    chosen  = _random.choices(dish_pool, weights=weights, k=1)[0]

    top_dim = max(
        [("hydration", demand["hydration_need"]),
         ("warming",   demand["warming_food_need"]),
         ("cooling",   demand["cooling_food_need"])],
        key=lambda x: x[1]
    )[0]
    why_map = {
        "hydration": f"Hôm nay nắng nóng, {chosen['title']} giúp bổ sung nước hiệu quả.",
        "warming":   f"Thời tiết lạnh hôm nay, {chosen['title']} ấm bụng, rất phù hợp.",
        "cooling":   f"Nhiệt độ cao, {chosen['title']} có tính mát giúp hạ nhiệt tốt.",
    }
    why_today = why_map.get(top_dim, f"{chosen['title']} phù hợp với thời tiết hôm nay.")

    difficulty_map = {1: "easy", 2: "easy", 3: "medium"}
    cook_t = chosen.get("cook_time_minutes") or 30
    diff   = "easy" if cook_t <= 20 else ("medium" if cook_t <= 45 else "hard")

    db.close()
    return jsonify({
        "challenge_dish": {
            "dish_id":      chosen["id"],
            "title":        chosen["title"],
            "image_url":    chosen.get("image_url", ""),
            "url":          chosen.get("url", ""),
            "nation":       chosen.get("nation", ""),
            "cook_time_min": cook_t,
            "difficulty":   diff,
            "why_today":    why_today,
            "tips":         [],
            "final_score":  round(scores.get(chosen["id"], 0.5), 4),
        },
        "challenge_date": today,
        "streak":         0,
    })


@app.route("/api/v1/locations", methods=["GET"])
def list_locations():
    db   = get_db()
    rows = db.execute(
        "SELECT province_name, food_region, climate_type, lat_center, lon_center "
        "FROM vn_administrative_unit ORDER BY province_name"
    ).fetchall()
    db.close()
    cols = ["province_name","food_region","climate_type","lat","lon"]
    return jsonify({"provinces": [dict(zip(cols, r)) for r in rows]})

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  Daily Mate — Demo Recommendation Server")
    print(f"  DB: {DB_PATH}")
    print(f"  Running at: http://localhost:5001")
    print(f"{'='*60}\n")
    app.run(debug=True, port=5001, host="0.0.0.0")