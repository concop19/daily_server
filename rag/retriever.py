"""Rule-aware semantic retriever for Nutrition RAG."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any

from dotenv import load_dotenv

# JinaEmbedder and NutritionVectorStore are lazily loaded in NutritionRetriever.__init__


load_dotenv()


@dataclass(frozen=True)
class RetrievalPlan:
    condition: str | None
    group: str | None
    topics: tuple[str, ...]
    nutrition_fields: tuple[str, ...]
    matched_keywords: tuple[str, ...]


CONDITION_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "diabetes": ("tieu_duong", ("tiểu đường", "đái tháo đường", "diabetes")),
    "hypertension": ("tang_huyet_ap", ("tăng huyết áp", "cao huyết áp", "huyết áp", "hypertension")),
    "gout": ("gout", ("gout", "gút", "purine", "axit uric", "acid uric")),
    "ibs": ("ibs", ("ibs", "ruột kích thích", "đầy hơi", "fodmap")),
}

CONDITION_DEFAULT_FIELDS: dict[str, tuple[str, ...]] = {
    "diabetes": ("dish_glycemic_load", "adj_glycemic_load", "adj_glycemic_load_per_100g", "gl_safety_score"),
    "hypertension": ("sodium_per_serving", "adj_sodium_total", "sodium_safety_score"),
    "gout": ("gout_risk_score",),
    "ibs": (),
}

METRIC_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "sodium": (("sodium", "natri", "muối", "nước mắm", "đồ mặn"), ("sodium_per_serving", "adj_sodium_total", "sodium_safety_score")),
    "glycemic_load": (("gl", "glycemic", "đường huyết", "carb", "carbohydrate"), ("dish_glycemic_load", "adj_glycemic_load", "adj_glycemic_load_per_100g", "gl_safety_score")),
    "gout_risk": (("gout", "gút", "purine", "axit uric", "acid uric"), ("gout_risk_score",)),
    "calories": (("calo", "calories", "năng lượng", "kcal"), ("energy_per_serving", "dish_energy_total", "adj_energy_total")),
    "protein": (("protein", "đạm"), ()),
    "fiber": (("chất xơ", "fiber"), ()),
    "satiety": (("no lâu", "cảm giác no", "satiety"), ("dish_satiety_score", "adj_satiety_score")),
    "hydration": (("cấp nước", "hydration", "bù nước"), ("dish_hydration_score", "adj_hydration_score")),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _is_negated(text: str, keyword: str) -> bool:
    """Detect common Vietnamese negation immediately before a keyword."""
    start = text.find(keyword)
    while start >= 0:
        prefix = text[max(0, start - 32) : start]
        if re.search(
            r"(?:không|chưa)\s+"
            r"(?:\S+\s+){0,1}"
            r"(?:bị|mắc|có|phải|bệnh)\s+"
            r"(?:\S+\s+){0,2}$",
            prefix,
        ):
            return True
        start = text.find(keyword, start + 1)
    return False


def build_retrieval_plan(query: str) -> RetrievalPlan:
    """Map fixed keywords to a safe metadata filter and dish fields."""

    normalized = _normalize(query)
    condition: str | None = None
    group: str | None = None
    matched: list[str] = []

    for condition_name, (condition_group, keywords) in CONDITION_RULES.items():
        found = [
            keyword
            for keyword in keywords
            if keyword in normalized and not _is_negated(normalized, keyword)
        ]
        if found:
            condition = condition_name
            group = condition_group
            matched.extend(found)
            break

    fields: list[str] = []
    topics: list[str] = []
    for metric_name, (keywords, metric_fields) in METRIC_RULES.items():
        found = [
            keyword
            for keyword in keywords
            if keyword in normalized and not _is_negated(normalized, keyword)
        ]
        if found:
            matched.extend(found)
            fields.extend(metric_fields)
            topics.append(metric_name)

    # With no metric keyword, the answer layer should show only basic values.
    if not fields and condition:
        fields = list(CONDITION_DEFAULT_FIELDS.get(condition, ()))
    if not fields:
        fields = ["energy_per_serving", "adj_energy_total", "adj_sodium_total", "adj_glycemic_load"]

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
        store: Any | None = None,
        embedder: Any | None = None,
    ) -> None:
        backend = os.environ.get("RAG_VECTOR_BACKEND", "").strip().lower()
        if not backend:
            backend = "supabase" if (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")) else "local"

        if backend == "supabase" and store is None and embedder is None:
            from .api_embedder import JinaAPIEmbedder
            from .supabase_vector_store import SupabaseVectorStore

            self.store = SupabaseVectorStore()
            self.embedder = JinaAPIEmbedder()
            return

        if backend == "local" or store is not None or embedder is not None:
            from .embedder import JinaEmbedder
            from .vector_store import NutritionVectorStore

            self.store = store or NutritionVectorStore()
            self.embedder = embedder or JinaEmbedder()
            return

        raise ValueError("RAG_VECTOR_BACKEND phải là 'local' hoặc 'supabase'")

    def retrieve_for_question(
        self,
        question_id: str,
        language: str = "vi",
        n_results: int = 5,
        query: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve chunks using precomputed 1024-dim embedding from RAM (0ms).
        Zero Jina API/model calls at runtime when precomputed embedding is available.
        """
        import logging
        import data_store
        from .health_qa import QUESTION_SPECS

        logger = logging.getLogger(__name__)
        lang = (language or "vi").strip().lower()
        cached = data_store.get_fixed_question_embedding(question_id, lang)

        if cached is not None:
            vector, meta = cached
            retrieval_query = meta.get("retrieval_query") or query or ""
            plan = build_retrieval_plan(retrieval_query)
            where = {"group": plan.group or "dinh_duong"}
            results = self.store.query_by_embedding(
                vector,
                n_results=n_results,
                where=where,
            )
            return {
                "query": query or meta.get("question_text", retrieval_query),
                "retrieval_query": retrieval_query,
                "plan": plan,
                "results": results,
                "retrieval_meta": {
                    "embedding_source": "precomputed",
                    "embedding_model": meta.get("embedding_model", "jina-embeddings-v3"),
                    "dimensions": len(vector),
                },
            }

        # Handle missing precomputed embedding
        allow_fallback = os.environ.get("ALLOW_RUNTIME_JINA_FALLBACK", "false").strip().lower() == "true"
        spec = QUESTION_SPECS.get(question_id, {})
        actual_query = query or spec.get("query") or "Giải thích các chỉ số dinh dưỡng cơ bản của món ăn"

        if allow_fallback:
            logger.warning(
                f"[NutritionRetriever] Precomputed embedding missing for '{question_id}:{lang}'. "
                f"Falling back to runtime Jina embedding call."
            )
            res = self.retrieve(actual_query, n_results=n_results)
            res["retrieval_meta"] = {
                "embedding_source": "runtime_jina_fallback",
                "embedding_model": getattr(self.embedder, "model_name", "unknown"),
            }
            return res
        else:
            logger.error(
                f"[NutritionRetriever] missing_precomputed_embedding for '{question_id}:{lang}'. "
                f"Runtime Jina fallback is DISABLED (ALLOW_RUNTIME_JINA_FALLBACK=false)."
            )
            plan = build_retrieval_plan(actual_query)
            return {
                "query": actual_query,
                "retrieval_query": actual_query,
                "plan": plan,
                "results": {
                    "ids": [[]],
                    "documents": [[]],
                    "metadatas": [[]],
                    "distances": [[]],
                },
                "retrieval_meta": {
                    "embedding_source": "missing_fallback",
                    "error": "missing_precomputed_embedding",
                },
            }

    def retrieve(self, query: str, n_results: int = 5) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("Query không được rỗng.")
        plan = build_retrieval_plan(query)
        # Không có bệnh lý dương tính thì chỉ lấy tài liệu dinh dưỡng chung.
        # Với câu phủ định như “không bị tiểu đường nhưng đau răng”, dùng
        # truy vấn trung tính để từ bị phủ định không kéo nhầm tài liệu bệnh lý.
        where = {"group": plan.group or "dinh_duong"}
        retrieval_query = query
        if plan.condition is None and not plan.topics:
            retrieval_query = "Giải thích các chỉ số dinh dưỡng cơ bản của món ăn"
        results = self.store.query(
            retrieval_query,
            self.embedder,
            n_results=n_results,
            where=where,
        )
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "plan": plan,
            "results": results,
            "retrieval_meta": {
                "embedding_source": "runtime_embedder",
                "embedding_model": getattr(self.embedder, "model_name", "unknown"),
            },
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
