import pytest

from app.ingestion import IngestionError, compute_document_id, extract_pages, validate_pdf_upload
from app.utils import sanitize_filename
from tests.conftest import make_pdf

MB = 1024 * 1024


def test_extracts_text_page_by_page_with_metadata(sample_pdf):
    result = extract_pages(sample_pdf, "sample.pdf")

    assert result.page_count == 3
    assert [p.page_number for p in result.pages] == [1, 3]
    assert result.empty_pages == [2]
    assert "photovoltaic" in result.pages[0].text
    assert "refund" in result.pages[1].text
    assert all(p.doc_name == "sample.pdf" and p.doc_id == result.doc_id for p in result.pages)


def test_document_id_is_content_hash(sample_pdf):
    assert compute_document_id(sample_pdf) == compute_document_id(bytes(sample_pdf))
    assert compute_document_id(sample_pdf) != compute_document_id(make_pdf(["different content here"]))
    assert extract_pages(sample_pdf, "a.pdf").doc_id == extract_pages(sample_pdf, "b.pdf").doc_id


def test_pdf_without_text_returns_no_pages_and_a_warning():
    result = extract_pages(make_pdf(["", ""]), "scan.pdf")
    assert result.pages == []
    assert result.empty_pages == [1, 2]
    assert any("No extractable text" in w for w in result.warnings)


def test_mostly_empty_pdf_warns():
    result = extract_pages(make_pdf(["Some real text on the first page of the file.", "", ""]), "x.pdf")
    assert len(result.pages) == 1
    assert any("2 of 3 pages" in w for w in result.warnings)


def test_malformed_pdf_raises_ingestion_error():
    with pytest.raises(IngestionError):
        extract_pages(b"%PDF-1.7\nthis is not really a pdf \x00\x01\x02", "broken.pdf")


@pytest.mark.parametrize(
    "filename, data, message",
    [
        ("notes.txt", b"%PDF-1.4 ...", "not a .pdf"),
        ("empty.pdf", b"", "empty"),
        ("fake.pdf", b"MZ\x90\x00 executable bytes", "does not look like a PDF"),
    ],
)
def test_validate_rejects_invalid_uploads(filename, data, message):
    with pytest.raises(IngestionError, match=message):
        validate_pdf_upload(filename, data, max_bytes=5 * MB)


def test_validate_rejects_oversized_upload(sample_pdf):
    with pytest.raises(IngestionError, match="upload limit"):
        validate_pdf_upload("big.pdf", sample_pdf, max_bytes=len(sample_pdf) - 1)


def test_validate_accepts_real_pdf(sample_pdf):
    validate_pdf_upload("ok.pdf", sample_pdf, max_bytes=5 * MB)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("..\\..\\Windows\\system32\\evil.pdf", "evil.pdf"),
        ("report <final>?.pdf", "report _final_.pdf"),
        ("", "document.pdf"),
        ("...", "document.pdf"),
    ],
)
def test_sanitize_filename_blocks_traversal_and_odd_characters(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_but_keeps_extension():
    name = sanitize_filename("a" * 500 + ".pdf", max_length=50)
    assert len(name) == 50 and name.endswith(".pdf")


def test_service_upload_detects_duplicates_and_stores_by_hash(service, sample_pdf):
    first, dup1 = service.upload("../report.pdf", sample_pdf)
    second, dup2 = service.upload("renamed.pdf", sample_pdf)

    assert (dup1, dup2) == (False, True)
    assert first.doc_id == second.doc_id
    assert first.filename == "report.pdf"
    assert len(service.list_documents()) == 1
    stored = list(service.settings.raw_dir.iterdir())
    assert [p.name for p in stored] == [f"{first.doc_id}.pdf"]


def test_service_marks_textless_pdf_as_failed(service):
    record, _ = service.upload("scan.pdf", make_pdf(["", ""]))
    [(processed, skipped)] = service.process([record.doc_id])
    assert not skipped
    assert processed.status == "failed"
    assert "No text" in processed.error
    assert service.store.size == 0


def test_malformed_pdf_error_does_not_expose_parser_internals():
    with pytest.raises(IngestionError) as info:
        extract_pages(b"%PDF-1.7\n garbage that is not a pdf body", "broken.pdf")
    assert str(info.value) == "Could not open 'broken.pdf': the file is damaged or not a valid PDF"


def test_text_volume_is_capped(monkeypatch):
    from app import ingestion

    monkeypatch.setattr(ingestion, "MAX_TEXT_CHARS", 100)
    pdf = make_pdf(["A sentence with enough words to count as real page text. " * 3] * 3)
    with pytest.raises(IngestionError, match="more than 100 characters"):
        ingestion.extract_pages(pdf, "big.pdf")
