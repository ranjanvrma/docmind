# The RAG pipeline

**Retrieval-augmented generation (RAG)** answers a question in two separate steps: first *retrieve* the passages most relevant to the question from your documents, then ask a language model to *generate* an answer using only those passages.

```
question
  → query embedding                    app/embeddings.py   Embedder.embed_query
  → vector search (top-k)              app/vector_store.py FaissVectorStore.search
  → retrieved chunks                   app/retrieval.py    Retriever.search
  → context construction               app/prompts.py      build_context, build_user_prompt
  → LLM                                app/llm.py          LLMClient.generate
  → answer
  → citation validation                app/qa.py           extract_citations, is_abstention
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

## Context limits

`build_context` adds passages in rank order and stops before `MAX_CONTEXT_CHARS` would be exceeded, so the prompt size is bounded whatever the chunk size or k. At least one passage is always included. **Only the passages that made it into the prompt are returned as sources**; retrieved passages that didn't fit are never shown as if the model saw them.

## How citations are generated

Each passage in the prompt is labelled `[Source n] (document: X, page: Y)`, and the system prompt requires a `[n]` citation after every claim. After generation, the citations are parsed and checked against the sources actually provided ([CITATIONS.md](CITATIONS.md)).

## How abstention works

The system prompt tells the model to **begin** its reply with the exact sentence *"I could not find the answer in the uploaded documents."* when the sources don't contain the answer. `qa.is_abstention` detects that sentence at the start of the reply, and the UI shows a "Not found in your documents" badge. If retrieval returns nothing at all (for example an empty library), DocMind returns that sentence **without calling the LLM**.

## What RAG does not guarantee

- If the right passage is not retrieved, the model cannot answer correctly: retrieval quality caps answer quality.
- The model is *instructed* to use only the sources; nothing enforces it.
- A cited source might not actually support the sentence next to it. DocMind verifies citation *numbers*, not claim-level support.
- Retrieval similarity cannot tell an answerable question from an unanswerable one: in testing, an unanswerable question retrieved a passage with a higher score than some correct answers. Abstention depends on the model following its instructions.
