import pytest

from evaluation.evaluate import hit_at_k, precision_at_k, recall_at_k, reciprocal_rank, token_f1


def test_precision_hit_and_mrr():
    relevance = [False, True, True, False, False]
    assert precision_at_k(relevance, 1) == 0.0
    assert precision_at_k(relevance, 3) == pytest.approx(2 / 3)
    assert precision_at_k(relevance, 5) == pytest.approx(2 / 5)
    assert hit_at_k(relevance, 1) == 0.0 and hit_at_k(relevance, 2) == 1.0
    assert reciprocal_rank(relevance) == 0.5
    assert reciprocal_rank([False, False]) == 0.0


def test_precision_divides_by_k_even_if_fewer_results_returned():
    assert precision_at_k([True], 5) == pytest.approx(0.2)


def test_recall_counts_distinct_relevant_pages():
    retrieved = [("a.pdf", 1), ("a.pdf", 1), ("b.pdf", 2), ("a.pdf", 3)]
    relevant = {("a.pdf", 1), ("a.pdf", 3)}
    assert recall_at_k(retrieved, relevant, 2) == 0.5  # two chunks from the same page count once
    assert recall_at_k(retrieved, relevant, 4) == 1.0
    assert recall_at_k(retrieved, set(), 4) == 0.0


def test_token_f1_ignores_citations_case_and_punctuation():
    assert token_f1("The refund window is 30 days [1].", "refund window is 30 days") == 1.0
    assert token_f1("completely different", "refund window") == 0.0
    assert 0 < token_f1("refund within 30 days", "refunds are allowed within 30 days") < 1
