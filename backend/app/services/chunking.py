"""
Dynamic text chunking for embedding into Qdrant.

Not a fixed-size character slice: this splits on paragraph/sentence
boundaries and packs sentences into a chunk up to `max_chars`, so chunk
size adapts to the actual text (a short pricing page yields 1 chunk, a
long careers listing yields several) instead of always cutting at a
hardcoded offset regardless of content shape.
"""
from __future__ import annotations
import re
from typing import List

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, max_chars: int = 1200, overlap_sentences: int = 1) -> List[str]:
    """Split `text` into chunks of up to `max_chars`, breaking on sentence
    boundaries so no chunk cuts a sentence in half. `overlap_sentences`
    carries the last N sentences of a chunk into the next one, so a fact
    that straddles a chunk boundary is still fully present in at least one
    chunk (important for retrieval quality on claims like "price rose from
    X to Y", where X and Y could otherwise land in different chunks).
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences: List[str] = []
    for para in paragraphs:
        sentences.extend(s for s in _SENTENCE_SPLIT.split(para) if s.strip())

    if not sentences:
        return [text[:max_chars]]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        if current_len + len(sentence) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            current = current[-overlap_sentences:] if overlap_sentences else []
            current_len = sum(len(s) + 1 for s in current)
        current.append(sentence)
        current_len += len(sentence) + 1

    if current:
        chunks.append(" ".join(current))

    return chunks
