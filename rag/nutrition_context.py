"""Combine retrieved evidence with authoritative dish values."""

from __future__ import annotations

from typing import Any

from .dish_context import get_dish_nutrition_context
from .retriever import NutritionRetriever, build_retrieval_plan


class NutritionContextBuilder:
    """Prepare grounded input for the future answer-generation layer."""

    def __init__(self, retriever: NutritionRetriever | None = None) -> None:
        self.retriever = retriever or NutritionRetriever()

    def build(self, dish_id: int, query: str, n_results: int = 5) -> dict[str, Any]:
        plan = build_retrieval_plan(query)
        dish_context = get_dish_nutrition_context(
            dish_id=dish_id,
            fields=plan.nutrition_fields,
        )
        retrieval = self.retriever.retrieve(query, n_results=n_results)
        return {
            "query": query,
            "dish": dish_context,
            "retrieval_plan": {
                "condition": plan.condition,
                "group": plan.group,
                "topics": list(plan.topics),
                "nutrition_fields": list(plan.nutrition_fields),
                "matched_keywords": list(plan.matched_keywords),
            },
            "retrieval_query": retrieval.get("retrieval_query", query),
            "evidence": retrieval["results"],
            "retrieval_meta": retrieval.get("retrieval_meta", {}),
        }

    def build_for_question(
        self,
        dish_id: int,
        question_id: str,
        language: str = "vi",
        query: str | None = None,
        n_results: int = 5,
    ) -> dict[str, Any]:
        """Build grounded RAG context using precomputed question vector (0ms Jina latency)."""
        retrieval = self.retriever.retrieve_for_question(
            question_id=question_id,
            language=language,
            query=query,
            n_results=n_results,
        )
        plan = retrieval.get("plan") or build_retrieval_plan(retrieval.get("retrieval_query", ""))
        dish_context = get_dish_nutrition_context(
            dish_id=dish_id,
            fields=plan.nutrition_fields,
        )
        return {
            "query": retrieval.get("query", query or ""),
            "dish": dish_context,
            "retrieval_plan": {
                "condition": plan.condition,
                "group": plan.group,
                "topics": list(plan.topics),
                "nutrition_fields": list(plan.nutrition_fields),
                "matched_keywords": list(plan.matched_keywords),
            },
            "retrieval_query": retrieval.get("retrieval_query", query or ""),
            "evidence": retrieval["results"],
            "retrieval_meta": retrieval.get("retrieval_meta", {}),
        }
