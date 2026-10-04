# The RAG pipeline

**Retrieval-augmented generation (RAG)** answers a question in two separate steps: first *retrieve* the passages most relevant to the question from your documents, then ask a language model to *generate* an answer using only those passages.

```
question
  → query embedding                    app/embeddings.py   Embedder.embed_query
  → vector search (top-k)              app/vector_store.py FaissVectorStore.search
  → retrieved chunks                   app/retrieval.py    Retriever.search
  → relevance floor + de-duplication   app/qa.py           select_passages
  → context construction               app/prompts.py      build_context, build_user_prompt
  → LLM                                app/llm.py          LLMClient.generate
  → answer
  → citation validation + grounding    app/qa.py           assess_answer (extract_citations, is_abstention)
  → one retry if ungrounded            app/qa.py           RETRY_REMINDER
```

The orchestration is `qa.answer_question`, called by `DocMindService.ask` and exposed as `POST /api/ask`.

## Why retrieval is separate from generation

- **The model has never seen your documents.** Retrieval supplies the relevant facts at question time, so new uploads are usable immediately, with no training.
- **Answers become checkable.** Because the model only receives numbered passages, every claim can point at a source (document and page) that a person can read.
- **Cost and focus.** Sending a whole PDF would be slow and expensive, could exceed the model's context window, and would dilute its attention. DocMind sends at most `MAX_CONTEXT_CHARS` (default 6,000 characters) of the most relevant text.
- **Each part can be measured on its own.** Retrieval quality (did the right page come back?) is evaluated separately from answer quality ([EVALUATION.md](EVALUATION.md)).

## How relevant chunks are found

Every chunk was embedded at indexing time ([EMBEDDINGS.md](EMBEDDINGS.md)). The question is embedded with the same model, and FAISS returns the chunks whose vectors have the highest cosine similarity ([VECTOR_SEARCH.md](VECTOR_SEARCH.md)). An optional document filter restricts the search to selected documents ([RETRIEVAL.md](RETRIEVAL.md)).

## Why top-k exists

The model needs enough context to answer, but every extra passage adds cost, latency, and irrelevant text the model has to ignore. `TOP_K` (default 5, max 20) is that trade-off. A larger k raises the chance the answer is in context (recall) while lowering the share of passages that are relevant (precision).

## Relevance floor and duplicates

After retrieval, `qa.select_passages` drops passages whose cosine score is below `MIN_RELEVANCE` (default 0.15) and removes passages whose text is an exact duplicate of a higher-ranked one (after collapsing whitespace and case), for example the same content uploaded twice. If nothing remains, DocMind abstains **without calling the LLM**. Search results (`POST /api/search`) are not filtered by the floor.

Why 0.15, from the sample evaluation set: all 24 labelled-relevant passages in the top 5 scored ≥ 0.245 (none below 0.2); 31 of 76 irrelevant top-5 passages scored below 0.15; clearly off-topic questions had top scores of 0.08–0.18. But unanswerable questions on the documents' topic scored 0.45–0.77, so the floor only removes obvious noise. It cannot replace abstention by the LLM.

## Context limits

`build_context` adds passages in rank order and stops before `MAX_CONTEXT_CHARS` would be exceeded, so the prompt size is bounded whatever the chunk size or k. At least one passage is always included. **Only the passages that made it into the prompt are returned as sources**; retrieved passages that didn't fit are never shown as if the model saw them.

## How citations are generated

Each passage in the prompt is labelled `[Source n] (document: X, page: Y)`, and the system prompt requires a `[n]` citation after every claim. After generation, the citations are parsed and checked against the sources actually provided, and the reply is classified as `grounded`, `not_found` or `ungrounded`. An `ungrounded` reply (no valid citation, no abstention) is retried once with a reminder of the rules; if it is still ungrounded, it is returned only as `unverified_answer`, never as the answer ([CITATIONS.md](CITATIONS.md)).

## How abstention works

The system prompt tells the model to **begin** its reply with the exact sentence *"I could not find the answer in the uploaded documents."* when the sources don't contain the answer. `qa.is_abstention` detects that sentence at the start of the reply, `grounding` becomes `not_found`, and the UI shows a "Not found in your documents" badge. Abstentions are not retried. If retrieval returns nothing, or nothing passes the relevance floor, DocMind returns that sentence **without calling the LLM**.

## What RAG does not guarantee

- If the right passage is not retrieved, the model cannot answer correctly: retrieval quality caps answer quality.
- The model is *instructed* to use only the sources; nothing enforces it. The grounding check only ensures that an answer shown as an answer cites at least one real source.
- A cited source might not actually support the sentence next to it. DocMind verifies citation *numbers*, not claim-level support.
- Retrieval similarity cannot tell an answerable question from an unanswerable one: in testing, an unanswerable question retrieved a passage with a higher score than some correct answers, and on-topic unanswerable questions scored 0.45–0.77. The relevance floor catches only clearly off-topic questions; otherwise abstention depends on the model following its instructions.
