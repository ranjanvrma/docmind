"""Registry <-> FAISS index consistency, and handling of damaged index files."""

import json

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app.models import DocumentRecord
from app.service import DocMindService
from app.vector_store import INDEX_FILE, MANIFEST_FILE, METADATA_FILE, VectorStoreError


def _processed_service(settings, fake_embedder, sample_pdf):
    service = DocMindService(settings, embedder=fake_embedder)
    record, _ = service.upload("sample.pdf", sample_pdf)
    [(processed, _)] = service.process()
    assert processed.status == "processed"
    return service, record.doc_id


# ------------------------------------------------------ registry/index sync


def test_failed_index_save_never_leaves_document_marked_processed(settings, fake_embedder, sample_pdf, monkeypatch):
    service = DocMindService(settings, embedder=fake_embedder)
    record, _ = service.upload("sample.pdf", sample_pdf)

    def broken_save():
        raise OSError("disk full")

    monkeypatch.setattr(service.store, "save", broken_save)
    with pytest.raises(VectorStoreError, match="could not|Failed to save"):
        service.process()

    failed = service.get_document(record.doc_id)
    assert failed.status == "failed" and "index could not be saved" in failed.error
    assert service.store.size == 0  # in-memory vectors rolled back

    # State on disk is consistent after a restart, and the document is recoverable.
    monkeypatch.undo()
    restarted = DocMindService(settings, embedder=fake_embedder)
    assert restarted.get_document(record.doc_id).status == "failed"
    [(recovered, _)] = restarted.process()
    assert recovered.status == "processed"
    assert restarted.search("refund within thirty days", top_k=1)[0].chunk.page_number == 3


def test_registry_is_not_marked_processed_before_the_index_is_saved(settings, fake_embedder, sample_pdf, monkeypatch):
    service = DocMindService(settings, embedder=fake_embedder)
    record, _ = service.upload("sample.pdf", sample_pdf)
    seen_status = []
    original_save = service.store.save
    monkeypatch.setattr(
        service.store, "save", lambda: seen_status.append(service.get_document(record.doc_id).status) or original_save()
    )
    service.process()
    assert seen_status == ["uploaded"]  # the registry still said "uploaded" while the index was being saved
    assert service.get_document(record.doc_id).status == "processed"


def test_lost_index_marks_documents_for_reprocessing_and_recovers(settings, fake_embedder, sample_pdf):
    # Simulates a crash or a deleted index directory after the registry said "processed".
    service, doc_id = _processed_service(settings, fake_embedder, sample_pdf)
    for name in (INDEX_FILE, METADATA_FILE, MANIFEST_FILE):
        (settings.index_dir / name).unlink()

    restarted = DocMindService(settings, embedder=fake_embedder)
    record = restarted.get_document(doc_id)
    assert record.status == "uploaded" and record.chunk_count == 0
    assert any("processed again" in w for w in record.warnings)

    [(reprocessed, skipped)] = restarted.process()  # "process pending documents" now picks it up
    assert not skipped and reprocessed.status == "processed"
    assert restarted.store.has_document(doc_id)


def test_index_entries_for_unprocessed_documents_are_dropped_on_startup(settings, fake_embedder, sample_pdf):
    service, doc_id = _processed_service(settings, fake_embedder, sample_pdf)
    stale = DocumentRecord.from_dict(service.get_document(doc_id).to_dict())
    stale.status = "failed"
    service.registry.upsert(stale)  # registry and index now disagree

    restarted = DocMindService(settings, embedder=fake_embedder)
    assert restarted.store.size == 0
    assert restarted.search("refund", top_k=3) == []


# ------------------------------------------------------ damaged index files


def _write(path, data: bytes):
    path.write_bytes(data)


def _strip_chunk_text(index_dir):
    # Same number of entries, but each is missing a required field.
    metadata = json.loads((index_dir / METADATA_FILE).read_text())
    for meta in metadata.values():
        del meta["text"]
    _write(index_dir / METADATA_FILE, json.dumps(metadata).encode())


@pytest.mark.parametrize(
    "damage, message",
    [
        (lambda d: (d / INDEX_FILE).unlink(), "missing"),
        (lambda d: _write(d / INDEX_FILE, b"definitely not a faiss index"), "corrupt"),
        (lambda d: _write(d / METADATA_FILE, b"{not json"), "unreadable"),
        (lambda d: _write(d / MANIFEST_FILE, b"{not json"), "unreadable"),
        (lambda d: _write(d / MANIFEST_FILE, json.dumps({"embedding_model": "x"}).encode()), "malformed"),
        (lambda d: (d / MANIFEST_FILE).unlink(), "missing"),
        (_strip_chunk_text, "inconsistent or damaged"),
    ],
)
def test_damaged_index_raises_application_error_with_recovery_hint(
    settings, fake_embedder, sample_pdf, damage, message
):
    _processed_service(settings, fake_embedder, sample_pdf)
    damage(settings.index_dir)
    with pytest.raises(VectorStoreError, match=message) as info:
        DocMindService(settings, embedder=fake_embedder)
    assert "Delete the index directory" in str(info.value)


def test_api_starts_and_explains_a_corrupt_index(settings, fake_embedder, sample_pdf, monkeypatch):
    _processed_service(settings, fake_embedder, sample_pdf)
    _write(settings.index_dir / INDEX_FILE, b"garbage")
    monkeypatch.setattr(api_module, "get_settings", lambda: settings)
    monkeypatch.setattr(api_module, "DocMindService", lambda s: DocMindService(s, embedder=fake_embedder))

    with TestClient(api_module.create_app()) as client:
        health = client.get("/api/health")
        search = client.post("/api/search", json={"query": "refund"})

    assert health.status_code == 503 and search.status_code == 503
    assert "Search index unavailable" in health.json()["detail"]
    assert "corrupt" in search.json()["detail"]
