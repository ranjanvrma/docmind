"""Shared test fixtures.

Most tests use ``HashingEncoder`` instead of a real transformer: it is a
deterministic bag-of-words embedding, so tests run in milliseconds, need no
network access, and texts that share words really are more similar. Tests in
``test_embeddings.py`` exercise the real sentence-transformer model.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pymupdf
import pytest

from app.config import Settings
from app.embeddings import Embedder
from app.llm import LLMClient
from app.service import DocMindService

DIM = 256


class HashingEncoder:
    def encode(self, sentences, **kwargs):
        vectors = np.zeros((len(sentences), DIM), dtype=np.float32)
        for row, text in enumerate(sentences):
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % DIM
                vectors[row, bucket] += 1.0
        return vectors

    def get_embedding_dimension(self):
        return DIM


class FakeLLM(LLMClient):
    """Returns a canned answer and records the prompts it received."""

    def __init__(self, answer: str = "The answer is 42 [1]."):
        self.model = "fake-llm"
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.answer


def make_pdf(pages: list[str]) -> bytes:
    """Create an in-memory PDF with one text block per page ('' = blank page)."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def fake_embedder() -> Embedder:
    return Embedder("test-hashing-encoder", model=HashingEncoder())


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", chunk_size=300, chunk_overlap=50, top_k=3)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(settings, fake_embedder, fake_llm) -> DocMindService:
    return DocMindService(settings, embedder=fake_embedder, llm=fake_llm)


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf(
        [
            "Solar panels convert sunlight into electricity using photovoltaic cells. "
            "Efficiency of modern panels is around twenty percent.",
            "",
            "The company refund policy allows customers to request a refund within thirty days of purchase. "
            "Refunds are processed to the original payment method.",
        ]
    )
