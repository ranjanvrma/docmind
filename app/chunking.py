"""Deterministic, sentence-aware chunking.

Design choices
--------------
* Chunks never cross page boundaries. That costs a little context at page
  breaks, but it means every chunk maps to exactly one page, so citations
  ("document X, page 7") are always exact.
* Chunks are built from whole sentences where possible. A sentence longer than
  ``chunk_size`` is split on word boundaries instead.
* Overlap is made of whole trailing sentences from the previous chunk (up to
  ``chunk_overlap`` characters), so a fact that straddles two chunks still
  appears intact in at least one of them.
* Sizes are measured in characters: simple, tokenizer-independent, and easy to
  reason about. ~800 characters is roughly 150-200 English tokens, which is
  comfortably below the 256-token limit of MiniLM-style embedding models.
"""

from __future__ import annotations

import re

from app.models import Chunk, PageText

# Split after sentence-ending punctuation followed by whitespace, or at a
# paragraph/line break. Abbreviations like "e.g." will occasionally cause an
# early split; that only affects where a chunk boundary falls, not correctness.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s and s.strip()]


def _split_long_unit(unit: str, chunk_size: int) -> list[str]:
    """Split a single over-long sentence on word boundaries."""
    pieces: list[str] = []
    current = ""
    for word in unit.split():
        # A single "word" longer than chunk_size (e.g. a URL or hash) gets hard-cut.
        while len(word) > chunk_size:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:chunk_size])
            word = word[chunk_size:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) > chunk_size:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _joined_length(units: list[str]) -> int:
    return sum(len(u) for u in units) + max(len(units) - 1, 0)


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 150) -> list[str]:
    """Split text into chunks of at most ``chunk_size`` characters."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    units: list[str] = []
    for sentence in split_sentences(text):
        units.extend(_split_long_unit(sentence, chunk_size) if len(sentence) > chunk_size else [sentence])

    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        if current and _joined_length(current + [unit]) > chunk_size:
            chunks.append(" ".join(current))
            # Carry whole trailing sentences forward as overlap.
            overlap: list[str] = []
            for prev in reversed(current):
                if _joined_length([prev] + overlap) > chunk_overlap:
                    break
                overlap.insert(0, prev)
            # Drop the overlap if it would push the next chunk over the limit.
            current = overlap if _joined_length(overlap + [unit]) <= chunk_size else []
        current.append(unit)
    if current:
        chunks.append(" ".join(current))
    return chunks


def make_chunk_id(doc_id: str, page_number: int, chunk_index: int) -> str:
    return f"{doc_id}:p{page_number}:c{chunk_index}"


def chunk_pages(pages: list[PageText], chunk_size: int = 800, chunk_overlap: int = 150) -> list[Chunk]:
    """Chunk every page and attach citation metadata to each chunk."""
    chunks: list[Chunk] = []
    for page in pages:
        for index, text in enumerate(chunk_text(page.text, chunk_size, chunk_overlap)):
            chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(page.doc_id, page.page_number, index),
                    doc_id=page.doc_id,
                    doc_name=page.doc_name,
                    page_number=page.page_number,
                    chunk_index=index,
                    text=text,
                )
            )
    return chunks
