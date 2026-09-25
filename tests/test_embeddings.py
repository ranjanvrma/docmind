"""Embedding tests.

The first group uses a fake encoder to test the Embedder wrapper itself. The
second group loads the real sentence-transformer model (downloaded on first
use) and is skipped automatically if the model cannot be loaded, e.g. offline.
"""

import numpy as np
import pytest

from app.classifier import document_embedding
from app.config import Settings
from app.embeddings import Embedder, normalize_rows


class UnnormalizedEncoder:
    def encode(self, sentences, **kwargs):
        return np.array([[3.0, 4.0], [0.0, 0.0]][: len(sentences)], dtype=np.float64)


def test_embedder_returns_float32_unit_vectors_even_if_encoder_does_not_normalize():
    vectors = Embedder("fake", model=UnnormalizedEncoder()).embed(["a", "b"])
    assert vectors.dtype == np.float32
    np.testing.assert_allclose(vectors[0], [0.6, 0.8], rtol=1e-6)
    np.testing.assert_array_equal(vectors[1], [0.0, 0.0])  # zero vector stays zero, no NaN


def test_embed_empty_list(fake_embedder):
    assert fake_embedder.embed([]).shape[0] == 0


def test_query_embedding_shape(fake_embedder):
    assert fake_embedder.embed_query("hello").shape == (1, fake_embedder.dimension)


def test_document_embedding_is_normalized_mean():
    doc = document_embedding(normalize_rows(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)))
    np.testing.assert_allclose(doc, [[np.sqrt(0.5), np.sqrt(0.5)]], rtol=1e-6)
    with pytest.raises(ValueError):
        document_embedding(np.zeros((0, 2), dtype=np.float32))


@pytest.fixture(scope="module")
def real_embedder():
    embedder = Embedder(Settings().embedding_model)
    try:
        _ = embedder.model
    except Exception as exc:  # network/model download problems
        pytest.skip(f"Embedding model unavailable: {exc}")
    return embedder


def test_real_model_shape_and_normalization(real_embedder):
    vectors = real_embedder.embed(["The cat sat on the mat.", "Stock prices fell sharply today."])
    assert vectors.shape == (2, real_embedder.dimension)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5)


def test_real_model_is_deterministic(real_embedder):
    a = real_embedder.embed(["Deterministic embeddings please."])
    b = real_embedder.embed(["Deterministic embeddings please."])
    np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-6)


def test_real_model_captures_semantic_similarity(real_embedder):
    # Paraphrases share almost no words, so this only passes if the model encodes meaning.
    query, paraphrase, unrelated = real_embedder.embed(
        [
            "How do I get my money back?",
            "Customers may request a refund within 30 days.",
            "Photosynthesis converts light energy into chemical energy.",
        ]
    )
    assert float(query @ paraphrase) > float(query @ unrelated)
