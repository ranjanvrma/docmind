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


def test_removes_explicit_page_labels_anywhere_and_extra_spaces():
    raw = "Intro   text   here.\n\nPage 3 of 10\n\npage 4/10\nMore text."
    assert clean_text(raw) == "Intro text here.\n\nMore text."


def test_keeps_standalone_years_and_numeric_values():
    # Regression: number-only lines (table cells, years) used to be deleted as "page numbers".
    raw = "Year\n2023\n2024\nRevenue\n1480\n1570"
    assert clean_text(raw) == "Year 2023 2024 Revenue 1480 1570"
    assert clean_text(raw, page_number=3) == "Year 2023 2024 Revenue 1480 1570"


def test_keeps_numbers_in_the_middle_of_a_page_even_if_they_equal_the_page_number():
    assert clean_text("Totals:\n7\nend of table", page_number=7) == "Totals: 7 end of table"


def test_removes_bare_page_number_at_top_or_bottom_edge():
    assert clean_text("12\nBody text here.", page_number=12) == "Body text here."
    assert clean_text("Body text here.\n\n  12  \n", page_number=12) == "Body text here."
    assert clean_text("Body text here.\n12 / 40", page_number=12) == "Body text here."


def test_keeps_edge_number_that_does_not_match_the_page():
    # A table ending with a value, or offset printed numbering: not safe to delete.
    assert clean_text("Revenue\n1570", page_number=3) == "Revenue 1570"
    assert clean_text("Body text here.\n12") == "Body text here. 12"  # page unknown -> keep


def test_prose_with_numbers_is_unchanged_by_page_number_rules():
    raw = "In 2024 the grid produced 1,480 MWh.\nPage count: 12 pages."
    assert clean_text(raw, page_number=1) == "In 2024 the grid produced 1,480 MWh. Page count: 12 pages."


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
    # Page 2 contains only its own printed page number.
    cleaned = preprocess_pages(_pages(["Real content.", "  2  ", "More content."]))
    assert [p.page_number for p in cleaned] == [1, 3]


def test_preprocess_passes_page_numbers_through_to_cleaning():
    cleaned = preprocess_pages(_pages(["Intro text.\n1", "Table\n2023\n2", "Closing text.\n3"]))
    assert [p.text for p in cleaned] == ["Intro text.", "Table 2023", "Closing text."]
