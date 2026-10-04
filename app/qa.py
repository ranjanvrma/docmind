"""Retrieval-augmented question answering.

question -> retrieve top-k chunks -> drop irrelevant/duplicate passages ->
numbered context -> LLM -> citation check -> answer

Citation honesty: the sources returned to the user are exactly the chunks that
were placed in the prompt. Citation markers in the answer are parsed and
checked against that list; a marker pointing at a source number that was never
provided (a hallucinated citation) is reported in ``invalid_citations`` rather
than shown as a real source.

Grounding: every answer is classified as

* ``grounded``   - cites at least one source that was actually provided;
* ``not_found``  - the model abstained with the agreed sentence;
* ``ungrounded`` - neither. The model is asked once more with a reminder of
  the rules (router models such as ``openrouter/free`` sometimes land on a
  model that ignores them). If the retry is still ungrounded, its text is not
  presented as an answer: the user sees an explicit "could not verify" reply,
  and the raw model output is returned separately, labelled unverified.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.llm import LLMClient, timed_generate
from app.models import SearchResult
from app.prompts import NOT_FOUND_ANSWER, SYSTEM_PROMPT, build_context, build_user_prompt
from app.retrieval import Retriever

logger = logging.getLogger(__name__)

GROUNDED, NOT_FOUND, UNGROUNDED = "grounded", "not_found", "ungrounded"
UNVERIFIED_ANSWER = (
    "I could not produce an answer that is supported by citations to your documents. "
    "Try rephrasing the question, or check the retrieved sources below."
)
RETRY_REMINDER = (
    "\n\nYour previous reply did not follow the rules: it did not cite any of the numbered sources. "
    "Reply again. Put the supporting source number in square brackets after every claim, e.g. [1]. "
    f'If the sources do not answer the question, begin your reply with exactly: "{NOT_FOUND_ANSWER}"'
)

# Matches [1], [2, 3], [Source 4] and similar. Source numbers have at most two
# digits because a prompt never holds more than max_top_k (20) sources, so
# bracketed years or values such as "[2024]" are ordinary text, not citations.
# An out-of-range marker like "[9]" with 5 sources still counts as an (invalid) citation.
_CITATION_GROUP = re.compile(r"\[(?:source\s*)?(\d{1,2}(?:\s*,\s*(?:source\s*)?\d{1,2})*)\]", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


@dataclass
class QAResult:
    question: str
    answer: str
    sources: list[SearchResult]  # the chunks that were given to the LLM, in source-number order
    cited_numbers: set[int] = field(default_factory=set)
    invalid_citations: list[int] = field(default_factory=list)
    grounding: str = NOT_FOUND
    unverified_answer: str | None = None  # raw model text when it could not be grounded
    model: str | None = None

    @property
    def answered_from_documents(self) -> bool:
        return self.grounding == GROUNDED


def extract_citations(answer: str) -> list[int]:
    numbers: list[int] = []
    for group in _CITATION_GROUP.findall(answer):
        numbers.extend(int(n) for n in re.findall(r"\d+", group))
    return numbers


def is_abstention(answer: str) -> bool:
    """True if the answer *starts* with the not-found sentence, as the prompt instructs.

    Checking only the start means a partial answer that mentions the sentence
    later ("X is 5 [1]. I could not find … for Y") still counts as grounded.
    """
    return answer.strip().lstrip("\"'*").lower().startswith(NOT_FOUND_ANSWER.lower().rstrip("."))


def assess_answer(answer: str, n_sources: int) -> tuple[set[int], list[int], str]:
    """Return (valid cited numbers, invalid cited numbers, grounding)."""
    cited = extract_citations(answer)
    valid = {n for n in cited if 1 <= n <= n_sources}
    invalid = sorted({n for n in cited if n not in valid})
    if is_abstention(answer):
        grounding = NOT_FOUND
    elif valid:
        grounding = GROUNDED
    else:
        grounding = UNGROUNDED
    return valid, invalid, grounding


def select_passages(results: list[SearchResult], min_score: float) -> list[SearchResult]:
    """Drop passages below the relevance floor and exact duplicates (same text).

    Duplicates appear when the same content exists in two uploads; sending it
    twice wastes context and splits citations across identical sources.
    """
    selected: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        if result.score < min_score:
            continue
        key = _WHITESPACE.sub(" ", result.chunk.text).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(result)
    return selected


def answer_question(
    question: str,
    retriever: Retriever,
    llm: LLMClient,
    top_k: int,
    max_context_chars: int,
    doc_ids: list[str] | None = None,
    min_score: float = 0.0,
) -> QAResult:
    retrieved = retriever.search(question, top_k, doc_ids)
    results = select_passages(retrieved, min_score)
    if not results:
        # Nothing indexed, or nothing relevant enough: don't call the LLM.
        logger.info("No passage above the relevance floor (%.2f) among %d retrieved; abstaining", min_score, len(retrieved))
        return QAResult(question=question, answer=NOT_FOUND_ANSWER, sources=[], grounding=NOT_FOUND)

    context, included = build_context(results, max_context_chars)
    user_prompt = build_user_prompt(question, context)
    answer = timed_generate(llm, SYSTEM_PROMPT, user_prompt)
    valid, invalid, grounding = assess_answer(answer, len(included))

    if grounding == UNGROUNDED:
        logger.warning("LLM answer cited no provided source; retrying once with a reminder")
        retry = timed_generate(llm, SYSTEM_PROMPT, user_prompt + RETRY_REMINDER)
        r_valid, r_invalid, r_grounding = assess_answer(retry, len(included))
        if r_grounding != UNGROUNDED:
            answer, valid, invalid, grounding = retry, r_valid, r_invalid, r_grounding
        else:
            answer = retry

    if invalid:
        logger.warning("LLM cited non-existent source numbers %s (had %d sources)", invalid, len(included))

    if grounding == UNGROUNDED:
        logger.warning("LLM answer is still uncited after the retry; returning it only as unverified output")
        return QAResult(
            question=question,
            answer=UNVERIFIED_ANSWER,
            sources=included,
            invalid_citations=invalid,
            grounding=UNGROUNDED,
            unverified_answer=answer,
            model=llm.model,
        )

    return QAResult(
        question=question,
        answer=answer,
        sources=included,
        cited_numbers=valid,
        invalid_citations=invalid,
        grounding=grounding,
        model=llm.model,
    )
