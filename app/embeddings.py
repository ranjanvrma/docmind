"""Sentence-transformer embeddings.

Embeddings are L2-normalised, which makes the inner product of two vectors
equal to their cosine similarity. The vector store relies on this: it uses a
FAISS inner-product index, so ``score = cosine(query, chunk)``.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class EncoderModel(Protocol):
    """The subset of the SentenceTransformer interface we depend on."""

    def encode(self, sentences: list[str], **kwargs) -> np.ndarray: ...


@lru_cache(maxsize=2)
def load_sentence_transformer(model_name: str):
    """Load (and cache per process) a SentenceTransformer model.

    Loading takes seconds and hundreds of MB of RAM, so it must happen once,
    not per request. The import is local so that modules which only need the
    Embedder type (and tests using a fake encoder) do not import torch.
    """
    from sentence_transformers import SentenceTransformer

    start = time.perf_counter()
    model = SentenceTransformer(model_name, device="cpu")
    logger.info("Loaded embedding model %s in %.1fs", model_name, time.perf_counter() - start)
    return model


class Embedder:
    def __init__(self, model_name: str, batch_size: int = 32, model: EncoderModel | None = None):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = model
        self._dimension: int | None = None

    @property
    def model(self) -> EncoderModel:
        if self._model is None:
            self._model = load_sentence_transformer(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # sentence-transformers >= 5 renamed the method; support both names.
            getter = getattr(self.model, "get_embedding_dimension", None) or getattr(
                self.model, "get_sentence_embedding_dimension", None
            )
            dim = getter() if callable(getter) else None
            self._dimension = int(dim) if dim else int(self.embed(["dimension probe"]).shape[1])
        return self._dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts -> float32 array of shape (n, dim), unit-length rows."""
        if not texts:
            return np.zeros((0, self._dimension or 0), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        # Re-normalise defensively: custom encoders may ignore normalize_embeddings.
        return normalize_rows(vectors)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query -> shape (1, dim)."""
        return self.embed([query])


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # leave all-zero vectors as zeros instead of dividing by zero
    return (vectors / norms).astype(np.float32)
