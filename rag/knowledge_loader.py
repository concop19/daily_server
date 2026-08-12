"""Load Nutrition RAG Markdown documents and their frontmatter.

This is the first RAG step: convert files in knowledge/ into structured
documents. It intentionally does not create embeddings or call Chroma yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    """One source document before it is split into chunks."""

    doc_id: str
    path: str
    content: str
    metadata: dict[str, Any]


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"null", "none"}:
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the small, predictable YAML frontmatter used by knowledge/*.md.

    The project currently needs only scalar values and lists. Keeping this
    parser dependency-free makes the loader usable before installing RAG
    packages. A malformed document raises ValueError instead of being silently
    indexed.
    """

    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise ValueError("Document thiếu frontmatter mở đầu bằng '---'.")

    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("Document thiếu dấu '---' kết thúc frontmatter.") from exc

    metadata: dict[str, Any] = {}
    current_list: list[Any] | None = None

    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("-"):
            if current_list is None:
                raise ValueError(f"List không có key trong frontmatter: {line}")
            current_list.append(_parse_scalar(stripped[1:].strip()))
            continue
        if ":" not in line:
            raise ValueError(f"Dòng frontmatter không hợp lệ: {line}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            raise ValueError(f"Key frontmatter rỗng: {line}")
        if raw_value:
            metadata[key] = _parse_scalar(raw_value)
            current_list = None
        else:
            metadata[key] = []
            current_list = metadata[key]

    content = "\n".join(lines[end + 1 :]).strip()
    if not metadata.get("doc_id"):
        raise ValueError("Document thiếu doc_id.")
    return metadata, content


def load_knowledge(root: str | Path = "knowledge") -> list[KnowledgeDocument]:
    """Load all indexed Markdown documents below *root*.

    KNOWLEDGE_BASE_REPORT.md is an operational report, not a retrieval source,
    so it is deliberately excluded.
    """

    root = Path(root)
    documents: list[KnowledgeDocument] = []
    for path in sorted(root.rglob("*.md")):
        if path.name == "KNOWLEDGE_BASE_REPORT.md":
            continue
        metadata, content = parse_frontmatter(path.read_text(encoding="utf-8"))
        doc_id = str(metadata["doc_id"])
        documents.append(
            KnowledgeDocument(
                doc_id=doc_id,
                path=str(path),
                content=content,
                metadata=metadata,
            )
        )
    return documents


if __name__ == "__main__":
    docs = load_knowledge()
    print(f"Loaded documents: {len(docs)}")
    for doc in docs:
        print(f"- {doc.doc_id}: {doc.metadata.get('topic')} ({len(doc.content)} chars)")

