"""Split loaded Nutrition RAG documents into searchable chunks."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable

from .knowledge_loader import KnowledgeDocument, load_knowledge


@dataclass(frozen=True)
class KnowledgeChunk:
    """A searchable piece of a knowledge document."""

    chunk_id: str
    doc_id: str
    content: str
    metadata: dict[str, Any]


_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _sections(content: str) -> list[tuple[str, str]]:
    """Return (heading, body) sections while preserving heading context."""

    matches = list(_HEADING_RE.finditer(content))
    if not matches:
        return [("", content.strip())]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = content[: matches[0].start()].strip()
        if preamble:
            sections.append(("", preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        heading = match.group(0).strip()
        body = content[match.end() : end].strip()
        sections.append((heading, body))
    return sections


def _blocks(text: str, max_chars: int) -> list[str]:
    """Split a section into paragraph blocks, splitting oversized paragraphs."""

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    result: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            result.append(paragraph)
            continue

        sentences = [s.strip() for s in _SENTENCE_RE.split(paragraph) if s.strip()]
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                result.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            result.append(current)
    return result


def _overlap_blocks(blocks: list[str], overlap_chars: int) -> list[str]:
    selected: list[str] = []
    total = 0
    for block in reversed(blocks):
        if total and total + len(block) > overlap_chars:
            break
        selected.insert(0, block)
        total += len(block)
    return selected


def _chunk_section(
    heading: str,
    body: str,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    blocks = _blocks(body, max_chars)
    if not blocks:
        return [heading] if heading else []

    chunks: list[str] = []
    current: list[str] = []
    current_size = len(heading) + 1 if heading else 0

    for block in blocks:
        block_size = len(block) + 2
        if current and current_size + block_size > max_chars:
            chunks.append("\n\n".join(current))
            current = _overlap_blocks(current, overlap_chars)
            current_size = sum(len(item) + 2 for item in current)
        current.append(block)
        current_size += block_size

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_document(
    document: KnowledgeDocument,
    max_chars: int = 1800,
    overlap_chars: int = 250,
) -> list[KnowledgeChunk]:
    """Chunk one document while retaining its original metadata."""

    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("max_chars phải > 0 và overlap_chars phải nhỏ hơn max_chars.")

    raw_chunks: list[tuple[str, str]] = []
    for heading, body in _sections(document.content):
        for content in _chunk_section(heading, body, max_chars, overlap_chars):
            raw_chunks.append((heading, content))

    result: list[KnowledgeChunk] = []
    for index, (heading, content) in enumerate(raw_chunks):
        metadata = dict(document.metadata)
        metadata.update(
            {
                "doc_id": document.doc_id,
                "section": heading,
                "chunk_index": index,
                "chunk_count": len(raw_chunks),
            }
        )
        result.append(
            KnowledgeChunk(
                chunk_id=f"{document.doc_id}__chunk_{index:03d}",
                doc_id=document.doc_id,
                content=content,
                metadata=metadata,
            )
        )
    return result


def chunk_documents(
    documents: Iterable[KnowledgeDocument],
    max_chars: int = 1800,
    overlap_chars: int = 250,
) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, max_chars, overlap_chars))
    return chunks


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    chunks = chunk_documents(load_knowledge())
    lengths = [len(chunk.content) for chunk in chunks]
    print(f"Documents: 24")
    print(f"Chunks: {len(chunks)}")
    print(f"Min chars: {min(lengths)}")
    print(f"Max chars: {max(lengths)}")
    print(f"Average chars: {sum(lengths) // len(lengths)}")
    for chunk in chunks[:5]:
        print(f"- {chunk.chunk_id}: {chunk.metadata['section']} ({len(chunk.content)} chars)")
