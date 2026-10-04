"""Serving the built web UI from FastAPI, security headers, and UI-facing endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api import CONTENT_SECURITY_POLICY, create_app
from app.config import Settings
from app.service import DocMindService


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('ui')", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside dist", encoding="utf-8")
    return root


def _client(tmp_path, fake_embedder, fake_llm, **overrides):
    settings = Settings(data_dir=tmp_path / "data", chunk_size=300, chunk_overlap=50, top_k=3, **overrides)
    return TestClient(create_app(DocMindService(settings, embedder=fake_embedder, llm=fake_llm)))


def test_ui_is_served_with_spa_fallback_and_csp(tmp_path, dist, fake_embedder, fake_llm):
    with _client(tmp_path, fake_embedder, fake_llm, web_dist_dir=dist) as client:
        home = client.get("/")
        deep_link = client.get("/documents/abc123?page=2")  # client-side route
        asset = client.get("/assets/app.js")
        favicon = client.get("/favicon.svg")

    assert home.status_code == 200 and "id=root" in home.text
    assert home.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY and "unsafe-eval" not in CONTENT_SECURITY_POLICY
    assert deep_link.status_code == 200 and "id=root" in deep_link.text
    assert asset.status_code == 200 and "console.log" in asset.text
    assert favicon.status_code == 200


def test_ui_fallback_never_serves_files_outside_dist(tmp_path, dist, fake_embedder, fake_llm):
    with _client(tmp_path, fake_embedder, fake_llm, web_dist_dir=dist) as client:
        response = client.get("/..%2Fsecret.txt")
    assert "outside dist" not in response.text


def test_api_paths_never_fall_through_to_the_ui(tmp_path, dist, fake_embedder, fake_llm):
    with _client(tmp_path, fake_embedder, fake_llm, web_dist_dir=dist) as client:
        response = client.get("/api/does-not-exist")
        docs = client.get("/api/docs")
    assert response.status_code == 404 and response.json() == {"detail": "Not found"}
    assert docs.status_code == 200 and "swagger" in docs.text.lower()


def test_without_a_build_only_the_api_is_served(tmp_path, fake_embedder, fake_llm):
    with _client(tmp_path, fake_embedder, fake_llm, web_dist_dir=tmp_path / "missing") as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200


def test_security_headers_on_api_responses(tmp_path, fake_embedder, fake_llm):
    with _client(tmp_path, fake_embedder, fake_llm) as client:
        response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_health_reports_limits_without_secrets(tmp_path, fake_embedder, fake_llm):
    with _client(
        tmp_path, fake_embedder, fake_llm, api_token="tok-secret", llm_api_key="sk-secret", max_upload_mb=7, max_pages=42,
        public_max_active_jobs=0,
    ) as client:
        body = client.get("/api/health").json()
    assert body["limits"]["max_upload_mb"] == 7 and body["limits"]["max_pages"] == 42
    assert body["limits"]["max_files_per_upload"] == 20 and body["limits"]["max_top_k"] == 20
    assert body["session_ttl_hours"] == 24
    assert "tok-secret" not in str(body) and "sk-secret" not in str(body) and "auth_required" not in body


def test_document_chunks_endpoint(tmp_path, fake_embedder, fake_llm, sample_pdf):
    with _client(tmp_path, fake_embedder, fake_llm) as client:
        doc_id = client.post(
            "/api/documents/upload", files=[("files", ("s.pdf", sample_pdf, "application/pdf"))]
        ).json()["items"][0]["doc_id"]
        client.post("/api/documents/process", json={})
        chunks = client.get(f"/api/documents/{doc_id}/chunks")
        missing = client.get("/api/documents/nope/chunks")

    assert chunks.status_code == 200
    pages = [c["page_number"] for c in chunks.json()]
    assert pages == sorted(pages) and set(pages) == {1, 3}  # page 2 of the sample is blank
    assert all(c["chunk_id"].startswith(doc_id) for c in chunks.json())
    assert missing.status_code == 404


def test_document_chunks_are_private_to_the_uploading_session(tmp_path, fake_embedder, fake_llm, sample_pdf):
    app = _client(tmp_path, fake_embedder, fake_llm).app
    with TestClient(app) as alice, TestClient(app) as bob:
        doc_id = alice.post(
            "/api/documents/upload", files=[("files", ("s.pdf", sample_pdf, "application/pdf"))]
        ).json()["items"][0]["doc_id"]
        alice.post("/api/documents/process", json={})
        assert alice.get(f"/api/documents/{doc_id}/chunks").status_code == 200
        assert bob.get(f"/api/documents/{doc_id}/chunks").status_code == 404
