"""Conservative text cleaning for PDF-extracted text.

PDF text layers are full of layout artifacts: hard line breaks in the middle of
sentences, words hyphenated across lines, page numbers, running headers and
footers. The goal here is to remove those artifacts *without* changing the
meaning of the text: punctuation, casing, numbers and symbols are kept, because
the LLM needs the original wording. (The default embedding model lowercases
its input internally, so casing only matters for the text the LLM sees.)
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.models import PageText

# Characters that commonly leak out of PDFs and carry no meaning.
_INVISIBLE_CHARS = dict.fromkeys(map(ord, "­​‌‍﻿"), None)
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}

_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")
# "Page 3", "Page 3 of 10", "page 3/10": explicit labels, safe to drop anywhere.
_PAGE_LABEL_LINE = re.compile(r"^\s*page\s+\d{1,4}(\s*(/|of)\s*\d{1,4})?\s*$", re.IGNORECASE)
# "3", "3 of 10", "3/10": ambiguous. A lone number may be a year or a table cell.
_BARE_PAGE_NUMBER_LINE = re.compile(r"^\s*(\d{1,4})(\s*(/|of)\s*\d{1,4})?\s*$", re.IGNORECASE)
_BULLET_LINE = re.compile(r"^\s*([-*•●▪]|\d{1,2}[.)])\s+")
_MULTI_SPACE = re.compile(r"[ \t\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def normalize_unicode(text: str) -> str:
    for ligature, replacement in _LIGATURES.items():
        text = text.replace(ligature, replacement)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_INVISIBLE_CHARS)
    # Drop control characters except newline and tab.
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")


def _join_wrapped_lines(text: str) -> str:
    """Merge lines that were wrapped by the PDF layout into paragraphs.

    A blank line marks a paragraph break. Bullet/numbered list items start a
    new line so lists are not flattened into one sentence.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    merged: list[str] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        if not lines:
            continue
        out = lines[0]
        for line in lines[1:]:
            out += ("\n" if _BULLET_LINE.match(line) else " ") + line
        merged.append(out)
    return "\n\n".join(merged)


def _remove_page_number_lines(lines: list[str], page_number: int | None) -> list[str]:
    """Drop printed page numbers without deleting legitimate numeric lines.

    Explicit labels ("Page 3 of 10") are removed wherever they appear. A bare
    number ("3", "3 / 10") is removed only when it is the first or last
    non-empty line of the page *and* equals that page's number: that is where
    PDF headers/footers put page numbers, while years and table values on
    their own line are kept. Documents whose printed numbering is offset from
    the physical page (e.g. roman-numeral front matter) keep the stray number,
    which is harmless compared with deleting real data.
    """
    content = [i for i, line in enumerate(lines) if line.strip()]
    edges = {content[0], content[-1]} if content else set()
    kept: list[str] = []
    for i, line in enumerate(lines):
        if _PAGE_LABEL_LINE.match(line):
            continue
        if page_number is not None and i in edges:
            match = _BARE_PAGE_NUMBER_LINE.match(line)
            if match and int(match.group(1)) == page_number:
                continue
        kept.append(line)
    return kept


def clean_text(text: str, page_number: int | None = None) -> str:
    """Clean a single page of extracted text. Returns '' for empty input.

    ``page_number`` (1-based) enables removal of bare page numbers at the top
    or bottom of the page; without it only explicit "Page N" labels are removed.
    """
    if not text or not text.strip():
        return ""
    text = normalize_unicode(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # "infor-\nmation" -> "information". Only when both sides are word chars,
    # so genuine dashes and ranges like "2019-\n2020" at line ends are rare casualties.
    text = _HYPHEN_LINEBREAK.sub(r"\1\2", text)
    text = "\n".join(_remove_page_number_lines(text.split("\n"), page_number))
    text = _MULTI_SPACE.sub(" ", text)
    text = _join_wrapped_lines(text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def find_repeated_lines(pages: list[PageText], min_pages: int = 3, threshold: float = 0.6) -> set[str]:
    """Detect running headers/footers: short lines that repeat on most pages."""
    if len(pages) < min_pages:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        unique_lines = {line.strip() for line in page.text.split("\n") if 0 < len(line.strip()) <= 80}
        counts.update(unique_lines)
    cutoff = threshold * len(pages)
    return {line for line, count in counts.items() if count >= cutoff}


def preprocess_pages(pages: list[PageText]) -> list[PageText]:
    """Remove repeated headers/footers, clean each page, and drop pages left empty."""
    repeated = find_repeated_lines(pages)
    cleaned: list[PageText] = []
    for page in pages:
        text = page.text
        if repeated:
            text = "\n".join(line for line in text.split("\n") if line.strip() not in repeated)
        text = clean_text(text, page.page_number)
        if text:
            cleaned.append(PageText(page.doc_id, page.doc_name, page.page_number, text))
    return cleaned
