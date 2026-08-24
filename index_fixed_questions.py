"""
index_fixed_questions.py — Offline Indexing Script for Fixed Health Questions.

Precomputes 1024-dimensional embeddings for all 14 fixed health questions (Vietnamese & English),
saving them directly to data/fixed_question_embeddings.json for 0ms in-memory runtime retrieval.

Usage:
    python index_fixed_questions.py [--force] [--dry-run] [--language vi|en|all]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from localization import QUESTION_LABELS_EN
from rag.health_qa import QUESTION_SPECS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("index_fixed_questions")

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "fixed_question_embeddings.json"


def _compute_hash(question_id: str, language: str, text: str, query: str) -> str:
    payload = f"{question_id}:{language}:{text.strip()}:{query.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_embedder():
    """Pick Jina API Embedder if API key configured, else local embedder."""
    jina_key = os.environ.get("JINA_API_KEY", "").strip()
    if jina_key:
        from rag.api_embedder import JinaAPIEmbedder
        logger.info("Using Jina API Embedder (jina-embeddings-v3)")
        return JinaAPIEmbedder(api_key=jina_key)
    else:
        from rag.embedder import JinaEmbedder
        logger.info("Using local Jina SentenceTransformer Embedder")
        return JinaEmbedder()


def index_fixed_questions(
    languages: tuple[str, ...] = ("vi", "en"),
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing_data: dict[str, Any] = {}
    if OUTPUT_FILE.exists():
        try:
            raw = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            existing_data = raw.get("questions", {})
        except Exception as e:
            logger.warning(f"Could not read existing embeddings file: {e}")
            existing_data = {}

    to_embed: list[dict[str, Any]] = []
    stats = {"total": 0, "new": 0, "updated": 0, "unchanged": 0, "errors": 0}

    # Gather all target question specifications
    for qid, spec in QUESTION_SPECS.items():
        query = spec["query"]
        for lang in languages:
            stats["total"] += 1
            if lang == "en":
                text = QUESTION_LABELS_EN.get(qid, spec["label"])
            else:
                text = spec["label"]

            key = f"{qid}:{lang}"
            source_hash = _compute_hash(qid, lang, text, query)
            existing_item = existing_data.get(key)

            if (
                not force
                and existing_item
                and existing_item.get("source_hash") == source_hash
                and len(existing_item.get("embedding", [])) == 1024
            ):
                stats["unchanged"] += 1
                continue

            is_new = existing_item is None
            if is_new:
                stats["new"] += 1
            else:
                stats["updated"] += 1

            to_embed.append({
                "key":             key,
                "question_id":     qid,
                "language":        lang,
                "question_text":   text,
                "retrieval_query": query,
                "source_hash":     source_hash,
                "is_new":          is_new,
            })

    logger.info(
        f"Found {stats['total']} total question targets: "
        f"{stats['new']} new, {stats['updated']} changed, {stats['unchanged']} unchanged"
    )

    if dry_run:
        logger.info("[DRY RUN] No API calls made.")
        return stats

    if not to_embed:
        logger.info("All question embeddings are already up to date!")
        return stats

    embedder = _get_embedder()
    model_name = getattr(embedder, "model_name", "jina-embeddings-v3")

    for item in to_embed:
        logger.info(f"Embedding [{item['key']}]: {item['retrieval_query'][:60]}...")
        try:
            vector = embedder.embed_query(item["retrieval_query"])
            if hasattr(vector, "tolist"):
                vector = vector.tolist()

            vector = [float(x) for x in vector]
            if len(vector) != 1024:
                raise ValueError(f"Expected 1024 dimensions, got {len(vector)}")

            existing_data[item["key"]] = {
                "question_id":          item["question_id"],
                "language":             item["language"],
                "question_text":        item["question_text"],
                "retrieval_query":      item["retrieval_query"],
                "embedding_model":      model_name,
                "embedding_dimensions": len(vector),
                "source_hash":          item["source_hash"],
                "embedding":            vector,
                "updated_at":           datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed embedding [{item['key']}]: {e}")
            stats["errors"] += 1
            if item["is_new"]:
                stats["new"] -= 1
            else:
                stats["updated"] -= 1

    payload = {
        "version":              "1.0",
        "embedding_model":      model_name,
        "dimensions":           1024,
        "generated_at":         datetime.now(timezone.utc).isoformat(),
        "total_questions":      len(existing_data),
        "questions":            existing_data,
    }

    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Saved {len(existing_data)} question embeddings to {OUTPUT_FILE}")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Precompute fixed question embeddings for Daily Mate.")
    parser.add_argument("--force", action="store_true", help="Force re-embedding even if hash matches.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without calling Jina API.")
    parser.add_argument("--language", choices=["vi", "en", "all"], default="all", help="Target languages.")

    args = parser.parse_args()
    target_langs = ("vi", "en") if args.language == "all" else (args.language,)

    print("=" * 65)
    print("  Daily Mate — Precompute Fixed Question Embeddings")
    print(f"  Languages: {target_langs} | Force: {args.force} | DryRun: {args.dry_run}")
    print("=" * 65)

    res = index_fixed_questions(languages=target_langs, force=args.force, dry_run=args.dry_run)
    print("\nSummary:")
    print(f"  Total targets: {res['total']}")
    print(f"  New:           {res['new']}")
    print(f"  Updated:       {res['updated']}")
    print(f"  Unchanged:     {res['unchanged']}")
    print(f"  Errors:        {res['errors']}\n")
