"""Background processing: queue, worker, status transitions, restart recovery."""

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.models import DocumentRecord
from app.service import DocMindService
from tests.conftest import make_pdf


def _settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", chunk_size=300, chunk_overlap=50, top_k=3)


def test_background_processing_via_api(tmp_path, fake_embedder, fake_llm, sample_pdf):
    svc = DocMindService(_settings(tmp_path), embedder=fake_embedder, llm=fake_llm)
    with TestClient(create_app(svc)) as c:
        doc_id = c.post("/api/documents/upload", files=[("files", ("a.pdf", sample_pdf, "application/pdf"))]).json()["items"][0]["doc_id"]
        r = c.post("/api/documents/process", json={"doc_ids": [doc_id], "background": True})
        assert r.status_code == 202
        assert r.json()["items"][0]["status"] in ("queued", "processing", "processed")
        assert svc.wait_for_processing(timeout=30)
        doc = c.get(f"/api/documents/{doc_id}").json()
        assert doc["status"] == "processed" and doc["chunk_count"] > 0
        assert c.post("/api/search", json={"query": "refund policy"}).json()["results"]

        # Already indexed documents are skipped unless forced.
        again = c.post("/api/documents/process", json={"doc_ids": [doc_id], "background": True}).json()
        assert again["items"][0]["skipped"] is True
        forced = c.post("/api/documents/process", json={"doc_ids": [doc_id], "force": True, "background": True}).json()
        assert forced["items"][0]["skipped"] is False
        assert svc.wait_for_processing(timeout=30)
        assert c.get(f"/api/documents/{doc_id}").json()["status"] == "processed"


def test_background_failure_is_recorded(tmp_path, fake_embedder, fake_llm):
    svc = DocMindService(_settings(tmp_path), embedder=fake_embedder, llm=fake_llm)
    record, _ = svc.upload("blank.pdf", make_pdf(["", ""]))
    svc.enqueue([record.doc_id])
    assert svc.wait_for_processing(timeout=30)
    assert svc.get_document(record.doc_id).status == "failed"
    svc.shutdown()


def test_deleting_a_queued_document_does_not_resurrect_it(tmp_path, fake_embedder, fake_llm, sample_pdf):
    svc = DocMindService(_settings(tmp_path), embedder=fake_embedder, llm=fake_llm)
    record, _ = svc.upload("a.pdf", sample_pdf)
    with svc._write_lock:  # hold the worker back while the document is deleted
        svc.enqueue([record.doc_id])
    svc.delete_document(record.doc_id)
    assert svc.wait_for_processing(timeout=30)
    assert svc.registry.get(record.doc_id) is None and svc.store.size == 0
    svc.shutdown()


def test_interrupted_processing_resumes_after_restart(tmp_path, fake_embedder, fake_llm, sample_pdf):
    settings = _settings(tmp_path)
    svc = DocMindService(settings, embedder=fake_embedder, llm=fake_llm)
    record, _ = svc.upload("a.pdf", sample_pdf)
    # Simulate a crash mid-processing: the status was persisted, the work was not done.
    crashed = DocumentRecord.from_dict(record.to_dict())
    crashed.status = "processing"
    svc.registry.upsert(crashed)

    restarted = DocMindService(settings, embedder=fake_embedder, llm=fake_llm)
    assert restarted.wait_for_processing(timeout=30)
    assert restarted.get_document(record.doc_id).status == "processed"
    restarted.shutdown()


def test_unknown_document_in_background_request_is_404(tmp_path, fake_embedder, fake_llm):
    with TestClient(create_app(DocMindService(_settings(tmp_path), embedder=fake_embedder, llm=fake_llm))) as c:
        r = c.post("/api/documents/process", json={"doc_ids": ["nope"], "background": True})
    assert r.status_code == 404
