"""FAISS vector index with persisted chunk metadata.

The store holds two things that must always agree:

* a FAISS index mapping integer IDs -> vectors, and
* a metadata dict mapping the same integer IDs -> chunk metadata (text,
  document, page).

Every mutation updates both in memory, and ``save()`` writes both files plus a
manifest. ``load()`` refuses to start if their sizes disagree or if the index
was built with a different embedding model, because silently mixing vectors
from two models produces meaningless similarity scores.

Index type: ``IndexFlatIP`` (exact inner-product search) wrapped in
``IndexIDMap2`` so vectors can be removed by ID when a document is deleted or
re-processed. Exact search is O(n * d) per query, which is fast for the tens of
thousands of chunks a local app will hold; approximate indexes (IVF, HNSW)
only pay off at much larger scale.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import faiss
import numpy as np

from app.models import Chunk
from app.utils import StorageError, atomic_write_bytes, atomic_write_json, read_json

logger = logging.getLogger(__name__)

INDEX_FILE = "index.faiss"
METADATA_FILE = "metadata.json"
MANIFEST_FILE = "manifest.json"


class VectorStoreError(StorageError):
    pass


class FaissVectorStore:
    def __init__(self, dimension: int, embedding_model: str, index_dir: Path | None = None):
        self.dimension = dimension
        self.embedding_model = embedding_model
        self.index_dir = index_dir
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        self._metadata: dict[int, dict] = {}
        self._next_id = 0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ info
    @property
    def size(self) -> int:
        return int(self._index.ntotal)

    def document_ids(self) -> set[str]:
        with self._lock:
            return {meta["doc_id"] for meta in self._metadata.values()}

    def has_document(self, doc_id: str) -> bool:
        return doc_id in self.document_ids()

    def chunks_for_document(self, doc_id: str) -> list[Chunk]:
        """All indexed chunks of one document, in page/chunk order."""
        with self._lock:
            chunks = [Chunk.from_dict(meta) for meta in self._metadata.values() if meta["doc_id"] == doc_id]
        return sorted(chunks, key=lambda c: (c.page_number, c.chunk_index))

    # ------------------------------------------------------------- mutation
    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        if len(chunks) != len(embeddings):
            raise VectorStoreError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
        if not chunks:
            return
        embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[1] != self.dimension:
            raise VectorStoreError(
                f"Embedding dimension {embeddings.shape[-1]} does not match index dimension {self.dimension}"
            )
        with self._lock:
            ids = np.arange(self._next_id, self._next_id + len(chunks), dtype=np.int64)
            self._index.add_with_ids(embeddings, ids)
            for faiss_id, chunk in zip(ids.tolist(), chunks):
                self._metadata[faiss_id] = chunk.to_dict()
            self._next_id += len(chunks)
        logger.info("Indexed %d chunks (index size now %d)", len(chunks), self.size)

    def remove_document(self, doc_id: str) -> int:
        with self._lock:
            ids = [fid for fid, meta in self._metadata.items() if meta["doc_id"] == doc_id]
            if not ids:
                return 0
            removed = self._index.remove_ids(np.array(ids, dtype=np.int64))
            for fid in ids:
                del self._metadata[fid]
        logger.info("Removed %d chunks for doc_id=%s", removed, doc_id)
        return int(removed)

    # --------------------------------------------------------------- search
    def search(
        self, query_vector: np.ndarray, top_k: int, doc_ids: set[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        """Return up to ``top_k`` (chunk, cosine score) pairs, best first."""
        if top_k <= 0 or self.size == 0:
            return []
        query = np.ascontiguousarray(query_vector, dtype=np.float32).reshape(1, -1)
        if query.shape[1] != self.dimension:
            raise VectorStoreError(
                f"Query dimension {query.shape[1]} does not match index dimension {self.dimension}"
            )
        with self._lock:
            # With a document filter we over-fetch and filter afterwards. For a
            # flat index, searching everything costs the same as searching a few.
            fetch = self.size if doc_ids else min(top_k, self.size)
            scores, ids = self._index.search(query, fetch)
            results: list[tuple[Chunk, float]] = []
            for score, fid in zip(scores[0].tolist(), ids[0].tolist()):
                if fid == -1:  # FAISS pads with -1 when fewer results exist
                    continue
                meta = self._metadata.get(fid)
                if meta is None:
                    # Should be impossible if save/load kept things in sync.
                    logger.error("FAISS id %d has no metadata; index and metadata are out of sync", fid)
                    continue
                if doc_ids and meta["doc_id"] not in doc_ids:
                    continue
                results.append((Chunk.from_dict(meta), float(score)))
                if len(results) >= top_k:
                    break
        return results

    # ---------------------------------------------------------- persistence
    def save(self) -> None:
        if self.index_dir is None:
            raise VectorStoreError("index_dir is not set; cannot save")
        with self._lock:
            # serialize_index + our own atomic write (instead of faiss.write_index)
            # avoids FAISS's C-level file I/O, which cannot handle non-ASCII
            # paths on Windows, and prevents half-written index files.
            index_bytes = faiss.serialize_index(self._index).tobytes()
            metadata = {str(fid): meta for fid, meta in self._metadata.items()}
            manifest = {
                "embedding_model": self.embedding_model,
                "dimension": self.dimension,
                "next_id": self._next_id,
                "size": self.size,
            }
            atomic_write_bytes(self.index_dir / INDEX_FILE, index_bytes)
            atomic_write_json(self.index_dir / METADATA_FILE, metadata)
            # The manifest is written last: its "size" is the consistency check on load.
            atomic_write_json(self.index_dir / MANIFEST_FILE, manifest)
        logger.info("Saved vector store (%d vectors) to %s", self.size, self.index_dir)

    @classmethod
    def load_or_create(cls, index_dir: Path, dimension: int, embedding_model: str) -> "FaissVectorStore":
        """Load the persisted index, or create an empty one if none exists.

        Every way the files can be missing, unreadable or inconsistent raises
        ``VectorStoreError`` with recovery instructions, never a raw exception.
        """
        recovery = (
            f"Delete the index directory ({index_dir}) and restart DocMind; previously processed "
            "documents will then be marked for re-processing."
        )
        try:
            manifest = read_json(index_dir / MANIFEST_FILE)
        except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
            raise VectorStoreError(f"The index manifest in {index_dir} is unreadable ({exc}). {recovery}") from exc
        if manifest is None:
            if (index_dir / INDEX_FILE).exists():
                raise VectorStoreError(f"{MANIFEST_FILE} is missing from {index_dir}. {recovery}")
            logger.info("No existing index at %s; creating a new one", index_dir)
            return cls(dimension, embedding_model, index_dir)

        try:
            built_with, built_dim = manifest["embedding_model"], int(manifest["dimension"])
            next_id, expected_size = int(manifest["next_id"]), int(manifest["size"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreError(f"The index manifest in {index_dir} is malformed. {recovery}") from exc

        if built_with != embedding_model or built_dim != dimension:
            raise VectorStoreError(
                f"The index in {index_dir} was built with '{built_with}' "
                f"(dim {built_dim}) but the configured model is '{embedding_model}' "
                f"(dim {dimension}). Delete the index directory and re-process your documents, "
                "or set EMBEDDING_MODEL back to the original model."
            )

        store = cls(dimension, embedding_model, index_dir)
        index_path = index_dir / INDEX_FILE
        if not index_path.exists():
            raise VectorStoreError(f"{INDEX_FILE} is missing from {index_dir}. {recovery}")
        try:
            raw = np.frombuffer(index_path.read_bytes(), dtype=np.uint8)
            store._index = faiss.deserialize_index(raw)
        except Exception as exc:  # FAISS raises RuntimeError for corrupt data
            raise VectorStoreError(f"{INDEX_FILE} in {index_dir} is corrupt ({exc.__class__.__name__}). {recovery}") from exc
        try:
            metadata = read_json(index_dir / METADATA_FILE) or {}
            store._metadata = {int(k): v for k, v in metadata.items()}
        except (OSError, ValueError, AttributeError) as exc:
            raise VectorStoreError(f"{METADATA_FILE} in {index_dir} is unreadable. {recovery}") from exc
        store._next_id = next_id

        required = set(Chunk.__dataclass_fields__)
        if store._index.d != dimension or not all(
            isinstance(meta, dict) and required <= meta.keys() for meta in store._metadata.values()
        ):
            raise VectorStoreError(f"The index files in {index_dir} are inconsistent or damaged. {recovery}")
        if store.size != len(store._metadata) or store.size != expected_size:
            raise VectorStoreError(
                f"Index/metadata mismatch in {index_dir}: index has {store.size} vectors, "
                f"metadata has {len(store._metadata)} entries, manifest expects {expected_size}. {recovery}"
            )
        logger.info("Loaded vector store with %d vectors from %s", store.size, index_dir)
        return store
