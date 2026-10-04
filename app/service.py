"""Application service: wires the pipeline stages together.

This is the single place where upload -> extract -> clean -> chunk -> embed ->
index -> classify is orchestrated. The FastAPI routes, the CLI and the
evaluation script all call this class, so none of them re-implement pipeline
logic.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime, timezone

from app.chunking import chunk_pages
from app.classifier import DocumentClassifier, document_embedding
from app.config import Settings
from app.embeddings import Embedder
from app.ingestion import IngestionError, compute_document_id, extract_pages, validate_pdf_upload
from app import runtime_settings
from app.llm import LLMClient, LLMError, create_llm_client
from app.models import Chunk, DocumentRecord, SearchResult
from app.preprocessing import preprocess_pages
from app.qa import QAResult, answer_question
from app.registry import DocumentRegistry
from app.retrieval import Retriever
from app.utils import StorageError, atomic_write_bytes, sanitize_filename
from app.vector_store import FaissVectorStore, VectorStoreError

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DocMindService:
    def __init__(self, settings: Settings, embedder: Embedder | None = None, llm: LLMClient | None = None):
        try:
            settings.ensure_dirs()
        except OSError as exc:
            raise StorageError(
                f"DATA_DIR {settings.data_dir} is not writable ({exc.strerror or exc}). "
                "Mount a volume the app user (UID 1000 in Docker) can write to."
            ) from exc
        # Environment values, then any overrides saved from the Settings page.
        self._env_settings = settings
        settings, self._overrides = runtime_settings.load_overrides(settings)
        self.settings = settings
        self.embedder = embedder or Embedder(settings.embedding_model, settings.embedding_batch_size)
        self.store = FaissVectorStore.load_or_create(
            settings.index_dir, self.embedder.dimension, self.embedder.model_name
        )
        self.registry = DocumentRegistry(settings.processed_dir / "documents.json")
        self._reconcile_registry_with_index()
        self.retriever = Retriever(self.embedder, self.store)
        self.classifier = DocumentClassifier(
            self.embedder, settings.classifier_labels, settings.classifier_model_path
        )
        self._llm = llm
        self._llm_injected = llm is not None  # tests inject a fake LLM; keep it across setting changes
        # Serialises index mutations (process/delete). Searches only take the
        # vector store's own read lock.
        self._write_lock = threading.Lock()
        # Background processing: one worker thread, started on first use.
        self._queue: queue.Queue[str] = queue.Queue()
        self._queue_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stopping = threading.Event()
        self._resume_interrupted_processing()

    # ------------------------------------------------------------------ LLM
    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = create_llm_client(self.settings)  # raises LLMNotConfiguredError
        return self._llm

    @property
    def llm_available(self) -> bool:
        return self._llm is not None or self.settings.llm_configured

    def test_llm(self) -> dict:
        """Make one tiny real request to the configured LLM and report the outcome."""
        start = time.perf_counter()
        try:
            reply = self.llm.generate("You are a connectivity check. Follow the instruction exactly.", "Reply with the single word: OK")
        except LLMError as exc:  # includes LLMNotConfiguredError; messages contain no provider bodies
            return {"ok": False, "message": str(exc), "latency_ms": None, "model": self.settings.llm_model}
        latency = round((time.perf_counter() - start) * 1000)
        logger.info("LLM connection test succeeded in %d ms (model=%s)", latency, self.settings.llm_model)
        return {"ok": True, "message": f"Model replied: {reply.strip()[:40]}", "latency_ms": latency, "model": self.settings.llm_model}

    # ------------------------------------------------------------- settings
    def settings_view(self) -> dict:
        view = runtime_settings.public_view(self.settings, self._overrides, self._env_settings)
        view["read_only"]["embedding_model"] = self.embedder.model_name  # the model actually loaded
        return view

    def update_settings(self, changes: dict) -> dict:
        """Validate, persist and apply setting changes. Raises ValueError if invalid."""
        with self._write_lock:
            _, coerced = runtime_settings.apply_changes(self.settings, changes)  # validates; raises ValueError
            overrides = {**self._overrides, **coerced}
            updated = runtime_settings.resolve(self._env_settings, overrides)
            runtime_settings.save_overrides(self.settings, overrides)
            self._apply_settings(updated, overrides, changed=set(coerced))
        logger.info("Settings updated: %s", ", ".join(sorted(coerced)))  # names only, never values
        return self.settings_view()

    def remove_overrides(self, names: set[str]) -> dict:
        """Drop saved overrides (e.g. the stored API key) so the environment value applies again."""
        with self._write_lock:
            remaining = {k: v for k, v in self._overrides.items() if k not in names}
            updated = runtime_settings.resolve(self._env_settings, remaining)
            runtime_settings.save_overrides(self.settings, remaining)
            self._apply_settings(updated, remaining, changed=names & set(self._overrides))
        return self.settings_view()

    def reset_settings(self) -> dict:
        with self._write_lock:
            runtime_settings.overrides_path(self.settings).unlink(missing_ok=True)
            changed = set(self._overrides)
            self._apply_settings(self._env_settings, {}, changed=changed)
        logger.info("Settings reset to environment defaults")
        return self.settings_view()

    def _apply_settings(self, settings: Settings, overrides: dict, changed: set[str]) -> None:
        self.settings, self._overrides = settings, overrides
        if changed & runtime_settings.LLM_FIELDS and not self._llm_injected:
            self._llm = None  # recreated lazily with the new provider/model/key
        if "classifier_labels" in changed:
            self.classifier = DocumentClassifier(self.embedder, settings.classifier_labels, settings.classifier_model_path)

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
            succeeded: list[DocumentRecord] = []
            for record in targets:
                current = self.registry.get(record.doc_id)
                if current is None:
                    continue  # deleted while waiting for the lock
                record = current
                if record.status == "processed" and not force and self.store.has_document(record.doc_id):
                    results.append((record, True))
                    continue
                # Work on a copy so the registry never shows "processed" before the index is saved.
                processed = self._process_one(DocumentRecord.from_dict(record.to_dict()))
                if processed.status == "processed":
                    succeeded.append(processed)
                results.append((processed, False))
                changed = True
            if changed:
                self._save_index_then_commit(succeeded)
        return results

    # ------------------------------------------------- background processing
    def enqueue(self, doc_ids: list[str] | None = None, force: bool = False) -> list[tuple[DocumentRecord, bool]]:
        """Queue documents for processing on the background worker.

        Returns (record, skipped) pairs immediately. Queued documents have
        status "queued", then "processing", then "processed" or "failed";
        clients poll the document list. Selection rules match ``process``.
        """
        with self._queue_lock:
            if doc_ids is None:
                targets = [r for r in self.registry.all() if force or r.status in ("uploaded", "failed")]
            else:
                targets = []
                for doc_id in doc_ids:
                    record = self.registry.get(doc_id)
                    if record is None:
                        raise DocumentNotFoundError(doc_id)
                    targets.append(record)
            results: list[tuple[DocumentRecord, bool]] = []
            for record in targets:
                if record.status in ("queued", "processing"):
                    results.append((record, False))  # already pending
                elif record.status == "processed" and not force and self.store.has_document(record.doc_id):
                    results.append((record, True))
                else:
                    results.append((self._queue_document(record), False))
            return results

    def _queue_document(self, record: DocumentRecord) -> DocumentRecord:
        queued = self._with_status(record, "queued")
        self._queue.put(queued.doc_id)
        self._ensure_worker()
        return queued

    def _with_status(self, record: DocumentRecord, status: str) -> DocumentRecord:
        updated = DocumentRecord.from_dict(record.to_dict())
        updated.status = status
        if status == "queued":
            updated.error = None
        self.registry.upsert(updated)
        return updated

    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._stopping.clear()
            self._worker = threading.Thread(target=self._work, name="docmind-processing", daemon=True)
            self._worker.start()

    def _work(self) -> None:
        while not self._stopping.is_set():
            try:
                doc_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                # Atomic with delete_document, so a deleted document is never resurrected.
                with self._queue_lock:
                    record = self.registry.get(doc_id)
                    if record is None or record.status != "queued":
                        continue  # deleted, or already processed synchronously
                    self._with_status(record, "processing")
                self.process([doc_id], force=True)
            except DocumentNotFoundError:
                pass  # deleted while queued
            except Exception:
                logger.exception("Background processing failed for doc_id=%s", doc_id)
            finally:
                self._queue.task_done()

    def _resume_interrupted_processing(self) -> None:
        """Re-queue documents whose processing was interrupted by a restart."""
        interrupted = [r for r in self.registry.all() if r.status in ("queued", "processing")]
        if interrupted:
            logger.info("Resuming processing of %d document(s) interrupted by a restart", len(interrupted))
            with self._queue_lock:
                for record in interrupted:
                    self._queue_document(record)

    def wait_for_processing(self, timeout: float | None = None) -> bool:
        """Block until the queue is empty (tests and the CLI). Returns False on timeout."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._queue.unfinished_tasks:
            if deadline is not None and time.monotonic() > deadline:
                return False
            time.sleep(0.05)
        return True

    def shutdown(self, timeout: float = 20.0) -> None:
        """Stop the worker after the document it is processing (if any).

        Documents still queued keep their status and are resumed on next start.
        """
        self._stopping.set()
        if self._worker is not None:
            self._worker.join(timeout)
            if self._worker.is_alive():
                logger.warning("Background processing did not finish within %.0fs; it resumes on next start", timeout)

    def _save_index_then_commit(self, succeeded: list[DocumentRecord]) -> None:
        """Persist the index first; only then mark documents as processed.

        If saving fails, the new vectors are rolled back and the documents are
        marked failed, so the registry never claims a document is indexed when
        its vectors are not on disk.
        """
        try:
            self.store.save()
        except Exception as exc:
            logger.exception("Saving the vector index failed; rolling back %d document(s)", len(succeeded))
            for record in succeeded:
                self.store.remove_document(record.doc_id)
                record.status, record.chunk_count, record.classification = "failed", 0, None
                record.error = "The search index could not be saved, so this document was not indexed. Process it again."
                self.registry.upsert(record)
            raise VectorStoreError(f"Failed to save the search index: {exc}") from exc
        for record in succeeded:
            self.registry.upsert(record)

    def _reconcile_registry_with_index(self) -> None:
        """Make the index contain exactly the documents the registry marks as processed.

        Repairs the state left by a crash or a deleted index directory:
        vectors of documents that are not "processed" are dropped, and
        "processed" documents without vectors go back to "uploaded" so that
        "process pending documents" indexes them again.
        """
        processed = {r.doc_id for r in self.registry.all() if r.status == "processed"}
        indexed = self.store.document_ids()
        for doc_id in indexed - processed:
            self.store.remove_document(doc_id)
            logger.warning("Dropped index entries for doc_id=%s (not marked processed in the registry)", doc_id)
        for doc_id in processed - indexed:
            record = DocumentRecord.from_dict(self.registry.get(doc_id).to_dict())
            record.status, record.chunk_count, record.processed_at = "uploaded", 0, None
            record.warnings = record.warnings + ["Index entries were missing; the document needs to be processed again."]
            self.registry.upsert(record)
            logger.warning("doc_id=%s was marked processed but has no index entries; marked for re-processing", doc_id)

    def _process_one(self, record: DocumentRecord) -> DocumentRecord:
        """Process one document into the in-memory index.

        Failures are written to the registry immediately. Successes are
        returned un-persisted; the caller commits them after saving the index.
        """
        start = time.perf_counter()
        # Remove stale vectors first so re-processing never duplicates chunks.
        self.store.remove_document(record.doc_id)
        record.warnings, record.error, record.classification = [], None, None
        try:
            data = self._raw_path(record.doc_id).read_bytes()
            extraction = extract_pages(
                data,
                record.filename,
                record.doc_id,
                min_chars_per_page=self.settings.min_chars_per_page,
                max_pages=self.settings.max_pages,
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
        if record.status != "processed":
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

    def get_document_chunks(self, doc_id: str) -> list[Chunk]:
        self.get_document(doc_id)  # raises DocumentNotFoundError
        return self.store.chunks_for_document(doc_id)

    def delete_document(self, doc_id: str) -> None:
        # Lock order everywhere: _write_lock, then _queue_lock.
        with self._write_lock, self._queue_lock:
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
            min_score=self.settings.min_relevance,
        )
