"""PDF validation and page-by-page text extraction with PyMuPDF."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pymupdf

from app.models import PageText
from app.utils import sha256_bytes

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
# Document IDs are a prefix of the SHA-256 of the file bytes, so uploading the
# same file twice (even under another name) maps to the same ID.
DOC_ID_LENGTH = 16
# Upper bound on text extracted from one document. A small, highly compressed
# PDF can expand to an enormous amount of text (a decompression bomb); this
# keeps memory and embedding time bounded. 5 million characters is roughly
# 2,000 dense pages, far above MAX_PAGES worth of normal documents.
MAX_TEXT_CHARS = 5_000_000


class IngestionError(Exception):
    """Raised when a file cannot be accepted or read as a PDF."""


@dataclass
class ExtractionResult:
    doc_id: str
    doc_name: str
    page_count: int
    pages: list[PageText]  # only pages that contain usable text
    empty_pages: list[int] = field(default_factory=list)  # 1-based page numbers
    warnings: list[str] = field(default_factory=list)


def compute_document_id(pdf_bytes: bytes) -> str:
    return sha256_bytes(pdf_bytes)[:DOC_ID_LENGTH]


def validate_pdf_upload(filename: str, data: bytes, max_bytes: int) -> None:
    """Cheap checks before we hand bytes to the PDF parser.

    The extension check is for user feedback; the magic-number check is what
    actually stops non-PDF content being parsed as a PDF.
    """
    if not filename.lower().endswith(".pdf"):
        raise IngestionError(f"'{filename}' is not a .pdf file")
    if not data:
        raise IngestionError(f"'{filename}' is empty")
    if len(data) > max_bytes:
        raise IngestionError(f"'{filename}' exceeds the {max_bytes // (1024 * 1024)} MB upload limit")
    # The PDF spec allows the header to appear within the first 1024 bytes.
    if PDF_MAGIC not in data[:1024]:
        raise IngestionError(f"'{filename}' does not look like a PDF (missing %PDF header)")


def extract_pages(
    pdf_bytes: bytes,
    doc_name: str,
    doc_id: str | None = None,
    min_chars_per_page: int = 20,
    max_pages: int | None = None,
) -> ExtractionResult:
    """Extract text from every page of a PDF.

    Pages with fewer than ``min_chars_per_page`` non-whitespace characters are
    recorded in ``empty_pages`` and excluded from ``pages``. Scanned PDFs have
    no text layer, so they come back with every page empty and a warning (OCR
    is out of scope for this project). Documents with more than ``max_pages``
    pages are rejected before any text is extracted.
    """
    doc_id = doc_id or compute_document_id(pdf_bytes)
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several exception types for corrupt files
        # The parser's message stays in the log; users get a stable, generic reason.
        logger.warning("PyMuPDF could not open doc_id=%s: %s", doc_id, exc)
        raise IngestionError(f"Could not open '{doc_name}': the file is damaged or not a valid PDF") from exc

    with document:
        if document.needs_pass:
            raise IngestionError(f"'{doc_name}' is password-protected")
        if document.page_count == 0:
            raise IngestionError(f"'{doc_name}' contains no pages")
        if max_pages is not None and document.page_count > max_pages:
            raise IngestionError(
                f"'{doc_name}' has {document.page_count} pages; the limit is {max_pages} (MAX_PAGES)"
            )

        pages: list[PageText] = []
        empty_pages: list[int] = []
        warnings: list[str] = []
        total_chars = 0

        for index in range(document.page_count):
            page_number = index + 1
            try:
                # sort=True orders text blocks top-to-bottom, left-to-right,
                # which gives a more natural reading order for multi-column pages.
                text = document.load_page(index).get_text("text", sort=True)
            except Exception as exc:
                logger.warning("Failed to read page %d of %s: %s", page_number, doc_id, exc)
                warnings.append(f"Page {page_number} could not be read and was skipped")
                empty_pages.append(page_number)
                continue

            total_chars += len(text)
            if total_chars > MAX_TEXT_CHARS:
                raise IngestionError(
                    f"'{doc_name}' contains more than {MAX_TEXT_CHARS:,} characters of text, "
                    "which is more than DocMind processes per document"
                )
            if len("".join(text.split())) < min_chars_per_page:
                empty_pages.append(page_number)
                continue
            pages.append(PageText(doc_id=doc_id, doc_name=doc_name, page_number=page_number, text=text))

        page_count = document.page_count

    if not pages:
        warnings.append(
            "No extractable text found. The PDF may be scanned/image-only; OCR is not supported."
        )
    elif len(empty_pages) > page_count / 2:
        warnings.append(
            f"{len(empty_pages)} of {page_count} pages had little or no extractable text "
            "(possibly scanned images)."
        )

    logger.info(
        "Extracted doc_id=%s pages=%d text_pages=%d empty_pages=%d",
        doc_id,
        page_count,
        len(pages),
        len(empty_pages),
    )
    return ExtractionResult(
        doc_id=doc_id,
        doc_name=doc_name,
        page_count=page_count,
        pages=pages,
        empty_pages=empty_pages,
        warnings=warnings,
    )
