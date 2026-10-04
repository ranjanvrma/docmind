"""Sentence embeddings with ONNX Runtime.

DocMind runs the sentence-transformers model (all-MiniLM-L6-v2 by default)
through its official ONNX export instead of PyTorch. The vectors are the same
(cosine similarity 1.000000 against ``SentenceTransformer.encode`` on the
project's sample documents; see docs/EMBEDDINGS.md), but the runtime needs
no PyTorch: the process uses a fraction of the memory and the Docker image is
about a gigabyte smaller, which matters on free hosting tiers.

The encoder reproduces the sentence-transformers pipeline exactly:
WordPiece tokenisation (truncated to the model's ``max_seq_length``), the
transformer, then the pooling the model was trained with (mean or CLS).

Embeddings are L2-normalised, which makes the inner product of two vectors
equal to their cosine similarity. The vector store relies on this: it uses a
FAISS inner-product index, so ``score = cosine(query, chunk)``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)

ONNX_FILE = "onnx/model.onnx"
_REQUIRED_FILES = (ONNX_FILE, "tokenizer.json", "sentence_bert_config.json", "1_Pooling/config.json")


class EncoderModel(Protocol):
    """What the Embedder needs from a model (tests substitute a fast fake)."""

    def encode(self, sentences: list[str], **kwargs) -> np.ndarray: ...


class EmbeddingModelError(RuntimeError):
    """The embedding model could not be loaded."""


def download_model_files(model_name: str) -> dict[str, Path]:
    """Fetch (or reuse from the Hugging Face cache) the files the encoder needs.

    With ``HF_HUB_OFFLINE=1`` (as in the Docker image) only the local cache is used.
    """
    from huggingface_hub import hf_hub_download

    paths: dict[str, Path] = {}
    for filename in _REQUIRED_FILES:
        try:
            try:
                # Cached files need no network round-trip at startup.
                paths[filename] = Path(hf_hub_download(model_name, filename, local_files_only=True))
            except Exception:
                paths[filename] = Path(hf_hub_download(model_name, filename))
        except Exception as exc:
            raise EmbeddingModelError(
                f"Could not load '{filename}' for embedding model '{model_name}' ({exc.__class__.__name__}). "
                "DocMind needs a sentence-transformers model that ships an ONNX export (onnx/model.onnx), "
                "and network access or a pre-populated Hugging Face cache to load it."
            ) from exc
    return paths


class OnnxSentenceEncoder:
    """A sentence-transformers model executed with ONNX Runtime on the CPU."""

    def __init__(self, model_name: str):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        files = download_model_files(model_name)
        pooling = json.loads(files["1_Pooling/config.json"].read_text(encoding="utf-8"))
        if pooling.get("pooling_mode_mean_tokens"):
            self.pooling = "mean"
        elif pooling.get("pooling_mode_cls_token"):
            self.pooling = "cls"
        else:
            raise EmbeddingModelError(f"Unsupported pooling for '{model_name}': only mean or CLS pooling is supported")
        max_length = int(json.loads(files["sentence_bert_config.json"].read_text(encoding="utf-8"))["max_seq_length"])

        self.tokenizer = Tokenizer.from_file(str(files["tokenizer.json"]))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding()  # pads each batch to its longest text
        self.max_length = max_length

        options = ort.SessionOptions()
        # Release memory after large batches instead of keeping the peak
        # allocation for the life of the process (important on small instances).
        options.enable_cpu_mem_arena = False
        options.log_severity_level = 3
        self.session = ort.InferenceSession(str(files[ONNX_FILE]), options, providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self.session.get_inputs()}
        dim = self.session.get_outputs()[0].shape[-1]
        self._dimension = int(dim) if isinstance(dim, int) else None
        # ONNX Runtime sessions are thread-safe, but serialising calls keeps
        # peak memory to one batch at a time when requests overlap.
        self._lock = threading.Lock()

    def get_embedding_dimension(self) -> int | None:
        return self._dimension

    def encode(self, sentences: list[str], batch_size: int = 32, **_) -> np.ndarray:
        if not sentences:
            return np.zeros((0, self._dimension or 0), dtype=np.float32)
        # Encode similar lengths together so short texts are not padded to a long one.
        order = sorted(range(len(sentences)), key=lambda i: len(sentences[i]))
        out: list[np.ndarray | None] = [None] * len(sentences)
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            for i, vector in zip(batch, self._encode_batch([sentences[i] for i in batch])):
                out[i] = vector
        return np.vstack(out).astype(np.float32)

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encodings = self.tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feed = {"input_ids": input_ids, "attention_mask": attention}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)
        with self._lock:
            token_embeddings = self.session.run(None, feed)[0]
        if self.pooling == "cls":
            return token_embeddings[:, 0]
        mask = attention[..., None].astype(np.float32)
        return (token_embeddings * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)


@lru_cache(maxsize=2)
def load_encoder(model_name: str) -> OnnxSentenceEncoder:
    """Load (and cache per process) the embedding model.

    Loading takes a second or two and tens of MB of RAM, so it happens once per
    process, never per request.
    """
    start = time.perf_counter()
    encoder = OnnxSentenceEncoder(model_name)
    logger.info("Loaded embedding model %s (ONNX, %s pooling) in %.1fs", model_name, encoder.pooling, time.perf_counter() - start)
    return encoder


class Embedder:
    def __init__(self, model_name: str, batch_size: int = 32, model: EncoderModel | None = None):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = model
        self._dimension: int | None = None

    @property
    def model(self) -> EncoderModel:
        if self._model is None:
            self._model = load_encoder(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            getter = getattr(self.model, "get_embedding_dimension", None)
            dim = getter() if callable(getter) else None
            self._dimension = int(dim) if dim else int(self.embed(["dimension probe"]).shape[1])
        return self._dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts -> float32 array of shape (n, dim), unit-length rows."""
        if not texts:
            return np.zeros((0, self._dimension or 0), dtype=np.float32)
        vectors = np.asarray(self.model.encode(texts, batch_size=self.batch_size), dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        return normalize_rows(vectors)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query -> shape (1, dim)."""
        return self.embed([query])


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # leave all-zero vectors as zeros instead of dividing by zero
    return (vectors / norms).astype(np.float32)
