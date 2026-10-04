"""Persistent registry of uploaded documents and their processing status.

Stored as a single JSON file (``data/processed/documents.json``). A database
would be overkill for a single-user local app; JSON is easy to inspect and the
file is small (one entry per document, no chunk text).
"""

from __future__ import annotations

import threading
from pathlib import Path

from app.models import DocumentRecord
from app.utils import StorageError, atomic_write_json, read_json


class RegistryError(StorageError):
    pass


class DocumentRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        try:
            raw = read_json(path, default={}) or {}
            self._records: dict[str, DocumentRecord] = {k: DocumentRecord.from_dict(v) for k, v in raw.items()}
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise RegistryError(
                f"The document registry {path} is unreadable ({exc.__class__.__name__}). Restore it from a "
                "backup, or delete it together with the index directory and upload the documents again."
            ) from exc

    def _save(self) -> None:
        atomic_write_json(self.path, {k: r.to_dict() for k, r in self._records.items()})

    def get(self, doc_id: str) -> DocumentRecord | None:
        with self._lock:
            return self._records.get(doc_id)

    def all(self) -> list[DocumentRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.uploaded_at)

    def upsert(self, record: DocumentRecord) -> None:
        with self._lock:
            self._records[record.doc_id] = record
            self._save()

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            if self._records.pop(doc_id, None) is None:
                return False
            self._save()
            return True

    def __len__(self) -> int:
        return len(self._records)
