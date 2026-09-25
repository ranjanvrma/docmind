import json

import numpy as np
import pytest

from app.models import Chunk
from app.retrieval import Retriever
from app.vector_store import MANIFEST_FILE, FaissVectorStore, VectorStoreError

TEXTS = {
    ("docA", 1): "Solar panels convert sunlight into electricity.",
    ("docA", 2): "Wind turbines generate power from moving air.",
    ("docB", 1): "The refund policy allows returns within thirty days.",
    ("docB", 4): "Employees must complete security training every year.",
}


def _chunks():
    return [
        Chunk(f"{doc}:p{page}:c0", doc, f"{doc}.pdf", page, 0, text) for (doc, page), text in TEXTS.items()
    ]


@pytest.fixture
def store(fake_embedder, tmp_path):
    s = FaissVectorStore(fake_embedder.dimension, fake_embedder.model_name, tmp_path / "index")
    chunks = _chunks()
    s.add(chunks, fake_embedder.embed([c.text for c in chunks]))
    return s


def test_retrieves_most_relevant_chunk_first(fake_embedder, store):
    results = Retriever(fake_embedder, store).search("what is the refund policy for returns", top_k=2)
    assert results[0].chunk.chunk_id == "docB:p1:c0"
    assert results[0].chunk.page_number == 1 and results[0].chunk.doc_name == "docB.pdf"
    assert [r.rank for r in results] == [1, 2]
    assert results[0].score >= results[1].score


def test_scores_are_cosine_similarities(fake_embedder, store):
    [top] = Retriever(fake_embedder, store).search(TEXTS[("docA", 2)], top_k=1)
    assert top.score == pytest.approx(1.0, abs=1e-5)  # identical text -> cosine 1


def test_top_k_is_respected_and_capped_by_index_size(fake_embedder, store):
    retriever = Retriever(fake_embedder, store)
    assert len(retriever.search("power", top_k=3)) == 3
    assert len(retriever.search("power", top_k=50)) == len(TEXTS)


def test_document_filter(fake_embedder, store):
    results = Retriever(fake_embedder, store).search("refund policy", top_k=5, doc_ids=["docA"])
    assert results and all(r.chunk.doc_id == "docA" for r in results)


def test_empty_index_returns_no_results(fake_embedder, tmp_path):
    empty = FaissVectorStore(fake_embedder.dimension, fake_embedder.model_name, tmp_path)
    assert Retriever(fake_embedder, empty).search("anything", top_k=5) == []


@pytest.mark.parametrize("query, top_k", [("", 5), ("   ", 5), ("ok", 0)])
def test_invalid_queries_raise(fake_embedder, store, query, top_k):
    with pytest.raises(ValueError):
        Retriever(fake_embedder, store).search(query, top_k=top_k)


def test_add_rejects_mismatched_inputs(store):
    with pytest.raises(VectorStoreError):
        store.add(_chunks()[:2], np.zeros((1, store.dimension), dtype=np.float32))
    with pytest.raises(VectorStoreError):
        store.add(_chunks()[:1], np.zeros((1, store.dimension + 1), dtype=np.float32))


def test_save_and_load_round_trip(fake_embedder, store):
    query = fake_embedder.embed_query("wind power")
    before = store.search(query, 3)
    store.save()

    loaded = FaissVectorStore.load_or_create(store.index_dir, store.dimension, store.embedding_model)
    assert loaded.size == store.size
    assert [(c.chunk_id, round(s, 5)) for c, s in loaded.search(query, 3)] == [
        (c.chunk_id, round(s, 5)) for c, s in before
    ]


def test_remove_document_keeps_index_and_metadata_in_sync(fake_embedder, store):
    assert store.remove_document("docB") == 2
    assert store.size == 2 and store.document_ids() == {"docA"}
    results = store.search(fake_embedder.embed_query("refund policy"), 5)
    assert all(c.doc_id == "docA" for c, _ in results)

    # IDs must not be reused after removal, or old metadata could be overwritten.
    new = Chunk("docC:p1:c0", "docC", "docC.pdf", 1, 0, "Brand new chunk about refunds.")
    store.add([new], fake_embedder.embed([new.text]))
    store.save()
    reloaded = FaissVectorStore.load_or_create(store.index_dir, store.dimension, store.embedding_model)
    assert reloaded.document_ids() == {"docA", "docC"}


def test_load_refuses_different_embedding_model(store):
    store.save()
    with pytest.raises(VectorStoreError, match="configured model"):
        FaissVectorStore.load_or_create(store.index_dir, store.dimension, "some-other-model")


def test_load_detects_out_of_sync_files(store):
    store.save()
    manifest_path = store.index_dir / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text())
    manifest["size"] += 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(VectorStoreError, match="mismatch"):
        FaissVectorStore.load_or_create(store.index_dir, store.dimension, store.embedding_model)


def test_service_does_not_reembed_processed_documents(service, sample_pdf, fake_embedder, monkeypatch):
    record, _ = service.upload("sample.pdf", sample_pdf)
    [(first, skipped)] = service.process()
    assert first.status == "processed" and not skipped
    size = service.store.size

    calls = []
    original = fake_embedder.embed
    monkeypatch.setattr(fake_embedder, "embed", lambda texts: calls.append(texts) or original(texts))
    [(_, skipped_again)] = service.process([record.doc_id])
    assert skipped_again and calls == [] and service.store.size == size

    service.process([record.doc_id], force=True)  # forced re-processing replaces, not duplicates
    assert calls and service.store.size == size
