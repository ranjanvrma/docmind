from app.models import PageText
from app.preprocessing import clean_text, find_repeated_lines, preprocess_pages


def test_empty_and_whitespace_input_returns_empty_string():
    assert clean_text("") == ""
    assert clean_text("   \n\t  \n") == ""


def test_joins_wrapped_lines_but_keeps_paragraphs():
    raw = "This sentence was wrapped\nby the PDF layout.\n\nSecond paragraph here."
    assert clean_text(raw) == "This sentence was wrapped by the PDF layout.\n\nSecond paragraph here."


def test_repairs_hyphenated_line_breaks():
    assert clean_text("The infor-\nmation is useful.") == "The information is useful."


def test_preserves_meaningful_punctuation_numbers_and_case():
    raw = "Revenue grew 12.5% (Q3), vs. $4.2M in 2023; see Fig. 2!"
    assert clean_text(raw) == raw


def test_removes_page_number_lines_and_extra_spaces():
    raw = "Intro   text   here.\n\n  12  \n\nPage 3 of 10\nMore text."
    assert clean_text(raw) == "Intro text here.\n\nMore text."


def test_normalizes_ligatures_and_invisible_characters():
    assert clean_text("eﬃcient​ de­sign") == "efficient design"


def test_keeps_bullet_items_on_separate_lines():
    raw = "Key points:\n- first item\n- second item"
    assert clean_text(raw) == "Key points:\n- first item\n- second item"


def _pages(texts):
    return [PageText("d", "d.pdf", i + 1, t) for i, t in enumerate(texts)]


def test_detects_and_removes_repeated_headers():
    pages = _pages([f"ACME Corp Annual Report\nUnique body text number {i}." for i in range(4)])
    assert "ACME Corp Annual Report" in find_repeated_lines(pages)
    cleaned = preprocess_pages(pages)
    assert all("ACME" not in p.text for p in cleaned)
    assert cleaned[2].text == "Unique body text number 2."


def test_no_header_detection_for_short_documents():
    assert find_repeated_lines(_pages(["Same line", "Same line"])) == set()


def test_preprocess_drops_pages_that_become_empty_and_keeps_page_numbers():
    cleaned = preprocess_pages(_pages(["Real content.", "  42  ", "More content."]))
    assert [p.page_number for p in cleaned] == [1, 3]
