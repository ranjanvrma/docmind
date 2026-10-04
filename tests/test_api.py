import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.service import DocMindService


@pytest.fixture
def client(service):
    with TestClient(create_app(service)) as c:
        yield c


def _upload(client, name, data):
    return client.post("/api/documents/upload", files=[("files", (name, data, "application/pdf"))])


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_configured"] is True  # fake LLM injected
    # Health is public: it must not reveal anything about other visitors' documents.
    assert "documents" not in body and "indexed_chunks" not in body


def test_full_flow_upload_process_search_ask(client, sample_pdf):
    upload = _upload(client, "sample.pdf", sample_pdf)
    assert upload.status_code == 201
    [item] = upload.json()["items"]
    assert item["status"] == "uploaded"
    doc_id = item["doc_id"]

    processed = client.post("/api/documents/process", json={"doc_ids": [doc_id]})
    assert processed.status_code == 200
    assert processed.json()["items"][0]["status"] == "processed"
    assert processed.json()["indexed_chunks"] > 0

    docs = client.get("/api/documents").json()
    assert docs[0]["doc_id"] == doc_id
    assert docs[0]["empty_pages"] == [2]
    classification = docs[0]["classification"]
    assert classification["method"] == "zero-shot"  # no trained classifier in the temp data dir
    assert classification["label"] in client.app.state.service.settings.classifier_labels
    assert set(classification["scores"]) == set(client.app.state.service.settings.classifier_labels)

    search = client.post("/api/search", json={"query": "refund within thirty days", "top_k": 2})
    assert search.status_code == 200
    top = search.json()["results"][0]
    assert top["doc_name"] == "sample.pdf" and top["page_number"] == 3

    ask = client.post("/api/ask", json={"question": "What is the refund window?"})
    assert ask.status_code == 200
    body = ask.json()
    assert body["sources"] and body["sources"][0]["source_number"] == 1
    assert body["sources"][0]["cited"] is True


def test_duplicate_upload_is_reported(client, sample_pdf):
    _upload(client, "a.pdf", sample_pdf)
    [item] = _upload(client, "b.pdf", sample_pdf).json()["items"]
    assert item["status"] == "duplicate"
    assert "a.pdf" in item["detail"]


def test_non_pdf_upload_is_rejected(client):
    response = _upload(client, "malware.exe", b"MZ\x90\x00")
    assert response.status_code == 400
    assert "not a .pdf" in response.json()["detail"]


def test_mixed_upload_reports_each_file(client, sample_pdf):
    files = [
        ("files", ("good.pdf", sample_pdf, "application/pdf")),
        ("files", ("bad.pdf", b"not a pdf at all", "application/pdf")),
    ]
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201
    assert [i["status"] for i in response.json()["items"]] == ["uploaded", "rejected"]


def test_upload_without_files_is_a_validation_error(client):
    assert client.post("/api/documents/upload").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [{"query": ""}, {"query": "   "}, {"query": "ok", "top_k": 0}, {"query": "ok", "top_k": 100}, {}],
)
def test_search_validation_errors(client, payload):
    assert client.post("/api/search", json=payload).status_code == 422


def test_ask_validation_error(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_process_unknown_document_returns_404(client):
    assert client.post("/api/documents/process", json={"doc_ids": ["nope"]}).status_code == 404


def test_get_and_delete_document(client, sample_pdf):
    doc_id = _upload(client, "sample.pdf", sample_pdf).json()["items"][0]["doc_id"]
    client.post("/api/documents/process", json={})
    assert client.get(f"/api/documents/{doc_id}").status_code == 200

    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404
    assert client.get("/api/documents").json() == []
    assert client.delete(f"/api/documents/{doc_id}").status_code == 404


def test_ask_without_llm_returns_503(settings, fake_embedder):
    service = DocMindService(settings, embedder=fake_embedder)  # no LLM, no API key
    with TestClient(create_app(service)) as c:
        assert c.get("/api/health").json()["llm_configured"] is False
        response = c.post("/api/ask", json={"question": "Hello?"})
    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]
