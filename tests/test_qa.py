import httpx
import pytest

from app.llm import LLMError, OpenAICompatibleClient
from app.models import Chunk, SearchResult
from app.prompts import NOT_FOUND_ANSWER, build_context
from app.qa import extract_citations, is_abstention
from tests.conftest import FakeLLM


def _result(i: int, text: str = "x" * 100) -> SearchResult:
    return SearchResult(Chunk(f"d:p{i}:c0", "d", "doc.pdf", i, 0, text), score=0.5, rank=i)


def test_extract_citations_handles_common_formats():
    answer = "A [1]. B [2][3]. C [Source 4]. D [5, 6]. Not a citation: [x] or [2024 report]."
    assert extract_citations(answer) == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("In [2024] revenue rose [1].", [1]),  # regression: years were counted as citations
        ("Figures for [1999, 2000] are missing.", []),
        ("The value [1480] appears in the table [2].", [2]),
        ("Out-of-range marker [12] is still a citation.", [12]),
        ("Cited twice [3][Source 3].", [3, 3]),
    ],
)
def test_bracketed_years_and_values_are_not_citations(answer, expected):
    assert extract_citations(answer) == expected


def test_bracketed_year_does_not_produce_invalid_citation_warning(service, sample_pdf, fake_llm):
    service.upload("sample.pdf", sample_pdf)
    service.process()
    fake_llm.answer = "Under the [2024] policy, refunds are allowed within thirty days [1]."
    result = service.ask("What is the refund policy?", top_k=2)
    assert result.invalid_citations == []
    assert result.cited_numbers == {1}


def test_abstention_detection():
    assert is_abstention(NOT_FOUND_ANSWER)
    assert is_abstention("I could not find the answer in the uploaded documents. The sources discuss X.")
    assert not is_abstention("The policy allows refunds [1].")


def test_context_is_numbered_and_respects_character_budget():
    results = [_result(i) for i in range(1, 6)]
    context, included = build_context(results, max_chars=400)
    assert 1 <= len(included) < 5
    assert "[Source 1] (document: doc.pdf, page: 1)" in context
    assert f"[Source {len(included) + 1}]" not in context


def test_context_always_includes_at_least_one_source():
    _, included = build_context([_result(1, "y" * 5000)], max_chars=100)
    assert len(included) == 1


def test_ask_grounds_answer_in_retrieved_chunks(service, sample_pdf, fake_llm):
    service.upload("sample.pdf", sample_pdf)
    service.process()
    fake_llm.answer = "Refunds are allowed within thirty days [1]. Also see [9]."

    result = service.ask("What is the refund policy?", top_k=2)

    system_prompt, user_prompt = fake_llm.calls[-1]
    assert "ONLY the document excerpts" in system_prompt
    assert "refund policy allows customers" in user_prompt  # retrieved chunk made it into the prompt
    assert result.sources[0].chunk.page_number == 3
    assert result.cited_numbers == {1}
    assert result.invalid_citations == [9]  # hallucinated source number is flagged, not shown as a source
    assert result.answered_from_documents


def test_ask_with_empty_index_does_not_call_llm(service, fake_llm):
    result = service.ask("Anything at all?")
    assert fake_llm.calls == []
    assert result.answer == NOT_FOUND_ANSWER and result.sources == []
    assert not result.answered_from_documents


def test_abstaining_answer_is_not_marked_as_grounded(service, sample_pdf):
    service.upload("sample.pdf", sample_pdf)
    service.process()
    service._llm = FakeLLM(NOT_FOUND_ANSWER)
    assert not service.ask("Who won the 1998 World Cup?").answered_from_documents


def _client(handler) -> OpenAICompatibleClient:
    return OpenAICompatibleClient("key", "m", 100, 5, transport=httpx.MockTransport(handler))


def test_openai_compatible_client_parses_response_and_sends_prompts():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer key"
        assert "SYS" in body and "USER" in body
        return httpx.Response(200, json={"choices": [{"message": {"content": " hello [1] "}}]})

    assert _client(handler).generate("SYS", "USER") == "hello [1]"


@pytest.mark.parametrize(
    "response, message",
    [
        (httpx.Response(401, json={}), "API key"),
        (httpx.Response(429, json={}), "rate limit"),
        (httpx.Response(500, text="boom"), "HTTP 500"),
        (httpx.Response(200, json={"unexpected": True}), "Unexpected response"),
        (httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), "empty"),
    ],
)
def test_openai_compatible_client_errors(response, message):
    with pytest.raises(LLMError, match=message):
        _client(lambda request: response).generate("s", "u")
