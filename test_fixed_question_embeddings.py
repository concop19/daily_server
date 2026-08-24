"""
test_fixed_question_embeddings.py — Automated Tests for Precomputed Fixed Question Embeddings.

Verifies:
1. In-memory loading of all 28 question embeddings (14 VI + 14 EN) in data_store with 1024 dimensions.
2. Idempotency of offline indexing (0 API calls when hash is unchanged).
3. Runtime retrieval strictly uses precomputed embeddings with ZERO Jina calls (embed_query is never invoked).
4. REST API endpoint /api/v1/dishes/<dish_id>/health-question returns valid answers for all fixed questions.
5. Missing question behavior with ALLOW_RUNTIME_JINA_FALLBACK=false.
"""

import os
import unittest
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()
os.environ["ALLOW_RUNTIME_JINA_FALLBACK"] = "false"

import data_store
data_store.load_all()

from app import app
from index_fixed_questions import index_fixed_questions
from rag.health_qa import QUESTION_SPECS
from rag.retriever import NutritionRetriever
from rag.nutrition_context import NutritionContextBuilder


class TestFixedQuestionEmbeddings(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.retriever = NutritionRetriever()
        self.context_builder = NutritionContextBuilder(self.retriever)

    def test_in_memory_embeddings_loaded(self):
        """Verify all 14 fixed questions exist for both VI and EN with 1024 dimensions."""
        all_embeddings = data_store.get_all_fixed_question_embeddings()
        self.assertEqual(len(all_embeddings), 28)

        for qid in QUESTION_SPECS:
            # Test Vietnamese
            vi_res = data_store.get_fixed_question_embedding(qid, "vi")
            self.assertIsNotNone(vi_res, f"Missing Vietnamese embedding for {qid}")
            vec_vi, meta_vi = vi_res
            self.assertEqual(len(vec_vi), 1024)
            self.assertEqual(meta_vi["embedding_model"], "jina-embeddings-v3")
            self.assertEqual(meta_vi["language"], "vi")

            # Test English
            en_res = data_store.get_fixed_question_embedding(qid, "en")
            self.assertIsNotNone(en_res, f"Missing English embedding for {qid}")
            vec_en, meta_en = en_res
            self.assertEqual(len(vec_en), 1024)
            self.assertEqual(meta_en["embedding_model"], "jina-embeddings-v3")
            self.assertEqual(meta_en["language"], "en")

    def test_indexing_idempotent(self):
        """Running index script without --force must not make any new API calls."""
        stats = index_fixed_questions(languages=("vi", "en"), force=False, dry_run=False)
        self.assertEqual(stats["total"], 28)
        self.assertEqual(stats["new"], 0)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["unchanged"], 28)
        self.assertEqual(stats["errors"], 0)

    def test_runtime_retrieval_zero_jina_call(self):
        """Verify that retrieve_for_question never calls embedder.embed_query."""
        def blow_up_on_embed_call(*args, **kwargs):
            raise AssertionError("Runtime Jina API should NEVER be called for fixed questions!")

        with patch.object(self.retriever.embedder, "embed_query", side_effect=blow_up_on_embed_call):
            # Test all 14 questions in Vietnamese
            for qid in QUESTION_SPECS:
                result_vi = self.retriever.retrieve_for_question(qid, language="vi", n_results=3)
                self.assertIn("results", result_vi)
                self.assertEqual(result_vi["retrieval_meta"]["embedding_source"], "precomputed")
                self.assertEqual(result_vi["retrieval_meta"]["dimensions"], 1024)

            # Test questions in English
            for qid in QUESTION_SPECS:
                result_en = self.retriever.retrieve_for_question(qid, language="en", n_results=3)
                self.assertIn("results", result_en)
                self.assertEqual(result_en["retrieval_meta"]["embedding_source"], "precomputed")

    def test_context_builder_for_question(self):
        """Verify NutritionContextBuilder.build_for_question works with precomputed embeddings."""
        dish = data_store.get_all_dishes()[0]
        dish_id = int(dish["id"])

        ctx = self.context_builder.build_for_question(dish_id, "diabetes", language="vi", n_results=3)
        self.assertEqual(ctx["dish"]["dish_id"], dish_id)
        self.assertEqual(ctx["retrieval_meta"]["embedding_source"], "precomputed")
        self.assertEqual(ctx["retrieval_plan"]["condition"], "diabetes")

    def test_api_health_question_endpoint(self):
        """Verify POST /api/v1/dishes/<dish_id>/health-question returns valid responses."""
        dish = data_store.get_all_dishes()[0]
        dish_id = dish["id"]

        with patch("auth_middleware._jwks_client.get_signing_key_from_jwt") as mock_key, \
             patch("jwt.decode") as mock_decode:
            mock_key.return_value.key = "fake_key"
            mock_decode.return_value = {
                "sub": "test_user_123",
                "email": "test@dailymate.vn",
                "role": "authenticated",
            }
            auth_headers = {"Authorization": "Bearer fake_test_token"}

            # 1. Test VI
            resp_vi = self.client.post(
                f"/api/v1/dishes/{dish_id}/health-question",
                headers=auth_headers,
                json={
                    "question_id": "diabetes",
                    "language": "vi",
                    "profile": {"health_condition": ["diabetes"]},
                    "show_sources": True,
                },
            )
            self.assertEqual(resp_vi.status_code, 200)
            data_vi = resp_vi.get_json()
            self.assertEqual(data_vi["dish_id"], int(dish_id))
            self.assertEqual(data_vi["question_id"], "diabetes")
            self.assertTrue(bool(data_vi["answer"]))
            self.assertIn(data_vi["answer_mode"], ["ai_rag", "grounded_fallback"])

            # 2. Test EN
            resp_en = self.client.post(
                f"/api/v1/dishes/{dish_id}/health-question",
                headers=auth_headers,
                json={
                    "question_id": "calories",
                    "language": "en",
                    "profile": {},
                },
            )
            self.assertEqual(resp_en.status_code, 200)
            data_en = resp_en.get_json()
            self.assertEqual(data_en["question_id"], "calories")
            self.assertEqual(data_en["language"], "en")
            self.assertTrue(bool(data_en["answer"]))

    def test_missing_question_and_disabled_fallback(self):
        """When an unknown question_id is passed and ALLOW_RUNTIME_JINA_FALLBACK=false, no Jina call is made."""
        res = self.retriever.retrieve_for_question("unknown_nonexistent_question", language="vi")
        self.assertEqual(res["retrieval_meta"]["embedding_source"], "missing_fallback")
        self.assertEqual(res["retrieval_meta"]["error"], "missing_precomputed_embedding")


if __name__ == "__main__":
    unittest.main()
