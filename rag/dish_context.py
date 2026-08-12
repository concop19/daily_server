"""Build a grounded nutrition context from a real dish in DataStore."""

from __future__ import annotations

from typing import Any, Iterable

import data_store


AVAILABLE_NUTRITION_FIELDS = {
    "energy_per_serving",
    "energy_per_100g",
    "dish_energy_total",
    "adj_energy_total",
    "sodium_per_serving",
    "sodium_per_100g",
    "dish_sodium_total",
    "adj_sodium_total",
    "sodium_safety_score",
    "dish_glycemic_load",
    "adj_glycemic_load",
    "adj_glycemic_load_per_100g",
    "gl_safety_score",
    "gout_risk_score",
    "dish_hydration_score",
    "adj_hydration_score",
    "dish_satiety_score",
    "adj_satiety_score",
    "dish_thermogenic_score",
    "adj_thermogenic_score",
    "dish_warming_score",
    "adj_warming_score",
    "dish_cooling_score",
    "adj_cooling_score",
    "total_weight_g",
}


def get_dish_nutrition_context(
    dish_id: int,
    fields: Iterable[str],
) -> dict[str, Any]:
    """Return only requested values that actually exist on the dish."""

    dish = data_store.get_dish_by_id(dish_id)
    if dish is None:
        data_store.load_all()
        dish = data_store.get_dish_by_id(dish_id)
    if dish is None:
        raise LookupError(f"Không tìm thấy dish_id={dish_id}.")

    requested = list(dict.fromkeys(fields))
    values = {field: dish.get(field) for field in requested if field in dish}
    missing = [field for field in requested if field not in dish]

    return {
        "dish_id": int(dish["id"]),
        "title": dish.get("title"),
        "description": dish.get("description"),
        "serving_size": "toàn bộ công thức món ăn",
        "values": values,
        "missing_fields": missing,
        "available_fields": sorted(AVAILABLE_NUTRITION_FIELDS.intersection(dish)),
    }

