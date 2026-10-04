"""Public (anonymous) mode: sessions, document isolation, rate limits, CSRF, admin separation."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.service import DocMindService
from tests.conftest import FakeLLM, make_pdf

TOKEN = "admin-token-" + "x" * 24
LLM_KEY = "sk-or-v1-" + "f" * 48


def _settings(tmp_path, **overrides) -> Settings:
    base = dict(data_dir=tmp_path / "data", chunk_size=300, chunk_overlap=50, top_k=3)
    base.update(overrides)
    return Settings(**base)


def _service(tmp_path, fake_embedder, llm=None, **overrides) -> DocMindService:
    return DocMindService(_settings(tmp_path, **overrides), embedder=fake_embedder, llm=llm or FakeLLM())


def _prod(tmp_path, fake_embedder, **overrides) -> DocMindService:
    return _service(tmp_path, fake_embedder, app_env="production", api_token=TOKEN, llm_api_key=LLM_KEY, **overrides)


def _client(app, **kwargs) -> TestClient:
    # Production cookies are Secure, so production tests talk HTTPS like Render does.
    return TestClient(app, base_url="https://testserver", **kwargs)


def _upload(client, name="a.pdf", data=None, pdf=None):
    data = data if data is not None else pdf
    return client.post("/api/documents/upload", files=[("files", (name, data, "application/pdf"))])


def _upload_and_index(client, svc, pdf, name="a.pdf") -> str:
    r = _upload(client, name, pdf)
    assert r.status_code == 201, r.text
    doc_id = r.json()["items"][0]["doc_id"]
    assert client.post("/api/documents/process", json={"doc_ids": [doc_id], "background": True}).status_code == 202
    assert svc.wait_for_processing(30)
    return doc_id


# ------------------------------------------------------------ public flow
def test_visitor_uses_everything_without_a_token_in_production(tmp_path, fake_embedder, sample_pdf):
    svc = _prod(tmp_path, fake_embedder)
    with _client(create_app(svc)) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/documents").json() == []  # no session yet, no error
        doc_id = _upload_and_index(c, svc, sample_pdf)
        assert c.get("/api/documents").json()[0]["status"] == "processed"
        hits = c.post("/api/search", json={"query": "refund policy"}).json()["results"]
        assert hits and hits[0]["doc_id"] == doc_id
        answer = c.post("/api/ask", json={"question": "What is the refund policy?"}).json()
        assert answer["grounding"] == "grounded" and answer["sources"][0]["doc_id"] == doc_id
        assert c.delete(f"/api/documents/{doc_id}").status_code == 204
        assert c.get("/api/documents").json() == []


def test_session_cookie_is_server_issued_httponly_strict_and_secure(tmp_path, fake_embedder, sample_pdf):
    svc = _prod(tmp_path, fake_embedder)
    with _client(create_app(svc)) as c:
        r = _upload(c, pdf=sample_pdf)
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("docmind_session=")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie.replace("Strict", "strict") and "Secure" in cookie
    assert "Path=/api" in cookie
    value = cookie.split(";")[0].split("=", 1)[1]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", value) and value != TOKEN
    # Only a hash of the cookie is stored on the server.
    stored = (tmp_path / "data" / "sessions.json").read_text(encoding="utf-8")
    assert value not in stored and value not in (tmp_path / "data" / "processed" / "documents.json").read_text()


def test_reads_do_not_create_sessions(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        for _ in range(3):
            assert "set-cookie" not in c.get("/api/documents").headers
            c.post("/api/search", json={"query": "anything"})
    assert len(svc.sessions) == 0


# -------------------------------------------------------------- isolation
def test_one_visitor_cannot_see_or_touch_another_visitors_documents(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    app = create_app(svc)
    with TestClient(app) as alice, TestClient(app) as bob:
        a_doc = _upload_and_index(alice, svc, sample_pdf)
        b_doc = _upload_and_index(bob, svc, make_pdf(["Bob's notes about photosynthesis in leaves and chlorophyll."]))

        assert [d["doc_id"] for d in bob.get("/api/documents").json()] == [b_doc]
        for method, path, body in [
            ("GET", f"/api/documents/{a_doc}", None),
            ("GET", f"/api/documents/{a_doc}/chunks", None),
            ("DELETE", f"/api/documents/{a_doc}", None),
            ("POST", "/api/documents/process", {"doc_ids": [a_doc], "force": True}),
            ("POST", "/api/documents/process", {"doc_ids": [a_doc], "force": True, "background": True}),
            ("POST", "/api/search", {"query": "refund", "doc_ids": [a_doc]}),
            ("POST", "/api/ask", {"question": "refund?", "doc_ids": [a_doc]}),
        ]:
            r = bob.request(method, path, json=body)
            assert r.status_code == 404, (method, path, r.status_code)
            assert "refund" not in r.text.lower()

        # Unfiltered search and Q&A only ever see Bob's own document.
        hits = bob.post("/api/search", json={"query": "refund policy thirty days", "top_k": 10}).json()["results"]
        assert hits and {h["doc_id"] for h in hits} == {b_doc}
        answer = bob.post("/api/ask", json={"question": "What is the refund policy?"}).json()
        assert {s["doc_id"] for s in answer["sources"]} <= {b_doc}
        # Bob re-processing "everything" touches only his documents.
        processed = bob.post("/api/documents/process", json={"force": True}).json()["items"]
        assert [i["doc_id"] for i in processed] == [b_doc]

        # Alice's document is intact.
        assert alice.get(f"/api/documents/{a_doc}").json()["status"] == "processed"
        assert alice.post("/api/search", json={"query": "refund"}).json()["results"][0]["doc_id"] == a_doc


def test_same_pdf_uploaded_by_two_visitors_gets_separate_documents(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    app = create_app(svc)
    with TestClient(app) as alice, TestClient(app) as bob:
        a_doc = _upload_and_index(alice, svc, sample_pdf)
        b_doc = _upload_and_index(bob, svc, sample_pdf)
        assert a_doc != b_doc
        assert bob.delete(f"/api/documents/{b_doc}").status_code == 204
        assert alice.get(f"/api/documents/{a_doc}").status_code == 200
        assert alice.post("/api/search", json={"query": "refund"}).json()["results"]


def test_forged_or_unknown_session_cookie_grants_nothing(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    app = create_app(svc)
    with TestClient(app) as alice:
        a_doc = _upload_and_index(alice, svc, sample_pdf)
    for forged in ["A" * 43, "not-a-session", a_doc, next(iter(svc.sessions.owners()))]:
        with TestClient(app, cookies={"docmind_session": forged}) as mallory:
            assert mallory.get("/api/documents").json() == []
            assert mallory.get(f"/api/documents/{a_doc}").status_code == 404
            r = _upload(mallory, "m.pdf", make_pdf(["Mallory's own document about volcanoes and lava."]))
            assert r.status_code == 201
            assert r.cookies.get("docmind_session") not in (None, forged)  # a fresh server-issued session


def test_operator_documents_without_owner_are_not_public(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    record, _ = svc.upload("operator.pdf", sample_pdf)  # e.g. `python main.py ingest`
    svc.process()
    with TestClient(create_app(svc)) as c:
        assert c.get("/api/documents").json() == []
        assert c.get(f"/api/documents/{record.doc_id}").status_code == 404
        assert c.post("/api/search", json={"query": "refund"}).json()["results"] == []
        _upload(c, "mine.pdf", make_pdf(["My document about bicycles, gears and chains."]))
        c.post("/api/documents/process", json={})
        assert all(h["doc_id"] != record.doc_id for h in c.post("/api/search", json={"query": "refund"}).json()["results"])


# ------------------------------------------------------------ rate limits
def test_general_rate_limit_returns_429_with_retry_after(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_rate_limit=5, public_rate_window_seconds=60)
    with TestClient(create_app(svc)) as c:
        codes = [c.get("/api/documents").status_code for _ in range(7)]
        r = c.get("/api/documents")
        assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        assert r.json()["detail"].startswith("Too many requests")
        assert c.get("/api/health").status_code == 200  # health is never rate limited


def test_rate_limit_follows_the_ip_across_sessions(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_rate_limit=4)
    app = create_app(svc)
    with TestClient(app) as a, TestClient(app) as b:  # same IP, different cookie jars
        assert [a.get("/api/documents").status_code for _ in range(2)] == [200, 200]
        assert [b.get("/api/documents").status_code for _ in range(3)] == [200, 200, 429]


def test_question_limits_per_client_and_global(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder, public_qa_rate_limit=2)
    with TestClient(create_app(svc)) as c:
        _upload_and_index(c, svc, sample_pdf)
        codes = [c.post("/api/ask", json={"question": "refund?"}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert "Question limit" in c.post("/api/ask", json={"question": "refund?"}).json()["detail"]

    svc2 = _service(tmp_path / "g", fake_embedder, public_qa_global_limit=1)
    app = create_app(svc2)
    with TestClient(app) as a, TestClient(app, headers={"x-forwarded-for": "198.51.100.9"}) as b:
        _upload_and_index(a, svc2, sample_pdf)
        _upload_and_index(b, svc2, sample_pdf)
        assert a.post("/api/ask", json={"question": "refund?"}).status_code == 200
        r = b.post("/api/ask", json={"question": "refund?"})
        assert r.status_code == 429 and "question limit for now" in r.json()["detail"]


def test_upload_rate_limit_counts_files(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_upload_rate_limit=3)
    with TestClient(create_app(svc)) as c:
        files = [("files", (f"f{i}.pdf", make_pdf([f"Document number {i} about topic {i}."]), "application/pdf")) for i in range(2)]
        assert c.post("/api/documents/upload", files=files).status_code == 201
        r = c.post("/api/documents/upload", files=files)  # 2 more would make 4 > 3
        assert r.status_code == 429 and "Upload limit" in r.json()["detail"]


def test_new_sessions_per_ip_and_global_session_capacity(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_new_sessions_per_ip=2)
    app = create_app(svc)
    pdf = make_pdf(["A small document about rivers and lakes."])
    codes = []
    for _ in range(3):
        with TestClient(app) as c:  # a fresh cookie jar each time = cookie-dropping client
            codes.append(_upload(c, pdf=pdf).status_code)
    assert codes == [201, 201, 429]

    svc2 = _service(tmp_path / "cap", fake_embedder, public_max_sessions=1)
    app2 = create_app(svc2)
    with TestClient(app2) as a, TestClient(app2) as b:
        assert _upload(a, pdf=pdf).status_code == 201
        r = _upload(b, pdf=pdf)
        assert r.status_code == 503 and "capacity" in r.json()["detail"]


def test_documents_per_session_and_active_jobs_are_capped(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_max_documents=2, public_max_active_jobs=1)
    with TestClient(create_app(svc)) as c:
        ids = [_upload(c, f"d{i}.pdf", make_pdf([f"Text of document {i} about subject {i}."])).json()["items"][0]["doc_id"] for i in range(2)]
        r = _upload(c, "d2.pdf", make_pdf(["One document too many."]))
        assert r.status_code == 409 and "at most 2 documents" in r.json()["detail"]

        with svc._write_lock:  # keep the first job from finishing
            assert c.post("/api/documents/process", json={"doc_ids": ids[:1], "background": True}).status_code == 202
            r = c.post("/api/documents/process", json={"doc_ids": ids[1:], "background": True})
            assert r.status_code == 429 and "processing at once" in r.json()["detail"]
        assert svc.wait_for_processing(30)
        assert c.post("/api/documents/process", json={"doc_ids": ids[1:], "background": True}).status_code == 202
        assert svc.wait_for_processing(30)


def test_upload_and_page_limits_still_apply_to_visitors(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, max_upload_mb=1, max_request_mb=50, max_pages=2)
    with TestClient(create_app(svc)) as c:
        big = b"%PDF-1.7\n" + b"0" * (1024 * 1024 + 10)
        r = _upload(c, "big.pdf", big)
        assert r.status_code == 400 and "upload limit" in r.json()["detail"]
        doc_id = _upload(c, "long.pdf", make_pdf(["Page one text here.", "Page two text here.", "Page three text."])).json()["items"][0]["doc_id"]
        item = c.post("/api/documents/process", json={"doc_ids": [doc_id]}).json()["items"][0]
        assert item["status"] == "failed" and "limit is 2" in item["detail"]


# --------------------------------------------------------------- client IP
def test_client_ip_uses_only_trusted_proxy_entries(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_rate_limit=2, trusted_proxy_count=1)
    app = create_app(svc)
    # The client forges the left part; the proxy appends the real address on the right.
    with TestClient(app) as c:
        for forged in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
            r = c.get("/api/documents", headers={"x-forwarded-for": f"{forged}, 203.0.113.50"})
        assert r.status_code == 429  # all three counted against 203.0.113.50
        assert c.get("/api/documents", headers={"x-forwarded-for": "203.0.113.51"}).status_code == 200


# --------------------------------------------------------------------- CSRF
def test_cross_site_state_changes_are_blocked(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        evil = {"origin": "https://evil.example"}
        assert _upload(c, pdf=sample_pdf).status_code == 201
        doc_id = c.get("/api/documents").json()[0]["doc_id"]
        assert c.delete(f"/api/documents/{doc_id}", headers=evil).status_code == 403
        assert c.post("/api/documents/process", json={}, headers=evil).status_code == 403
        assert c.post("/api/documents/upload", files=[("files", ("x.pdf", sample_pdf, "application/pdf"))], headers=evil).status_code == 403
        assert c.post("/api/ask", json={"question": "x"}, headers={"sec-fetch-site": "cross-site"}).status_code == 403
        assert c.patch("/api/admin/settings", json={"top_k": 4}, headers=evil).status_code == 403
        # Same-origin browser requests and non-browser clients work.
        assert c.post("/api/search", json={"query": "x"}, headers={"origin": "http://testserver"}).status_code == 200
        assert c.delete(f"/api/documents/{doc_id}", headers={"sec-fetch-site": "same-origin"}).status_code == 204


# -------------------------------------------------------------------- admin
def test_admin_endpoints_require_the_token_in_production(tmp_path, fake_embedder):
    svc = _prod(tmp_path, fake_embedder)
    with _client(create_app(svc)) as c:
        admin = {"x-api-key": TOKEN}
        for method, path in [
            ("GET", "/api/admin/settings"), ("PATCH", "/api/admin/settings"), ("POST", "/api/admin/settings/reset"),
            ("DELETE", "/api/admin/settings/llm-api-key"), ("POST", "/api/admin/settings/test-llm"),
            ("POST", "/api/admin/evaluation/retrieval"), ("GET", "/api/admin/diagnostics"),
        ]:
            assert c.request(method, path, json={"top_k": 4}).status_code == 401, path
        assert c.get("/api/admin/settings", headers=admin).status_code == 200
        diag = c.get("/api/admin/diagnostics", headers=admin).json()
        assert diag["client_ip"] == "testclient" and "active_sessions" in diag
        # Old unprefixed settings routes no longer exist.
        assert c.get("/api/settings").status_code == 404
        assert c.get("/api/docs").status_code == 404 and c.get("/api/openapi.json").status_code == 404


def test_api_docs_only_when_enabled_in_production(tmp_path, fake_embedder):
    svc = _prod(tmp_path, fake_embedder, api_docs=True)
    with _client(create_app(svc)) as c:
        assert c.get("/api/docs").status_code == 200


def test_failed_admin_attempts_are_throttled_but_the_right_token_still_works(tmp_path, fake_embedder):
    svc = _prod(tmp_path, fake_embedder)
    with _client(create_app(svc)) as c:
        codes = [c.get("/api/admin/settings", headers={"x-api-key": f"guess-{i}"}).status_code for i in range(11)]
        assert codes[:10] == [401] * 10 and codes[10] == 429
        assert c.get("/api/admin/settings", headers={"x-api-key": TOKEN}).status_code == 200


def test_visitors_cannot_change_the_llm_endpoint_or_model(tmp_path, fake_embedder):
    svc = _prod(tmp_path, fake_embedder)
    with _client(create_app(svc)) as c:
        assert c.patch("/api/admin/settings", json={"llm_base_url": "https://evil.example/v1"}).status_code == 401
        assert c.post("/api/ask", json={"question": "x", "llm_base_url": "https://evil.example"}).status_code in (200, 422)
    assert svc.settings.llm_base_url == ""


# ------------------------------------------------------------------ secrets
def test_no_secret_reaches_any_public_response(tmp_path, fake_embedder, sample_pdf):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    svc = _prod(tmp_path, fake_embedder, web_dist_dir=dist)
    with _client(create_app(svc)) as c:
        bodies = [c.get("/").text, c.get("/documents").text, c.get("/api/health").text]
        r = _upload(c, pdf=sample_pdf)
        bodies += [r.text, str(r.headers)]
        doc_id = r.json()["items"][0]["doc_id"]
        bodies += [
            c.post("/api/documents/process", json={}).text,
            c.get("/api/documents").text,
            c.get(f"/api/documents/{doc_id}").text,
            c.post("/api/search", json={"query": "refund"}).text,
            c.post("/api/ask", json={"question": "refund?"}).text,
            c.get("/api/admin/settings").text,
            c.get("/api/nope").text,
        ]
    blob = "\n".join(bodies)
    assert TOKEN not in blob and LLM_KEY not in blob
    assert "owner" not in json.loads(bodies[6])[0]  # owner keys are internal


# ---------------------------------------------------------------- lifecycle
def test_idle_sessions_expire_and_their_documents_are_deleted(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder, session_ttl_hours=1)
    clock = [1_000_000.0]
    svc.sessions._clock = lambda: clock[0]
    with TestClient(create_app(svc)) as c:
        doc_id = _upload_and_index(c, svc, sample_pdf)
        raw = tmp_path / "data" / "raw" / f"{doc_id}.pdf"
        assert raw.exists() and svc.store.size > 0
        clock[0] += 3601
        assert svc.expire_sessions() == 1
        assert not raw.exists() and svc.store.size == 0 and svc.registry.get(doc_id) is None
        assert c.get("/api/documents").json() == []  # the old cookie now means "no session"


def test_sessions_and_ownership_survive_a_restart(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        doc_id = _upload_and_index(c, svc, sample_pdf)
        cookie = c.cookies.get("docmind_session")
    svc.shutdown()
    restarted = _service(tmp_path, fake_embedder)
    with TestClient(create_app(restarted), cookies={"docmind_session": cookie}) as c:
        assert [d["doc_id"] for d in c.get("/api/documents").json()] == [doc_id]
    with TestClient(create_app(restarted)) as stranger:
        assert stranger.get("/api/documents").json() == []


def test_orphaned_upload_files_are_removed_at_startup(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder)
    orphan = tmp_path / "data" / "raw" / "0123456789abcdef.pdf"
    orphan.write_bytes(b"%PDF-1.7 leftover")
    _service(tmp_path, fake_embedder)
    assert not orphan.exists()
    svc.shutdown()


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"public_rate_limit": -1}, "PUBLIC_RATE_LIMIT"),
        ({"public_rate_window_seconds": 0}, "PUBLIC_RATE_WINDOW_SECONDS"),
        ({"session_ttl_hours": 0}, "SESSION_TTL_HOURS"),
        ({"session_cookie_name": "bad name;"}, "SESSION_COOKIE_NAME"),
    ],
)
def test_public_limit_settings_are_validated(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        _settings(tmp_path, **overrides).validate()


@pytest.mark.parametrize("base_url, secure", [("http://docmind.example.com", True), ("http://127.0.0.1:8000", False), ("https://127.0.0.1", True)])
def test_production_cookie_is_secure_except_on_loopback(tmp_path, fake_embedder, sample_pdf, base_url, secure):
    svc = _prod(tmp_path, fake_embedder)
    with TestClient(create_app(svc), base_url=base_url) as c:
        cookie = _upload(c, pdf=sample_pdf).headers["set-cookie"]
    assert ("Secure" in cookie) is secure


def test_synchronous_processing_is_capped_for_visitors_too(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, public_max_active_jobs=2, public_max_documents=5)
    with TestClient(create_app(svc)) as c:
        for i in range(3):
            _upload(c, f"d{i}.pdf", make_pdf([f"Document {i} about subject number {i}."]))
        r = c.post("/api/documents/process", json={})
        assert r.status_code == 429 and "at most 2" in r.json()["detail"]
        ids = [d["doc_id"] for d in c.get("/api/documents").json()]
        assert c.post("/api/documents/process", json={"doc_ids": ids[:2]}).status_code == 200
