"""Rule-aware semantic retriever for Nutrition RAG."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .embedder import JinaEmbedder
from .vector_store import NutritionVectorStore


@dataclass(frozen=True)
class RetrievalPlan:
    condition: str | None
    group: str | None
    topics: tuple[str, ...]
    nutrition_fields: tuple[str, ...]
    matched_keywords: tuple[str, ...]


CONDITION_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "diabetes": ("tieu_duong", ("tiểu đường", "đái tháo đường", "đường huyết", "diabetes")),
    "hypertension": ("tang_huyet_ap", ("tăng huyết áp", "cao huyết áp", "huyết áp", "hypertension")),
    "gout": ("gout", ("gout", "gút", "purine", "axit uric", "acid uric")),
    "ibs": ("ibs", ("ibs", "ruột kích thích", "đầy hơi", "fodmap")),
}

METRIC_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "sodium": (("sodium", "natri", "muối", "nước mắm", "đồ mặn"), ("dish_sodium_total", "adj_sodium_total", "sodium_safety_score")),
    "glycemic_load": (("gl", "glycemic", "đường huyết", "carb", "carbohydrate", "đường"), ("glycemic_load", "adj_glycemic_load", "adj_glycemic_load_per_100g")),
    "gout_risk": (("gout", "gút", "purine", "axit uric", "acid uric"), ("gout_risk_score",)),
    "calories": (("calo", "calories", "năng lượng", "kcal"), ("dish_energy_total", "adj_energy_total")),
    "protein": (("protein", "đạm"), ("protein_g",)),
    "fiber": (("chất xơ", "fiber"), ("fiber_g",)),
    "satiety": (("no lâu", "cảm giác no", "satiety"), ("dish_satiety_score", "adj_satiety_score")),
    "hydration": (("cấp nước", "hydration", "bù nước"), ("dish_hydration_score", "adj_hydration_score")),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def build_retrieval_plan(query: str) -> RetrievalPlan:
    """Map fixed keywords to a safe metadata filter and dish fields."""

    normalized = _normalize(query)
    condition: str | None = None
    group: str | None = None
    matched: list[str] = []

    for condition_name, (condition_group, keywords) in CONDITION_RULES.items():
        found = [keyword for keyword in keywords if keyword in normalized]
        if found:
            condition = condition_name
            group = condition_group
            matched.extend(found)
            break

    fields: list[str] = []
    topics: list[str] = []
    for metric_name, (keywords, metric_fields) in METRIC_RULES.items():
        found = [keyword for keyword in keywords if keyword in normalized]
        if found:
            matched.extend(found)
            fields.extend(metric_fields)
            topics.append(metric_name)

    # With no metric keyword, the answer layer should show only basic values.
    if not fields:
        fields = ["adj_energy_total", "protein_g", "carbs_g", "adj_sodium_total"]

    return RetrievalPlan(
        condition=condition,
        group=group,
        topics=tuple(dict.fromkeys(topics)),
        nutrition_fields=tuple(dict.fromkeys(fields)),
        matched_keywords=tuple(dict.fromkeys(matched)),
    )


class NutritionRetriever:
    def __init__(
        self,
        store: NutritionVectorStore | None = None,
        embedder: JinaEmbedder | None = None,
    ) -> None:
        self.store = store or NutritionVectorStore()
        self.embedder = embedder or JinaEmbedder()

    def retrieve(self, query: str, n_results: int = 5) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("Query không được rỗng.")
        plan = build_retrieval_plan(query)
        where = {"group": plan.group} if plan.group else None
        results = self.store.query(query, self.embedder, n_results=n_results, where=where)
        return {
            "query": query,
            "plan": plan,
            "results": results,
        }


if __name__ == "__main__":
    retriever = NutritionRetriever()
    result = retriever.retrieve("Người bị tiểu đường cần quan tâm chỉ số nào?")
    plan = result["plan"]
    print(f"condition={plan.condition}, group={plan.group}")
    print(f"fields={', '.join(plan.nutrition_fields)}")
    print(f"results={len(result['results']['ids'][0])}")
    for metadata, distance in zip(
        result["results"]["metadatas"][0], result["results"]["distances"][0]
    ):
        print(f"- {metadata.get('topic')} | distance={distance:.4f}")

