"""Request/response localization for the JSON-backed demo server."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).parent / "data"
SUPPORTED_LANGUAGES = {"vi", "en"}

QUESTION_LABELS_EN = {
    "general_nutrition": "What nutrition metrics does this dish have?",
    "diabetes": "What should people with diabetes keep in mind?",
    "hypertension": "Is this dish high in sodium?",
    "gout": "What should people with gout keep in mind?",
    "ibs": "Is there anything people with IBS should consider?",
    "calories": "Is this dish high in energy?",
    "weight_loss": "Does this dish fit a weight-loss goal?",
    "energy_goal": "Does this dish provide enough energy for my goal?",
    "satiety": "Will this dish help me feel full for longer?",
    "weather_fit": "Why does this dish fit today's weather?",
    "allergy_check": "Does this dish contain ingredients I should avoid?",
    "diet_type": "Does this dish fit my diet?",
    "ingredient_impact": "Which ingredients affect the dish metrics most?",
    "cooking_method": "How does the cooking method affect the dish?",
}

STATIC_EN = {
    "disclaimer": "This information is for reference only and does not replace medical advice.",
    "serving_warm": "Eat hot to get the warming effect.",
    "serving_cool": "Serve with fresh coconut water or extra ice.",
}


def normalize_language(value: Any) -> str:
    """Normalize query/header values such as ``en-US,en;q=0.9``."""
    raw = str(value or "").strip().lower().replace("_", "-")
    first = raw.split(",", 1)[0].split(";", 1)[0].strip()
    code = first.split("-", 1)[0]
    return code if code in SUPPORTED_LANGUAGES else "vi"


def language_from_request(request) -> str:
    """Prefer explicit query parameter, then Accept-Language, then Vietnamese."""
    return normalize_language(request.args.get("lang") or request.headers.get("Accept-Language"))


@lru_cache(maxsize=None)
def _overlay(filename: str) -> dict[str, dict[str, Any]]:
    path = DATA_DIR / "translations" / "en" / filename
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("data", []):
        key = row.get("id", row.get("method_id"))
        if key is not None:
            result[str(key)] = row
    return result


def localize_dish(dish: dict[str, Any], language: str = "vi") -> dict[str, Any]:
    result = dict(dish)
    if normalize_language(language) != "en":
        return result
    translated = _overlay("dishes.json").get(str(dish.get("id")), {})
    if translated.get("title_en"):
        result["title"] = translated["title_en"]
    if translated.get("description_en"):
        result["description"] = translated["description_en"]
    return result


def localize_ingredient(ingredient: dict[str, Any], language: str = "vi") -> dict[str, Any]:
    result = dict(ingredient)
    if normalize_language(language) != "en":
        return result
    translated = _overlay("ingredients.json").get(str(ingredient.get("id")), {})
    if translated.get("name_en"):
        result["name"] = translated["name_en"]
    if translated.get("category_en"):
        result["category"] = translated["category_en"]
    return result


def localize_ingredient_row(row: dict[str, Any], language: str = "vi") -> dict[str, Any]:
    result = dict(row)
    if normalize_language(language) != "en":
        return result
    ingredient = localize_ingredient({"id": row.get("ingredient_id"), "name": row.get("name", ""), "category": row.get("category", "")}, language)
    result["name"] = ingredient.get("name", result.get("name", ""))
    result["category"] = ingredient.get("category", result.get("category", ""))
    if result.get("ing_name_en"):
        result["ing_name_en"] = result["name"]
    return result


def localize_ranked_dishes(rows: list[dict[str, Any]], language: str = "vi") -> list[dict[str, Any]]:
    if normalize_language(language) != "en":
        return rows
    result = []
    for row in rows:
        item = dict(row)
        dish = localize_dish({"id": row.get("dish_id"), "title": row.get("title", "")}, language)
        item["title"] = dish.get("title", item.get("title", ""))
        explanation = row.get("explanation")
        if isinstance(explanation, dict):
            explanation = dict(explanation)
            explanation["headline"] = item["title"]
            item["explanation"] = explanation
        suggestion = item.get("serving_suggestion")
        if suggestion == "Ăn nóng để phát huy tác dụng giữ ấm":
            item["serving_suggestion"] = STATIC_EN["serving_warm"]
        elif suggestion == "Ăn kèm nước dừa tươi hoặc thêm đá":
            item["serving_suggestion"] = STATIC_EN["serving_cool"]
        result.append(item)
    return result


def localize_questions(rows: list[dict[str, Any]], language: str = "vi") -> list[dict[str, Any]]:
    if normalize_language(language) != "en":
        return rows
    return [
        {**row, "label": QUESTION_LABELS_EN.get(row.get("id"), row.get("label", ""))}
        for row in rows
    ]


def question_label(question_id: str, fallback: str, language: str = "vi") -> str:
    if normalize_language(language) == "en":
        return QUESTION_LABELS_EN.get(question_id, fallback)
    return fallback


def disclaimer(language: str = "vi") -> str:
    return STATIC_EN["disclaimer"] if normalize_language(language) == "en" else "Thông tin mang tính tham khảo, không thay thế tư vấn y tế."


def localize_province(row: dict[str, Any], language: str = "vi") -> dict[str, Any]:
    if normalize_language(language) != "en":
        return {
            "province_name": row.get("province_name", ""),
            "food_region": row.get("food_region", ""),
            "climate_type": row.get("climate_type", ""),
            "lat": row.get("lat_center"),
            "lon": row.get("lon_center"),
        }
    translated = _overlay("provinces.json").get(str(row.get("id")), {})
    return {
        "province_name": translated.get("name_en", row.get("province_name", "")),
        "food_region": translated.get("food_region_en", row.get("food_region", "")),
        "climate_type": translated.get("climate_type_en", row.get("climate_type", "")),
        "cuisine_culture": translated.get("cuisine_culture_en", row.get("cuisine_culture", "")),
        "lat": row.get("lat_center"),
        "lon": row.get("lon_center"),
    }
