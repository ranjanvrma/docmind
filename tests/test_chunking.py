import pytest

from app.chunking import chunk_pages, chunk_text, split_sentences
from app.models import PageText

SENTENCES = [f"This is sentence number {i} about topic {i % 3}." for i in range(40)]
TEXT = " ".join(SENTENCES)


def test_chunks_respect_size_limit():
    chunks = chunk_text(TEXT, chunk_size=200, chunk_overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_all_sentences_are_preserved_in_order():
    chunks = chunk_text(TEXT, chunk_size=200, chunk_overlap=0)
    assert " ".join(chunks) == TEXT


def test_overlap_repeats_trailing_sentences():
    chunks = chunk_text(TEXT, chunk_size=200, chunk_overlap=60)
    for previous, current in zip(chunks, chunks[1:]):
        last_sentence = split_sentences(previous)[-1]
        assert current.startswith(last_sentence)


def test_no_overlap_means_no_repetition():
    chunks = chunk_text(TEXT, chunk_size=200, chunk_overlap=0)
    joined = " ".join(chunks)
    for sentence in SENTENCES:
        assert joined.count(sentence) == 1


def test_chunking_is_deterministic():
    assert chunk_text(TEXT, 250, 80) == chunk_text(TEXT, 250, 80)


def test_long_sentence_is_split_on_word_boundaries():
    long_sentence = " ".join(["word"] * 100)  # 499 chars, no sentence punctuation
    chunks = chunk_text(long_sentence, chunk_size=100, chunk_overlap=0)
    assert all(len(c) <= 100 for c in chunks)
    assert all(set(c.split()) == {"word"} for c in chunks)


def test_giant_token_is_hard_cut():
    chunks = chunk_text("x" * 250, chunk_size=100, chunk_overlap=0)
    assert chunks == ["x" * 100, "x" * 100, "x" * 50]


def test_short_and_empty_text():
    assert chunk_text("Just one sentence.", 800, 100) == ["Just one sentence."]
    assert chunk_text("", 800, 100) == []


@pytest.mark.parametrize("size, overlap", [(0, 0), (-5, 0), (100, 100), (100, 150), (100, -1)])
def test_invalid_parameters_raise(size, overlap):
    with pytest.raises(ValueError):
        chunk_text(TEXT, size, overlap)


def test_chunk_pages_preserves_metadata_and_never_crosses_pages():
    pages = [PageText("doc1", "a.pdf", 2, TEXT), PageText("doc1", "a.pdf", 5, "Short page.")]
    chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=40)

    assert {c.page_number for c in chunks} == {2, 5}
    assert all(c.doc_id == "doc1" and c.doc_name == "a.pdf" for c in chunks)
    page5 = [c for c in chunks if c.page_number == 5]
    assert len(page5) == 1 and page5[0].text == "Short page." and page5[0].chunk_id == "doc1:p5:c0"
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    page2 = [c for c in chunks if c.page_number == 2]
    assert [c.chunk_index for c in page2] == list(range(len(page2)))
