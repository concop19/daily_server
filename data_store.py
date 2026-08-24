"""
data_store.py -- JSON-based data layer thay the SQLite.
Load tat ca JSON vao memory khi server start, query = Python dict lookup.
Giu nguyen ten ham de caller thay doi toi thieu.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# ── Internal state ──────────────────────────────────────────────────────────────
_dishes: list[dict] = []
_dishes_by_id: dict[int, dict] = {}
_ingredients: list[dict] = []
_ingredients_by_id: dict[int, dict] = {}
_dish_ingredients: list[dict] = []
_dish_ingredients_by_dish: dict[int, list[dict]] = {}
_cooking_methods: list[dict] = []
_provinces: list[dict] = []
_availability_matrix: list[dict] = []
_advice_templates: list[dict] = []
_device_tokens: list[dict] = []
_fixed_question_embeddings: dict[str, dict] = {}
_tokens_lock = threading.Lock()
_loaded = False
_advice_translations: list[dict] | None = None


def _load_json(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"[DataStore] Missing: {path}")
    raw = path.read_text(encoding="utf-8")
    obj = json.loads(raw)
    return obj.get("data", [])


def load_all():
    """Load tat ca JSON vao memory. Goi 1 lan khi server start."""
    global _dishes, _dishes_by_id
    global _ingredients, _ingredients_by_id
    global _dish_ingredients, _dish_ingredients_by_dish
    global _cooking_methods, _provinces, _availability_matrix
    global _advice_templates, _device_tokens, _loaded, _advice_translations
    global _fixed_question_embeddings

    _dishes = _load_json("dishes.json")
    _dishes_by_id = {int(d["id"]): d for d in _dishes}

    _ingredients = _load_json("ingredients.json")
    _ingredients_by_id = {int(i["id"]): i for i in _ingredients}

    _dish_ingredients = _load_json("dish_ingredients.json")
    _dish_ingredients_by_dish = {}
    for row in _dish_ingredients:
        did = int(row.get("recipe_id") or row.get("dish_id") or 0)
        _dish_ingredients_by_dish.setdefault(did, []).append(row)

    _cooking_methods = _load_json("cooking_methods.json")
    _provinces = _load_json("provinces.json")
    _availability_matrix = _load_json("availability_matrix.json")
    _advice_templates = _load_json("advice_templates.json")
    _advice_translations = None

    # device_tokens co the chua ton tai (server fresh)
    tokens_path = DATA_DIR / "device_tokens.json"
    if tokens_path.exists():
        raw = json.loads(tokens_path.read_text(encoding="utf-8"))
        _device_tokens = raw.get("data", [])
    else:
        _device_tokens = []

    # fixed_question_embeddings
    fixed_q_path = DATA_DIR / "fixed_question_embeddings.json"
    if fixed_q_path.exists():
        try:
            raw = json.loads(fixed_q_path.read_text(encoding="utf-8"))
            _fixed_question_embeddings = raw.get("questions", {})
        except Exception as e:
            print(f"[DataStore] Warning loading fixed_question_embeddings.json: {e}")
            _fixed_question_embeddings = {}
    else:
        _fixed_question_embeddings = {}

    _loaded = True
    print(
        f"[DataStore] Loaded: dishes={len(_dishes)}, ingredients={len(_ingredients)}, "
        f"dish_ingredients={len(_dish_ingredients)}, provinces={len(_provinces)}, "
        f"templates={len(_advice_templates)}, question_embeddings={len(_fixed_question_embeddings)}"
    )


# ── Dishes ──────────────────────────────────────────────────────────────────────

def get_all_dishes() -> list[dict]:
    return _dishes


def get_dish_by_id(dish_id: int) -> dict | None:
    return _dishes_by_id.get(int(dish_id))


def get_dishes_paginated(page: int = 1, per_page: int = 50) -> tuple[list[dict], int]:
    total = len(_dishes)
    start = (page - 1) * per_page
    return _dishes[start: start + per_page], total


# ── Ingredients ─────────────────────────────────────────────────────────────────

def get_all_ingredients() -> list[dict]:
    return _ingredients


def get_ingredient_by_id(ingredient_id: int) -> dict | None:
    return _ingredients_by_id.get(int(ingredient_id))


def get_ingredients_paginated(page: int = 1, per_page: int = 100) -> tuple[list[dict], int]:
    total = len(_ingredients)
    start = (page - 1) * per_page
    return _ingredients[start: start + per_page], total


# ── Dish-Ingredient relationships ───────────────────────────────────────────────

def get_ingredients_for_dish(dish_id: int) -> list[dict]:
    """Tra ve danh sach ingredient rows cua 1 dish (co enriched ingredient info)."""
    rows = _dish_ingredients_by_dish.get(int(dish_id), [])
    result = []
    for row in rows:
        ing_id = int(row.get("ingredient_id") or 0)
        ing = _ingredients_by_id.get(ing_id, {})
        merged = {**row, **{f"ing_{k}": v for k, v in ing.items()}}
        merged["name"] = ing.get("name", "")
        merged["category"] = ing.get("ingredient_type") or ing.get("category", "")
        merged["source_type"] = ing.get("source_type", "")
        result.append(merged)
    return result


def get_dish_ingredient_ids(dish_ids: list[int]) -> dict[int, list[int]]:
    """Batch: {dish_id: [ingredient_id, ...]} -- de compute basket coverage."""
    result: dict[int, list[int]] = {}
    for did in dish_ids:
        rows = _dish_ingredients_by_dish.get(int(did), [])
        result[int(did)] = [int(r["ingredient_id"]) for r in rows if r.get("ingredient_id")]
    return result


def get_dish_ingredient_rows(dish_id: int) -> list[dict]:
    """Raw rows tu dish_ingredient table cho 1 dish."""
    return _dish_ingredients_by_dish.get(int(dish_id), [])


# ── Provinces ───────────────────────────────────────────────────────────────────

def get_all_provinces() -> list[dict]:
    return _provinces


def get_province_by_id(province_id: int) -> dict | None:
    for p in _provinces:
        if int(p.get("id", -1)) == int(province_id):
            return p
    return None


# ── Availability matrix ─────────────────────────────────────────────────────────

def get_availability_matrix() -> list[dict]:
    return _availability_matrix


def get_availability(distribution_reach: str, food_region: str) -> dict | None:
    for row in _availability_matrix:
        if row.get("distribution_reach") == distribution_reach and row.get("food_region") == food_region:
            return row
    return None


# ── Advice templates ────────────────────────────────────────────────────────────

def _get_advice_templates_for_language(language: str = "vi") -> list[dict]:
    """Return source templates or the English overlay merged onto source rows."""
    global _advice_translations
    if str(language or "vi").lower().split("-", 1)[0] != "en":
        return _advice_templates

    if _advice_translations is None:
        path = DATA_DIR / "translations" / "en" / "advice_templates.json"
        overlay = {}
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            overlay = {str(row.get("id")): row for row in payload.get("data", [])}

        merged = []
        for source in _advice_templates:
            row = dict(source)
            translated = overlay.get(str(source.get("id")), {})
            if translated.get("template_text_en"):
                row["template_text"] = translated["template_text_en"]
            if translated.get("notes_en"):
                row["notes"] = translated["notes_en"]
            row["lang"] = "en"
            merged.append(row)
        _advice_translations = merged

    return _advice_translations


def get_advice_templates(context_type: str, trigger_dim: str, intensity: str,
                         language: str = "vi") -> list[dict]:
    """Tuong duong: SELECT * FROM advice_templates WHERE context_type=? AND trigger_dim=? AND intensity=?"""
    return [
        t for t in _get_advice_templates_for_language(language)
        if t.get("context_type") == context_type
        and t.get("trigger_dim") == trigger_dim
        and t.get("intensity") == intensity
    ]


def get_all_advice_templates(language: str = "vi") -> list[dict]:
    return _get_advice_templates_for_language(language)


# ── Cooking methods ─────────────────────────────────────────────────────────────

def get_all_cooking_methods() -> list[dict]:
    return _cooking_methods


# ── Device tokens (write-capable) ───────────────────────────────────────────────

def _persist_tokens():
    """Luu device_tokens xuong file JSON sau moi thay doi."""
    path = DATA_DIR / "device_tokens.json"
    payload = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "table": "device_tokens",
        "count": len(_device_tokens),
        "data": _device_tokens,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_device_token(device_id: str, fcm_token: str, platform: str = "android",
                        lat: float = None, lon: float = None, province: str = None):
    with _tokens_lock:
        now = datetime.now(timezone.utc).isoformat()
        for tok in _device_tokens:
            if tok.get("device_id") == device_id:
                tok.update({
                    "fcm_token": fcm_token, "platform": platform,
                    "lat": lat, "lon": lon, "province": province,
                    "updated_at": now,
                })
                _persist_tokens()
                return
        _device_tokens.append({
            "device_id": device_id, "fcm_token": fcm_token, "platform": platform,
            "lat": lat, "lon": lon, "province": province,
            "created_at": now, "updated_at": now,
        })
        _persist_tokens()


def get_device_tokens_by_province(province: str) -> list[dict]:
    with _tokens_lock:
        if not province:
            return list(_device_tokens)
        return [t for t in _device_tokens if t.get("province") == province]


def get_all_device_tokens() -> list[dict]:
    with _tokens_lock:
        return list(_device_tokens)


# ── Fixed Question Embeddings (0ms In-Memory) ───────────────────────────────────

def get_fixed_question_embedding(question_id: str, language: str = "vi") -> tuple[list[float], dict] | None:
    """
    Retrieve precomputed vector and metadata for a fixed question from memory (0ms).
    Prioritizes requested language, falls back to 'vi' if missing.
    Returns: (embedding_list, metadata_dict) or None if not found.
    """
    lang = (language or "vi").strip().lower()
    key = f"{question_id}:{lang}"
    item = _fixed_question_embeddings.get(key)
    if not item and lang != "vi":
        item = _fixed_question_embeddings.get(f"{question_id}:vi")
    if not item:
        return None
    return item.get("embedding"), item


def get_all_fixed_question_embeddings() -> dict[str, dict]:
    return _fixed_question_embeddings


# ── Stats helper ────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    return {
        "dishes":                     len(_dishes),
        "ingredients":                len(_ingredients),
        "dish_ingredients":           len(_dish_ingredients),
        "cooking_methods":            len(_cooking_methods),
        "provinces":                  len(_provinces),
        "availability_matrix":        len(_availability_matrix),
        "advice_templates":           len(_advice_templates),
        "device_tokens":              len(_device_tokens),
        "fixed_question_embeddings":  len(_fixed_question_embeddings),
    }

