"""Runtime settings (Settings page) and the evaluation lab endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.service import DocMindService
from tests.conftest import FakeLLM, make_pdf


def _service(tmp_path, fake_embedder, llm=None, **overrides):
    settings = Settings(data_dir=tmp_path / "data", chunk_size=300, chunk_overlap=50, top_k=3, **overrides)
    return DocMindService(settings, embedder=fake_embedder, llm=llm)


@pytest.fixture
def client(tmp_path, fake_embedder):
    with TestClient(create_app(_service(tmp_path, fake_embedder, llm=FakeLLM()))) as c:
        yield c


def test_get_settings_returns_values_but_never_secrets(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder, llm_api_key="sk-env-secret")
    with TestClient(create_app(svc)) as c:
        body = c.get("/api/admin/settings").json()
    assert body["values"]["chunk_size"] == 300
    assert "llm_api_key" not in body["values"]
    assert body["llm_api_key"] == {"configured": True, "source": "environment", "withheld": False}
    assert "sk-env-secret" not in json.dumps(body)
    assert body["read_only"]["embedding_model"] == "test-hashing-encoder"


def test_changes_are_validated_persisted_and_survive_restart(tmp_path, fake_embedder):
    with TestClient(create_app(_service(tmp_path, fake_embedder))) as c:
        response = c.patch("/api/admin/settings", json={"chunk_size": 120, "chunk_overlap": 20, "top_k": 7})
    assert response.status_code == 200
    assert response.json()["values"]["chunk_size"] == 120
    assert set(response.json()["overridden"]) == {"chunk_size", "chunk_overlap", "top_k"}

    restarted = _service(tmp_path, fake_embedder)
    assert (restarted.settings.chunk_size, restarted.settings.top_k) == (120, 7)

    # New processing really uses the saved chunk size.
    long_page = " ".join(f"Sentence number {i} about refunds." for i in range(30))
    restarted.upload("long.pdf", make_pdf([long_page]))
    restarted.process()
    assert all(len(c.text) <= 120 for c in restarted.store.chunks_for_document(restarted.list_documents()[0].doc_id))


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"chunk_size": 100, "chunk_overlap": 100}, "CHUNK_OVERLAP"),
        ({"top_k": 0}, "TOP_K"),
        ({"llm_effort": "turbo"}, "LLM_EFFORT"),
        ({"llm_base_url": "ftp://example.com"}, "LLM_BASE_URL"),
        ({"max_upload_mb": 500, "max_request_mb": 100}, "MAX_REQUEST_MB"),
        ({"classifier_labels": []}, "CLASSIFIER_LABELS"),
        ({"classifier_labels": ["A", "A"]}, "duplicates"),
    ],
)
def test_invalid_changes_are_rejected_and_nothing_is_saved(tmp_path, fake_embedder, payload, message):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        response = c.patch("/api/admin/settings", json=payload)
    assert response.status_code == 422 and message in response.json()["detail"]
    assert not (svc.settings.data_dir / "settings.json").exists()
    assert svc.settings.chunk_size == 300


def test_unknown_or_protected_fields_cannot_be_set(client):
    for field in ("api_token", "embedding_model", "data_dir", "cors_allow_origins", "nonsense"):
        assert client.patch("/api/admin/settings", json={field: "x"}).status_code == 422


def test_api_key_is_write_only_and_can_be_removed(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        saved = c.patch("/api/admin/settings", json={"llm_api_key": "sk-ui-secret"}).json()
        assert saved["llm_api_key"] == {"configured": True, "source": "settings", "withheld": False}
        assert "sk-ui-secret" not in json.dumps(saved) and "sk-ui-secret" not in json.dumps(c.get("/api/admin/settings").json())
        assert c.get("/api/health").json()["llm_configured"] is True

        removed = c.delete("/api/admin/settings/llm-api-key").json()
    assert removed["llm_api_key"] == {"configured": False, "source": None, "withheld": False}
    assert svc.settings.llm_api_key == ""


def test_reset_returns_to_environment_values(tmp_path, fake_embedder):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        c.patch("/api/admin/settings", json={"chunk_size": 150})
        body = c.post("/api/admin/settings/reset").json()
    assert body["values"]["chunk_size"] == 300 and body["overridden"] == []
    assert not (svc.settings.data_dir / "settings.json").exists()


def test_upload_request_limit_follows_live_settings(tmp_path, fake_embedder):
    big = b"%PDF-1.4\n" + b"0" * (3 * 1024 * 1024)
    with TestClient(create_app(_service(tmp_path, fake_embedder))) as c:
        c.patch("/api/admin/settings", json={"max_upload_mb": 1, "max_request_mb": 2})
        response = c.post("/api/documents/upload", files=[("files", ("big.pdf", big, "application/pdf"))])
    assert response.status_code == 413


def test_classifier_labels_apply_to_new_documents(tmp_path, fake_embedder, sample_pdf):
    svc = _service(tmp_path, fake_embedder)
    with TestClient(create_app(svc)) as c:
        c.patch("/api/admin/settings", json={"classifier_labels": ["Invoice", "Contract"]})
    svc.upload("s.pdf", sample_pdf)
    [(record, _)] = svc.process()
    assert set(record.classification["scores"]) == {"Invoice", "Contract"}


def test_corrupt_settings_file_is_ignored_at_startup(tmp_path, fake_embedder):
    data = tmp_path / "data"
    data.mkdir()
    (data / "settings.json").write_text("{not json", encoding="utf-8")
    assert _service(tmp_path, fake_embedder).settings.chunk_size == 300


def test_llm_connection_test(tmp_path, fake_embedder):
    with TestClient(create_app(_service(tmp_path, fake_embedder, llm=FakeLLM("OK")))) as c:
        ok = c.post("/api/admin/settings/test-llm").json()
    assert ok["ok"] is True and ok["latency_ms"] is not None

    with TestClient(create_app(_service(tmp_path / "b", fake_embedder))) as c:
        missing = c.post("/api/admin/settings/test-llm").json()
    assert missing["ok"] is False and "LLM_API_KEY" in missing["message"]


def test_settings_and_evaluation_require_the_token(tmp_path, fake_embedder):
    with TestClient(create_app(_service(tmp_path, fake_embedder, api_token="tok"))) as c:
        assert c.get("/api/admin/settings").status_code == 401
        assert c.patch("/api/admin/settings", json={"top_k": 4}).status_code == 401
        assert c.post("/api/admin/settings/reset").status_code == 401
        assert c.post("/api/admin/evaluation/retrieval").status_code == 401


def test_evaluation_lab_reports_metrics_for_current_settings(client):
    response = client.post("/api/admin/evaluation/retrieval", json={"ks": [1, 3]})
    assert response.status_code == 200
    body = response.json()
    assert [m["k"] for m in body["metrics"]] == [1, 3]
    assert body["n_queries"] == 20 and body["settings"]["chunk_size"] == 300
    assert 0 <= body["mrr"] <= 1
    assert "DEMO" in body["dataset_description"].upper()


def test_evaluation_rejects_bad_k(client):
    assert client.post("/api/admin/evaluation/retrieval", json={"ks": [0]}).status_code == 422


def test_environment_key_is_never_sent_to_an_endpoint_changed_from_the_ui(tmp_path, fake_embedder):
    # A token holder must not be able to redirect the server's own key to a host they control.
    svc = _service(tmp_path, fake_embedder, llm_provider="openai", llm_api_key="sk-env-secret",
                   llm_base_url="https://openrouter.ai/api/v1")
    with TestClient(create_app(svc)) as c:
        body = c.patch("/api/admin/settings", json={"llm_base_url": "https://attacker.example/v1"}).json()
        assert body["llm_api_key"] == {"configured": False, "source": "environment", "withheld": True}
        assert svc.settings.llm_api_key == ""
        assert c.post("/api/admin/settings/test-llm").json()["ok"] is False

        # Changing the model alone keeps the key; going back to the original endpoint restores it.
        c.patch("/api/admin/settings", json={"llm_base_url": "https://openrouter.ai/api/v1", "llm_model": "other/model"})
        assert svc.settings.llm_api_key == "sk-env-secret"

        # A key entered for the new endpoint is used there.
        c.patch("/api/admin/settings", json={"llm_base_url": "https://other.example/v1", "llm_api_key": "sk-new"})
        assert svc.settings.llm_api_key == "sk-new"

    # The rule also holds for overrides loaded at startup.
    (tmp_path / "data" / "settings.json").write_text(json.dumps({"llm_provider": "anthropic"}), encoding="utf-8")
    restarted = _service(tmp_path, fake_embedder, llm_provider="openai", llm_api_key="sk-env-secret")
    assert restarted.settings.llm_api_key == ""
