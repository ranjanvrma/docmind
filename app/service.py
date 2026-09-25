"""Application service: wires the pipeline stages together.

This is the single place where upload -> extract -> clean -> chunk -> embed ->
index -> classify is orchestrated. The FastAPI routes, the CLI and the
evaluation script all call this class, so none of them re-implement pipeline
logic.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from app.chunking import chunk_pages
from app.classifier import DocumentClassifier, document_embedding
from app.config import Settings
from app.embeddings import Embedder
from app.ingestion import IngestionError, compute_document_id, extract_pages, validate_pdf_upload
from app.llm import LLMClient, create_llm_client
from app.models import DocumentRecord, SearchResult
from app.preprocessing import preprocess_pages
from app.qa import QAResult, answer_question
from app.registry import DocumentRegistry
from app.retrieval import Retriever
from app.utils import atomic_write_bytes, sanitize_filename
from app.vector_store import FaissVectorStore

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DocMindService:
    def __init__(self, settings: Settings, embedder: Embedder | None = None, llm: LLMClient | None = None):
        self.settings = settings
        settings.ensure_dirs()
        self.embedder = embedder or Embedder(settings.embedding_model, settings.embedding_batch_size)
        self.store = FaissVectorStore.load_or_create(
            settings.index_dir, self.embedder.dimension, self.embedder.model_name
        )
        self.registry = DocumentRegistry(settings.processed_dir / "documents.json")
        self.retriever = Retriever(self.embedder, self.store)
        self.classifier = DocumentClassifier(
            self.embedder, settings.classifier_labels, settings.classifier_model_path
        )
        self._llm = llm
        # Serialises index mutations (process/delete). Searches only take the
        # vector store's own read lock.
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------------ LLM
    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = create_llm_client(self.settings)  # raises LLMNotConfiguredError
        return self._llm

    @property
    def llm_available(self) -> bool:
        return self._llm is not None or self.settings.llm_configured

    # -------------------------------------------------------------- uploads
    def _raw_path(self, doc_id: str):
        # Files are stored under their content hash, never under the
        # user-supplied name, so a crafted filename cannot escape raw_dir.
        return self.settings.raw_dir / f"{doc_id}.pdf"

    def upload(self, filename: str, data: bytes) -> tuple[DocumentRecord, bool]:
        """Validate and store a PDF. Returns (record, is_duplicate).

        Raises IngestionError if the file is rejected.
        """
        safe_name = sanitize_filename(filename)
        validate_pdf_upload(safe_name, data, self.settings.max_upload_bytes)
        doc_id = compute_document_id(data)

        existing = self.registry.get(doc_id)
        if existing is not None:
            logger.info("Duplicate upload of doc_id=%s ignored", doc_id)
            return existing, True

        atomic_write_bytes(self._raw_path(doc_id), data)
        record = DocumentRecord(doc_id=doc_id, filename=safe_name, size_bytes=len(data), uploaded_at=_now())
        self.registry.upsert(record)
        logger.info("Stored upload doc_id=%s size=%d bytes", doc_id, len(data))
        return record, False

    # ----------------------------------------------------------- processing
    def process(self, doc_ids: list[str] | None = None, force: bool = False) -> list[tuple[DocumentRecord, bool]]:
        """Process documents into the index. Returns (record, skipped) pairs.

        Documents already processed are skipped unless ``force`` is set, so
        embeddings are never recomputed unnecessarily.
        """
        if doc_ids is None:
            targets = [r for r in self.registry.all() if force or r.status != "processed"]
        else:
            targets = []
            for doc_id in doc_ids:
                record = self.registry.get(doc_id)
                if record is None:
                    raise DocumentNotFoundError(doc_id)
                targets.append(record)

        results: list[tuple[DocumentRecord, bool]] = []
        with self._write_lock:
            changed = False
            for record in targets:
                if record.status == "processed" and not force and self.store.has_document(record.doc_id):
                    results.append((record, True))
                    continue
                results.append((self._process_one(record), False))
                changed = True
            if changed:
                self.store.save()
        return results

    def _process_one(self, record: DocumentRecord) -> DocumentRecord:
        start = time.perf_counter()
        # Remove stale vectors first so re-processing never duplicates chunks.
        self.store.remove_document(record.doc_id)
        record.warnings, record.error, record.classification = [], None, None
        try:
            data = self._raw_path(record.doc_id).read_bytes()
            extraction = extract_pages(
                data, record.filename, record.doc_id, min_chars_per_page=self.settings.min_chars_per_page
            )
            record.page_count = extraction.page_count
            record.empty_pages = extraction.empty_pages
            record.warnings = list(extraction.warnings)

            pages = preprocess_pages(extraction.pages)
            chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
            if not chunks:
                raise IngestionError("No text could be extracted from this PDF, so there is nothing to index.")

            embeddings = self.embedder.embed([c.text for c in chunks])
            self.store.add(chunks, embeddings)

            classification = self.classifier.classify(document_embedding(embeddings))
            record.classification = {
                "label": classification.label,
                "method": classification.method,
                "scores": classification.scores,
            }
            record.chunk_count = len(chunks)
            record.status = "processed"
            record.processed_at = _now()
            logger.info(
                "Processed doc_id=%s pages=%d chunks=%d label=%s in %.1fs",
                record.doc_id,
                record.page_count,
                record.chunk_count,
                classification.label,
                time.perf_counter() - start,
            )
        except FileNotFoundError:
            record.status, record.chunk_count = "failed", 0
            record.error = "The stored PDF file is missing; please upload it again."
            logger.error("Raw file missing for doc_id=%s", record.doc_id)
        except IngestionError as exc:
            record.status, record.chunk_count, record.error = "failed", 0, str(exc)
            logger.warning("Processing failed for doc_id=%s: %s", record.doc_id, exc)
        except Exception as exc:
            # Keep the index consistent even on unexpected failures.
            self.store.remove_document(record.doc_id)
            record.status, record.chunk_count = "failed", 0
            record.error = f"Unexpected error while processing: {exc.__class__.__name__}"
            logger.exception("Unexpected failure processing doc_id=%s", record.doc_id)
        self.registry.upsert(record)
        return record

    # ------------------------------------------------------------ documents
    def list_documents(self) -> list[DocumentRecord]:
        return self.registry.all()

    def get_document(self, doc_id: str) -> DocumentRecord:
        record = self.registry.get(doc_id)
        if record is None:
            raise DocumentNotFoundError(doc_id)
        return record

    def delete_document(self, doc_id: str) -> None:
        with self._write_lock:
            if self.registry.get(doc_id) is None:
                raise DocumentNotFoundError(doc_id)
            if self.store.remove_document(doc_id):
                self.store.save()
            self.registry.delete(doc_id)
            self._raw_path(doc_id).unlink(missing_ok=True)
        logger.info("Deleted doc_id=%s", doc_id)

    # ---------------------------------------------------------------- query
    def _resolve_top_k(self, top_k: int | None) -> int:
        return max(1, min(top_k or self.settings.top_k, self.settings.max_top_k))

    def search(self, query: str, top_k: int | None = None, doc_ids: list[str] | None = None) -> list[SearchResult]:
        return self.retriever.search(query, self._resolve_top_k(top_k), doc_ids)

    def ask(self, question: str, top_k: int | None = None, doc_ids: list[str] | None = None) -> QAResult:
        return answer_question(
            question,
            self.retriever,
            self.llm,
            self._resolve_top_k(top_k),
            self.settings.max_context_chars,
            doc_ids,
        )
