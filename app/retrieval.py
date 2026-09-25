"""Semantic retrieval: query -> embedding -> FAISS search -> ranked results."""

from __future__ import annotations

import logging
import time

from app.embeddings import Embedder
from app.models import SearchResult
from app.vector_store import FaissVectorStore

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(self, embedder: Embedder, store: FaissVectorStore):
        self.embedder = embedder
        self.store = store

    def search(self, query: str, top_k: int, doc_ids: list[str] | None = None) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be empty")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        start = time.perf_counter()
        query_vector = self.embedder.embed_query(query)
        hits = self.store.search(query_vector, top_k, set(doc_ids) if doc_ids else None)
        results = [SearchResult(chunk=chunk, score=score, rank=i + 1) for i, (chunk, score) in enumerate(hits)]
        # Log sizes and timing, not the query text: queries can contain sensitive content.
        logger.info(
            "Retrieved %d/%d chunks in %.0f ms (query_chars=%d)",
            len(results),
            top_k,
            (time.perf_counter() - start) * 1000,
            len(query),
        )
        return results
