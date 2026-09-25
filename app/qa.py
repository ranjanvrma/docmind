"""Retrieval-augmented question answering.

question -> retrieve top-k chunks -> numbered context -> LLM -> answer + citations

Citation honesty: the sources returned to the user are exactly the chunks that
were placed in the prompt. Citation markers in the answer are parsed and
checked against that list; a marker pointing at a source number that was never
provided (a hallucinated citation) is reported in ``invalid_citations`` rather
than shown as a real source.
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

# Matches [1], [2, 3], [Source 4] and similar.
_CITATION_GROUP = re.compile(r"\[(?:source\s*)?(\d+(?:\s*,\s*(?:source\s*)?\d+)*)\]", re.IGNORECASE)


@dataclass
class QAResult:
    question: str
    answer: str
    sources: list[SearchResult]  # the chunks that were given to the LLM, in source-number order
    cited_numbers: set[int] = field(default_factory=set)
    invalid_citations: list[int] = field(default_factory=list)
    answered_from_documents: bool = False
    model: str | None = None


def extract_citations(answer: str) -> list[int]:
    numbers: list[int] = []
    for group in _CITATION_GROUP.findall(answer):
        numbers.extend(int(n) for n in re.findall(r"\d+", group))
    return numbers


def is_abstention(answer: str) -> bool:
    return NOT_FOUND_ANSWER.lower().rstrip(".") in answer.lower()


def answer_question(
    question: str,
    retriever: Retriever,
    llm: LLMClient,
    top_k: int,
    max_context_chars: int,
    doc_ids: list[str] | None = None,
) -> QAResult:
    results = retriever.search(question, top_k, doc_ids)
    if not results:
        # Nothing indexed (or nothing in the selected documents): don't call the LLM.
        return QAResult(question=question, answer=NOT_FOUND_ANSWER, sources=[])

    context, included = build_context(results, max_context_chars)
    answer = timed_generate(llm, SYSTEM_PROMPT, build_user_prompt(question, context))

    cited = extract_citations(answer)
    valid = {n for n in cited if 1 <= n <= len(included)}
    invalid = sorted({n for n in cited if n not in valid})
    if invalid:
        logger.warning("LLM cited non-existent source numbers %s (had %d sources)", invalid, len(included))

    return QAResult(
        question=question,
        answer=answer,
        sources=included,
        cited_numbers=valid,
        invalid_citations=invalid,
        answered_from_documents=not is_abstention(answer) and bool(valid),
        model=llm.model,
    )
