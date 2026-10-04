# Retrieval

Retrieval selects the passages most relevant to a query. In DocMind, it is **dense semantic retrieval**: embed the query, then return the top-k chunks by cosine similarity. It powers both **Search** (results shown directly) and **Ask** (results become the LLM's context).

Code: `app/retrieval.py` (`Retriever.search`), `app/service.py` (`search`, `_resolve_top_k`), `POST /api/search`.

## Steps

1. Validate: the query must be non-blank (the API also enforces 1–2,000 characters) and `top_k` must be 1–20.
2. Embed the query with the same model used for the chunks.
3. `FaissVectorStore.search(vector, k, doc_ids)` returns `(chunk, score)` pairs, best first.
4. Wrap them as ranked `SearchResult` objects (rank 1…k).
5. Log the result count, timing and query **length**, never the query text, which may be sensitive.

## Parameters

| Parameter | Where | Effect |
|---|---|---|
| `top_k` | request, else `TOP_K` setting | number of passages (clamped to 1–20) |
| `doc_ids` | request | restrict to selected documents (the UI's "Search within" filter) |
| `CHUNK_SIZE`/`CHUNK_OVERLAP` | indexing | what a "passage" is (default 600/150, size capped at 1200; [EMBEDDINGS.md](EMBEDDINGS.md)) |
| `MIN_RELEVANCE` | Ask only | passages scoring below it (default 0.15) are not sent to the LLM; Search results are **not** filtered ([RAG_PIPELINE.md](RAG_PIPELINE.md#relevance-floor-and-duplicates)) |

## Chunking choices that affect retrieval

- **Sentence-aware.** Chunks are built from whole sentences (`chunking.chunk_text`); a sentence longer than the chunk size is split on word boundaries.
- **Overlap.** The next chunk starts with the previous chunk's last whole sentences (up to `CHUNK_OVERLAP` characters), so a fact at a boundary survives intact in one of them.
- **Page-bounded.** Chunks never cross pages, which makes citations exact; the cost is that text continuing over a page break is split.
- **Deterministic.** The same text and settings always give the same chunks and IDs.

## Strengths and known weaknesses

- ✓ Matches paraphrases ("get my money back" ↔ "refund").
- ✗ No keyword (BM25) component: exact codes, names and numbers can be missed.
- ✗ No re-ranker: the top-k order is the embedding model's order.
- ✗ Small, English-focused model; inputs are truncated at 256 tokens.
- ✗ Similarity cannot detect "the answer isn't here": an unanswerable question still returns its nearest passages, sometimes with high scores (0.45–0.77 for on-topic unanswerable questions on the sample set). The Ask relevance floor (0.15) only removes clearly off-topic passages.

Measured quality and its caveats are in [EVALUATION.md](EVALUATION.md).
