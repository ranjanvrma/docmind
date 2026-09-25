# DocMind: Project Guide for Interview Preparation

This guide explains DocMind from the inside: what each file does, why it was built that way, the maths behind it, how it fails, and what an interviewer is likely to ask. Every section points at real code. Open the file next to the section as you read.

**Suggested study order:** `app/service.py` (the whole pipeline in one place) → `ingestion.py` → `preprocessing.py` → `chunking.py` → `embeddings.py` → `vector_store.py` → `retrieval.py` → `prompts.py` → `qa.py` → `llm.py` → `classifier.py` → `api.py` → `frontend/streamlit_app.py` → `evaluation/evaluate.py`. Run `notebooks/pipeline_walkthrough.ipynb` alongside to see the intermediate outputs.

---

## 1. Architecture

DocMind has three layers:

1. **Frontend** (`frontend/streamlit_app.py`): a Streamlit page containing no ML code. Every button press becomes an HTTP request to the API.
2. **API** (`app/api.py`): FastAPI routes. Each route validates input with a Pydantic model (`app/models.py`), calls one method on `DocMindService`, and converts domain exceptions into HTTP status codes.
3. **Core pipeline** (`app/*.py`): plain Python modules, each doing one job, orchestrated by `DocMindService` in `app/service.py`.

```
Streamlit ──HTTP/JSON──▶ FastAPI ──▶ DocMindService ──▶ ingestion → preprocessing → chunking → embeddings → vector_store
                                                    ├─▶ retrieval (embeddings + vector_store)
                                                    ├─▶ qa (retrieval + prompts + llm)
                                                    └─▶ classifier (embeddings)
```

Why this split? The service can be used without HTTP: the CLI (`main.py ingest`), the evaluation script and the tests all call `DocMindService` directly, so there is exactly one implementation of the pipeline. The API is a thin adapter, and the UI could be replaced (by React, or a CLI) without touching any ML code.

**State on disk** (all under `data/`, git-ignored):

| File | Written by | Contents |
|---|---|---|
| `raw/<doc_id>.pdf` | `service.upload` | the uploaded bytes |
| `processed/documents.json` | `registry.py` | one record per document: filename, status, pages, chunk count, classification, errors |
| `index/index.faiss` | `vector_store.save` | serialised FAISS index (vectors + integer IDs) |
| `index/metadata.json` | `vector_store.save` | integer ID → chunk text, doc ID, doc name, page, chunk ID |
| `index/manifest.json` | `vector_store.save` | embedding model name, dimension, next ID, vector count (consistency check) |
| `classifier/classifier.joblib` | `main.py train-classifier` | trained logistic regression + name of the embedding model it expects |

## 2. Data flow

```
PDF bytes
 │ validate_pdf_upload()        extension, %PDF magic bytes, size ≤ MAX_UPLOAD_MB
 │ compute_document_id()        sha256(bytes)[:16]  → duplicate detection
 ▼
extract_pages()                 PyMuPDF, page.get_text("text", sort=True) per page
 │  → [PageText(doc_id, doc_name, page_number, text)], empty_pages, warnings
 ▼
preprocess_pages()              remove repeated headers/footers, clean_text() each page
 ▼
chunk_pages()                   sentence-aware chunks ≤ CHUNK_SIZE chars, CHUNK_OVERLAP overlap, per page
 │  → [Chunk(chunk_id="doc:p3:c0", doc_id, doc_name, page_number, chunk_index, text)]
 ▼
Embedder.embed()                sentence-transformers, batch of 32, L2-normalised float32 (n × 384)
 ▼
FaissVectorStore.add()          IndexIDMap2(IndexFlatIP) + metadata dict  →  save() to disk
 ▼
document_embedding()            mean of chunk vectors, re-normalised  →  DocumentClassifier.classify()
```

## 3. Components

### `config.py`: settings
A `Settings` dataclass built from environment variables (`load_settings()`), with a `.env` file loaded by `python-dotenv`. `validate()` rejects impossible values at startup (for example overlap ≥ chunk size), so a configuration error is caught immediately rather than causing a confusing failure later. `get_settings()` is wrapped in `lru_cache` so settings are read once. Tests build `Settings(...)` directly with a temporary `data_dir`.

### `ingestion.py`: PDF validation and extraction
- `validate_pdf_upload`: checks the extension (for user feedback) and that `%PDF-` appears in the first 1024 bytes. The magic-number check is the one that matters: an `.exe` renamed to `.pdf` is rejected before any parser sees it.
- `compute_document_id`: a SHA-256 of the *content*, so the same file uploaded twice under different names gets the same ID and is reported as a duplicate.
- `extract_pages`: opens the bytes with `pymupdf.open(stream=..., filetype="pdf")` and wraps parser exceptions in `IngestionError`. It rejects password-protected files. A page with fewer than `MIN_CHARS_PER_PAGE` non-whitespace characters goes into `empty_pages`. If no page has text, a warning says the PDF is probably scanned. `sort=True` asks PyMuPDF to order text blocks top-to-bottom, left-to-right, which reads multi-column layouts more naturally.

### `preprocessing.py`: text cleaning
PDF text has layout artifacts. `clean_text` fixes them in this order:
1. Unicode NFKC normalisation and ligature expansion (`ﬁ` → `fi`), plus removal of zero-width and soft-hyphen characters.
2. Rejoins words hyphenated at a line break (`infor-\nmation` → `information`).
3. Drops lines that are only a page number (`12`, `Page 3 of 10`).
4. Collapses runs of spaces.
5. `_join_wrapped_lines`: within a paragraph (text between blank lines), line breaks become spaces, except before bullet or numbered items.

`find_repeated_lines` detects running headers and footers: short lines (≤ 80 characters) that appear on at least 60% of pages, in documents with 3 or more pages. It deliberately does *not* lowercase text, remove stop words, stem or strip punctuation. Transformer embedders were trained on natural text, and the LLM needs the original wording to quote accurately.

### `chunking.py`: splitting into retrievable units
See [§5 Algorithms](#5-important-algorithms). Key decisions: chunks never cross pages, they are built from whole sentences, overlap is made of whole trailing sentences, and sizes are measured in characters.

### `embeddings.py`: vectors
`load_sentence_transformer` is wrapped in `lru_cache`, so the model loads once per process. The API loads it at startup inside FastAPI's `lifespan`. `Embedder.embed` calls `model.encode(..., normalize_embeddings=True)` and normalises again defensively. `Embedder` accepts any object with an `encode` method, which is how tests substitute the fast `HashingEncoder` (`tests/conftest.py`).

### `vector_store.py`: FAISS plus metadata
`FaissVectorStore` pairs a FAISS index with a Python dict `{faiss_id: chunk_metadata}`. Important details:
- `IndexIDMap2(IndexFlatIP(dim))`: the inner index does exact inner-product search, and the ID map lets us assign our own 64-bit IDs and later `remove_ids`, which deleting or re-processing a document needs.
- IDs come from a monotonically increasing `_next_id` that is never reused, so a removed ID can never collide with new metadata.
- `save()` serialises the index to bytes and writes each file atomically (temp file + `os.replace`). The manifest is written last and records the vector count.
- `load_or_create()` refuses to load if the manifest's embedding model or dimension differs from the configured one, or if the index size, metadata count and manifest size disagree. Serving results from a mismatched index would give meaningless scores without any visible error, so a loud failure is better.
- A search with a document filter over-fetches (the whole index) and then filters. For a flat index this costs the same as a normal search.

### `retrieval.py`: `Retriever.search`
Validates the query, embeds it with `embed_query`, calls `store.search`, and wraps the hits in ranked `SearchResult` objects. It logs the result count, timing and query *length*, but not the query text, which may be sensitive.

### `prompts.py`: prompt and context
`SYSTEM_PROMPT` states the rules: use only the numbered sources, cite `[n]` after each claim, reply with the exact `NOT_FOUND_ANSWER` sentence when the answer is not in the sources, flag partial answers and conflicts. `build_context` adds `[Source n] (document: X, page: Y)` blocks in rank order until `MAX_CONTEXT_CHARS` would be exceeded (always at least one source), and returns which results were included. Only those can be shown as sources.

### `llm.py`: provider abstraction
`LLMClient` is an abstract class with one method, `generate(system_prompt, user_prompt) -> str`. `AnthropicClient` uses the official `anthropic` SDK. `OpenAICompatibleClient` POSTs to `{base_url}/chat/completions` with `httpx`, which covers OpenAI, Groq, OpenRouter, Together and local Ollama. `create_llm_client(settings)` is the only place that knows which provider is in use. Both clients translate provider errors (bad key, rate limit, network failure, empty or refused response) into `LLMError`, which the API turns into HTTP 502. A missing key raises `LLMNotConfiguredError`, which becomes HTTP 503.

### `qa.py`: RAG with citation checks
`answer_question`: retrieve → return `NOT_FOUND_ANSWER` immediately if nothing was retrieved (no LLM call) → build context → call the LLM → `extract_citations` (a regex for `[1]`, `[2, 3]`, `[Source 4]`) → split citations into valid ones (1…number of sources) and `invalid_citations` → `answered_from_documents = not abstained and at least one valid citation`.

### `classifier.py`: document category
See [§21](#21-how-classification-works).

### `registry.py`: document records
A thread-safe dict of `DocumentRecord`, persisted to one JSON file with atomic writes. It tracks the lifecycle `uploaded → processed | failed`.

### `service.py`: orchestration
`DocMindService.__init__` builds the embedder, loads or creates the vector store, the registry, the retriever and the classifier. The LLM client is created lazily, so the app starts without an API key. `process()` skips documents that are already processed and present in the index unless `force=True`, which is why nothing is ever re-embedded unnecessarily. `_process_one` removes any existing vectors for the document first, so re-processing replaces rather than duplicates. It catches failures per document, marks the record `failed` with a readable error, and keeps the index consistent. A `threading.Lock` serialises writes such as `process` and `delete`.

### `api.py`, `frontend/streamlit_app.py`, `evaluation/evaluate.py`
Covered in §22, §23 and §20.

## 4. Why each technology

| Choice | Reason | Alternatives considered |
|---|---|---|
| **PyMuPDF** | Fast C library (MuPDF), tolerant of malformed files, per-page API, reading-order sort. | `pypdf` (pure Python, slower, weaker on complex layouts), `pdfplumber` (good for tables, slower), `unstructured` (heavy). |
| **sentence-transformers / all-MiniLM-L6-v2** | Trained specifically so that cosine similarity reflects semantic similarity. 384 dimensions, ~90 MB, fast on CPU. | `bge-small-en`, `e5-small` (often better, but need query/passage prefixes), OpenAI embeddings (API cost, data leaves the machine). |
| **FAISS** | In-process, no server, exact search out of the box, and a path to approximate indexes (IVF, HNSW) if the data grows. | Chroma, Qdrant, Weaviate, pgvector: all add a service or a heavier dependency, which is unnecessary for a local single-user app. |
| **Direct RAG code, no LangChain** | The pipeline is about 150 lines, and writing it explicitly makes every step visible and testable. | LangChain / LlamaIndex: faster to prototype, but they hide the retrieval and prompt details this project is meant to demonstrate. |
| **FastAPI** | Pydantic validation, automatic OpenAPI docs, dependency injection, simple testing with `TestClient`. | Flask (no built-in validation), Django (too heavy). |
| **Streamlit** | A usable UI in one Python file. | Gradio (similar), React (far more work for no ML benefit). |
| **scikit-learn LogisticRegression** | Strong, fast, well-calibrated baseline on top of embeddings, and works with little data. | Fine-tuning a transformer (needs far more labelled data and a GPU), SVM (no native probabilities), zero-shot NLI models (slow). |

## 5. Important algorithms

### Sentence-aware chunking with overlap (`chunking.chunk_text`)
```
units = split text into sentences (regex: after . ! ? + whitespace, or at a newline)
        any sentence longer than chunk_size → split on word boundaries (_split_long_unit)
current = []
for unit in units:
    if current is non-empty and len(join(current + unit)) > chunk_size:
        emit join(current)
        overlap = the longest suffix of whole sentences in current with total length ≤ chunk_overlap
        current = overlap, unless overlap + unit would itself exceed chunk_size (then [])
    current.append(unit)
emit the rest
```
Properties (each covered by `tests/test_chunking.py`): every chunk is ≤ `chunk_size`; with zero overlap, joining the chunks reproduces the text exactly; each chunk starts with the last sentence of the previous one when overlap allows; the output is deterministic (no randomness, and the same input always gives the same chunks and IDs).

Why overlap? If a key fact spans a chunk boundary, then without overlap neither chunk contains all of it. Overlap duplicates some text (a larger index) in exchange for better recall.

Why about 800 characters? A chunk should hold one coherent idea. If it is too small, context is lost ("it increased by 6%": what increased?). If it is too large, several topics blur into one vector and the similarity score becomes vague, and each retrieved chunk uses more of the LLM's context. 800 characters is roughly 150–200 tokens, safely below MiniLM's 256 word-piece limit (text beyond it is silently truncated). The right value should be *chosen with the evaluation script*, not guessed.

### Header/footer detection (`preprocessing.find_repeated_lines`)
Count each distinct short line once per page; lines appearing on at least 60% of pages are boilerplate.

### Exact nearest-neighbour search (FAISS `IndexFlatIP`)
Score = q · xᵢ for every stored vector xᵢ. Keep the top-k with a heap. Cost O(n·d) per query.

### Mean pooling for document vectors (`classifier.document_embedding`)
doc = normalise( (1/n) Σ chunk_vectorᵢ ).

### Logistic regression (multinomial)
P(class c | x) = softmax(W x + b)_c, trained by minimising cross-entropy with L2 regularisation (`C=4.0` is the inverse regularisation strength). `class_weight="balanced"` reweights classes by inverse frequency.

## 6. Important formulas

| Formula | Where it is used |
|---|---|
| L2 normalisation: x̂ = x / ‖x‖₂, where ‖x‖₂ = √(Σ xᵢ²) | `embeddings.normalize_rows` |
| Cosine similarity: cos(a, b) = (a · b) / (‖a‖ ‖b‖) | the meaning of every score |
| For unit vectors: cos(a, b) = a · b | why `IndexFlatIP` returns cosine similarity |
| Relation to Euclidean distance for unit vectors: ‖a − b‖² = 2 − 2 cos(a, b) | why L2 search and cosine search give the same ranking on normalised vectors |
| Softmax: pᶜ = e^{zᶜ} / Σⱼ e^{zʲ} | logistic regression probabilities |
| Precision@K = (# relevant in top K) / K | `evaluate.precision_at_k` |
| Recall@K = (# distinct relevant pages found in top K) / (# relevant pages) | `evaluate.recall_at_k` |
| Hit@K = 1[at least one relevant in top K] | `evaluate.hit_at_k` |
| MRR = mean over queries of 1 / rank of first relevant result | `evaluate.reciprocal_rank` |
| Token F1 = 2PR / (P + R), with P = common tokens / predicted tokens and R = common tokens / reference tokens | `evaluate.token_f1` |
| Classifier precision = TP / (TP + FP), recall = TP / (TP + FN), macro-F1 = mean of per-class F1 | `classifier.train_classifier` report |

## 7. Important design decisions

1. **Content-hash document IDs.** Duplicate detection comes for free, and stored filenames are hashes, so path traversal via filenames is impossible.
2. **Chunks never cross pages.** Page citations are always exact. The cost is split context at page breaks.
3. **Normalised embeddings + inner-product index.** Scores are directly interpretable as cosine similarity.
4. **`IndexIDMap2` + never-reused IDs.** Documents can be deleted or re-processed without rebuilding the index, and metadata can never be attached to the wrong vector.
5. **Manifest check on load.** A changed embedding model or index/metadata drift raises a loud error instead of silently returning wrong results.
6. **Skip already-processed documents.** Embedding is the most expensive step and never runs twice for the same content unless forced.
7. **The LLM sees only retrieved chunks, within a character budget.** Cost and latency are bounded, and "the answer came from these passages" is literally true.
8. **Sources = exactly what was in the prompt, and citations are verified.** The UI cannot display a source that was not provided, and invented citation numbers are surfaced as warnings.
9. **A fixed abstention sentence.** Makes "I don't know" detectable in code and in evaluation.
10. **Lazy LLM client.** Search and classification work with no API key, and `/ask` fails with a clear 503.
11. **Zero-shot fallback for classification.** Something useful works on day one, and supervised training is opt-in once real labels exist.
12. **Page-level evaluation labels.** They survive changes to chunking parameters, so different configurations can be compared on the same dataset.

## 8. Possible alternatives

- **Chunking:** fixed token windows (using the model's tokenizer), recursive splitting by headings then paragraphs then sentences, or semantic chunking (split where the embedding similarity between consecutive sentences drops).
- **Retrieval:** BM25 keyword search; hybrid search combining BM25 and dense scores (e.g. reciprocal rank fusion); a cross-encoder re-ranker over the top 20–50 results; MMR (maximal marginal relevance) to diversify results.
- **Index:** `IndexHNSWFlat` or `IndexIVFFlat` for millions of vectors (approximate, faster); product quantisation to save memory; a managed vector DB for multi-user deployments.
- **Generation:** streaming answers; structured output (JSON with answer and citation list); a second "verifier" pass checking each claim against its citation.
- **Classification:** fine-tuned DistilBERT; zero-shot NLI (`facebook/bart-large-mnli`); asking the LLM to classify (costly, and harder to evaluate reproducibly).

## 9. Common failure modes

| Symptom | Likely cause | Where to look / fix |
|---|---|---|
| Document marked *failed*, "No text could be extracted" | Scanned or image-only PDF | Needs OCR (not implemented) |
| Garbled words, missing spaces | Unusual PDF font encoding, or text drawn as vector paths | Try another extractor, or OCR |
| Right document but wrong passage retrieved | Chunks too large or too small; vocabulary mismatch | Tune `CHUNK_SIZE` with `evaluate.py`; try a stronger embedding model; add BM25 |
| Exact codes or names not found | Dense embeddings blur rare tokens | Hybrid keyword + dense search |
| API won't start: "index … was built with …" | `EMBEDDING_MODEL` changed after indexing | Delete `data/index/` and re-process, or restore the model |
| Answer ignores the documents or cites wrong sources | Weak model, relevant chunk not retrieved, or context truncated | Check `context_has_relevant_page` in the QA evaluation; increase top-k or `MAX_CONTEXT_CHARS` |
| "I could not find the answer…" although it is in the PDF | Retrieval miss (answer ranked below top-k), or the answer is split across a page break | Increase top-k; inspect the search results for the same question |
| `/ask` returns 503 | No `LLM_API_KEY` | Configure `.env` |
| `/ask` returns 502 | Bad key, rate limit, network error, wrong base URL or model name | The error detail and API logs show which |
| Slow first request | Model download or loading | Loaded once at startup; the Docker image bakes the model in |

## 10–11. Interview questions and what you should be able to say

**Q: Walk me through what happens when I upload a PDF.** → See §12. Mention validation, hashing, extraction, cleaning, chunking, embedding, indexing, classification and persistence, in that order, with file names.

**Q: Why did you chunk the documents at all? Why not embed whole documents?**
- Embedding models truncate long inputs (MiniLM at 256 word-pieces), so most of a long document would simply be ignored.
- A single vector for a 50-page document averages many topics, so it matches everything weakly and nothing precisely.
- The LLM should receive a few relevant passages, not whole documents (cost, context limits, and focus).
- Chunks give precise page citations.

**Q: How did you choose chunk size and overlap?** Chunks should be large enough to hold a self-contained statement and small enough to stay on one topic and within the model's token limit. Overlap protects facts that straddle a boundary. The honest answer: 800/150 is a reasonable starting point, and the evaluation script exists to tune it on real data.

**Q: What is an embedding?** A learned mapping from text to a fixed-length vector (384 numbers here) where texts with similar meaning land close together. See §15.

**Q: Why cosine similarity rather than Euclidean distance?** Cosine compares direction and ignores vector length, which mostly reflects things like text length rather than meaning. After L2 normalisation the two are equivalent for ranking, because ‖a − b‖² = 2 − 2cos(a, b). We normalise and use an inner-product index so the score is exactly the cosine.

**Q: What does FAISS do? Is your search exact?** Yes. `IndexFlatIP` compares the query with every vector. For large collections you would switch to IVF or HNSW, which are approximate. See §17.

**Q: How do you keep FAISS and your metadata in sync?** Integer IDs assigned by us (`IndexIDMap2`), never reused; both structures are updated under a lock; atomic file writes; a manifest with the vector count, checked on load.

**Q: What is RAG and why use it instead of fine-tuning?** RAG supplies relevant text at question time. It works with new documents instantly (fine-tuning would need retraining), it can cite sources, it is cheaper, and the knowledge is inspectable and deletable. Fine-tuning changes *behaviour and style* better than it adds reliably-retrievable facts.

**Q: How do you reduce hallucinations?** Retrieval restricts the context; the prompt forbids outside knowledge and requires citations; a fixed abstention sentence; no LLM call at all when nothing is retrieved; citation numbers are verified; the UI shows the exact passages so the user can check. Be honest: none of this *guarantees* faithfulness. See §19.

**Q: How do you know your retrieval is any good?** Show `evaluate.py`: a labelled set of queries with relevant pages, then Hit@K, Precision@K, Recall@K and MRR. Then add the caveat that the bundled set is a tiny demo written by the author, so its scores are optimistic. A real evaluation needs independently written queries over real documents.

**Q: Why is your Precision@5 only 0.24?** Most sample queries have exactly one relevant page, and the index holds 11 chunks. With 5 results, at least 4 must be irrelevant, so the maximum possible Precision@5 is about 0.2–0.3. Recall@K and Hit@K are the more meaningful metrics here.

**Q: How does the classifier work, and how accurate is it?** See §21. On accuracy: the only measured number is 5-fold cross-validation on 48 synthetic training texts (0.81), which says little about real documents. The zero-shot mode has no measured accuracy.

**Q: What happens if two users upload at the same time?** Uploads are independent (content-addressed files). Processing and deletion are serialised by a lock inside one process. Multiple API worker processes would *not* share that lock or the in-memory index; that is a known single-process limitation. A real deployment would use a vector database and a job queue.

**Q: How did you handle security?** API keys only from the environment, never logged; content-hash storage names (no path traversal); `sanitize_filename` for display names; magic-byte and size checks; the upload read is capped at the limit + 1 byte; PDFs are parsed, never executed; the container runs as a non-root user; query text and document content are not logged. Known gaps: no authentication, and `joblib` model files must be trusted (pickle).

**Q: What would you improve first?** Hybrid retrieval + re-ranking, measured on a real evaluation set; then OCR, then background processing.

**Q: Why not LangChain?** Writing the pipeline directly made each step explicit, testable and explainable. LangChain is reasonable for fast prototyping, but it would hide exactly the parts this project is about.

## 12. Internals: uploading a PDF

1. Streamlit's *Upload & process* sends `POST /documents/upload` as multipart form data.
2. `api.upload_documents` reads each file, at most `MAX_UPLOAD_MB` + 1 bytes (so an oversized file is detected without reading all of it), and calls `service.upload(name, data)`.
3. `service.upload` runs `sanitize_filename` (strips directories and odd characters), `validate_pdf_upload` (extension, `%PDF-`, size), then `compute_document_id` (SHA-256 prefix). If the registry already has that ID, it returns `duplicate`. Otherwise it writes `data/raw/<doc_id>.pdf` atomically and saves a `DocumentRecord(status="uploaded")`.
4. The UI then calls `POST /documents/process {"doc_ids": [...]}` → `service.process` → `_process_one`:
   1. `store.remove_document(doc_id)` (a no-op the first time; prevents duplicates on re-processing).
   2. `extract_pages`: PyMuPDF text per page; empty pages recorded; warnings for scanned files.
   3. `preprocess_pages`: header/footer removal, then `clean_text`.
   4. `chunk_pages`: `Chunk` objects with IDs like `ccc4…:p2:c1`.
   5. `embedder.embed(all chunk texts)`: one batched call, giving an n × 384 unit-vector matrix.
   6. `store.add(chunks, embeddings)`: new integer IDs, `add_with_ids`, metadata stored.
   7. `classifier.classify(document_embedding(embeddings))`: the category is stored on the record.
   8. The record is set to `processed` with page and chunk counts.
5. After all documents are done, `store.save()` writes the index, metadata and manifest once.
6. The API responds with per-document status, and the UI shows successes, warnings and failures.

## 13. Internals: a search

1. The UI sends `POST /search {"query", "top_k", "doc_ids"}`.
2. Pydantic `SearchRequest` rejects a blank query or a `top_k` outside 1–20 with 422 before any code runs.
3. `service.search` → `Retriever.search` → `embedder.embed_query(query)`: one 1 × 384 unit vector, using the *same model* as the chunks (essential, because vectors from different models are not comparable).
4. `store.search(vector, k)` → FAISS computes the inner product with every stored vector and returns the top-k scores and IDs (IDs of −1 mean padding and are skipped).
5. Each ID is mapped to its metadata → `Chunk` → `SearchResult(score, rank)`.
6. The API returns `SearchHit` objects (score rounded to 4 decimals, document name, page, chunk text), and the UI renders each as an expandable passage.

## 14. Internals: asking a question

1. `POST /ask` → `service.ask` → `self.llm` (created on first use; `LLMNotConfiguredError` → 503).
2. `answer_question` runs the same retrieval as §13.
3. With no results, it returns `NOT_FOUND_ANSWER` and never calls the LLM.
4. `build_context` numbers the chunks `[Source 1…n]` with document and page, stopping at `MAX_CONTEXT_CHARS`.
5. `build_user_prompt` wraps the context in `<sources>` tags followed by the question; `SYSTEM_PROMPT` carries the rules.
6. `timed_generate` → `AnthropicClient` or `OpenAICompatibleClient` `.generate()`; the call is logged with sizes and duration, not content.
7. `extract_citations` finds `[n]` markers. Valid ones mark the corresponding sources as `cited=True`; out-of-range numbers go to `invalid_citations`.
8. `answered_from_documents` is true only if the model did not abstain *and* cited at least one real source.
9. The UI shows the answer, any warnings, and the sources (cited first) as expandable passages with document and page.

## 15. How embeddings work (in this project)

`all-MiniLM-L6-v2` is a 6-layer transformer (a distilled MiniLM). Text is tokenised into word-pieces (truncated at 256), each token gets a contextual vector from self-attention layers, and **mean pooling** over the token vectors gives one 384-dimensional sentence vector. sentence-transformers then L2-normalises it (we pass `normalize_embeddings=True`).

The model was fine-tuned with a **contrastive objective** on over a billion sentence pairs (question–answer, paraphrases and similar). Matching pairs were pushed together and non-matching pairs apart. That training is why "How do I get my money back?" lands near "Customers may request a refund within 30 days" even though they share almost no words. `tests/test_embeddings.py::test_real_model_captures_semantic_similarity` checks exactly this.

Individual dimensions have no human-readable meaning; only distances between vectors matter. The same model must embed both the documents and the queries.

## 16. How cosine similarity works

cos(a, b) = (a · b) / (‖a‖‖b‖): the cosine of the angle between two vectors. 1 means the same direction, 0 means orthogonal (unrelated), and −1 means opposite. For sentence embeddings, scores are rarely negative, and in practice unrelated text scores around 0–0.2 with MiniLM, while strong matches score 0.5 or more. Scores are *relative*: they depend on the model and the corpus, so there is no universal "relevant" threshold, which is why DocMind ranks rather than thresholds.

Because our vectors are unit length, the denominator is 1 and cosine = dot product. NumPy example from the notebook: `scores = chunk_vectors @ query_vector`.

## 17. How FAISS works (conceptually)

FAISS is a library of index structures for finding the nearest vectors to a query.

- **`IndexFlatIP`** (used here) stores all vectors in one contiguous float32 array and computes the query's inner product with every vector using optimised BLAS/SIMD code, then keeps the top-k. It is exact, needs no training, and costs O(n·d) per query. For 10,000 chunks × 384 dimensions that is about 4 million multiply-adds, which takes milliseconds.
- **`IndexIDMap2`** wraps it and stores a mapping from internal position to our 64-bit IDs, enabling `add_with_ids` and `remove_ids`.
- **At larger scale:** *IVF* clusters vectors with k-means and searches only the few clusters nearest the query (`nprobe`); *HNSW* builds a multi-layer proximity graph and walks it greedily; *PQ* compresses vectors into short codes. These are approximate: much faster, with slightly lower recall. That trade-off is only worth it past roughly hundreds of thousands of vectors.
- FAISS stores only vectors and IDs, never text, which is why DocMind keeps a separate metadata store and has to keep the two in sync.

## 18. How RAG works (in this project)

An LLM can only use knowledge from its training data plus whatever is in its prompt. RAG puts the relevant parts of *your* documents into the prompt at question time:

1. **Index** (offline): chunk → embed → store (§12).
2. **Retrieve** (per question): embed the question, get the top-k chunks (§13).
3. **Augment**: build a prompt with the numbered chunks and the grounding rules (`prompts.py`).
4. **Generate**: the LLM writes an answer from that context with `[n]` citations (`llm.py`).
5. **Verify/present**: parse and check the citations, show the sources (`qa.py`, UI).

Answer quality is capped by retrieval quality. If the right chunk is not in the top-k, the LLM cannot answer correctly (or it may answer from memory, which the prompt forbids). That is why retrieval is evaluated separately, and why the QA evaluation records `context_has_relevant_page`.

## 19. Why hallucinations happen

An LLM generates the most plausible continuation token by token. It has no built-in notion of "I don't have evidence for this". Hallucinations arise when:

- the relevant passage was **not retrieved** (retrieval miss), so the model fills the gap from training data or invents something;
- the retrieved context is **ambiguous, partial or contradictory**;
- the question **presupposes something false** ("Why did the policy ban X?" when it didn't);
- the model **over-generalises** from similar-looking text, e.g. mixing numbers from two sources;
- **long contexts** dilute attention, so details in the middle of the context get less weight.

DocMind's mitigations: a strict system prompt and an allowed "not found" answer; the prompt contains only retrieved passages; no LLM call when nothing is retrieved; a bounded context; citation numbers are verified; and passages are shown for human checking. Remaining risk: the model can cite a real source for a claim that source does not actually support. Detecting that needs claim-level verification (an NLI model or a verifier LLM), listed under future improvements.

## 20. How retrieval quality is evaluated

`evaluation/evaluate.py`:

1. Loads a dataset (`evaluation/datasets/sample_eval.json`) of `{query, relevant: [{document, page}]}`.
2. Indexes the dataset's PDFs into a **temporary** data directory with the *current* `.env` settings, so the real index is untouched and configurations can be compared by changing `.env` and re-running.
3. For each query, retrieves the top max(K) chunks and marks each one relevant if its `(document, page)` is labelled.
4. Computes Hit@K, Precision@K, Recall@K and MRR (formulas in §6), averages them with pandas, and prints and saves `retrieval_per_query.csv` and `summary.json`.
5. With `--qa`: runs `service.ask` on the QA items and records token F1 against the reference, abstention on answerable vs unanswerable items, whether a relevant page reached the context, citation precision, and invalid citations.

Measured on the demo set (20 queries, 3 fictional PDFs, MiniLM, 800/150): Hit@1 0.70, Hit@3 0.95, Hit@5 1.00, MRR 0.838. Be ready to explain why these are **not** evidence of real-world quality: the set is tiny, and the same person wrote the documents and the queries, so the wording overlaps more than real users' questions would.

How to do it properly: collect real documents; have other people write questions and label the relevant pages; use at least 100 queries; report metrics per configuration; look at failures by hand; and keep a held-out set you don't tune on.

## 21. How classification works

**Representation:** the document vector is the re-normalised mean of all its chunk embeddings (`document_embedding`). These vectors already exist from indexing, so classification is nearly free.

**Zero-shot mode** (default): each label has a natural-language description (`CATEGORY_DESCRIPTIONS`), which is embedded once and cached. The prediction is the label whose description has the highest cosine similarity with the document vector. The scores shown are raw cosine similarities, *not* probabilities, and the UI says so. In the sample run, the policy document scored Policy 0.2218 vs Report 0.2208: a correct label, but a margin too small to trust.

**Supervised mode:** `python main.py train-classifier data.csv` → `load_training_data` (validate columns, strip, deduplicate) → embed every text → **stratified k-fold cross-validation** (`cross_val_predict`, k = min(5, smallest class size)) to *measure* accuracy and macro-F1 on data the model hasn't seen → fit on all data → save with `joblib` together with the embedding model's name. At startup, `DocumentClassifier` loads it only if that name matches the current embedding model (the features would otherwise be meaningless). Predictions are softmax probabilities from logistic regression.

**Honesty points:** the bundled 48 examples are synthetic. The measured cross-validation accuracy of 0.81 is on those only. In the sample run, the supervised model labelled the ML lecture notes as "Research Paper". A likely explanation: embeddings capture *topic* more strongly than *document form*, and the training texts for "Notes" covered other topics. More varied real training data is the fix, and it is also a good talking point about dataset bias.

## 22. How the FastAPI layer works

- `create_app(service=None)` is an **app factory**. In production, a `lifespan` handler builds one `DocMindService` at startup (loading the model and index once) and stores it on `app.state`. Tests pass in a service built with the fake encoder and fake LLM.
- Routes get the service through `Depends(get_service)` (FastAPI dependency injection).
- **Validation:** request bodies are Pydantic models (`SearchRequest`, `AskRequest`, `ProcessRequest`) with field constraints (`min_length`, `ge`/`le` bounds, a custom non-blank validator). FastAPI returns **422** automatically when validation fails.
- **Status codes:** 201 upload, 400 all files rejected, 404 unknown document, 204 delete, 422 invalid input, 502 upstream LLM failure, 503 LLM not configured, 500 internal errors (logged with a traceback; the client gets a generic message).
- **Sync vs async:** CPU-bound routes (search, process) are plain `def`, so FastAPI runs them in a thread pool and they don't block the event loop. Upload is `async def` because it awaits `UploadFile.read`.
- Response models (`response_model=...`) define the output schema and appear in the auto-generated docs at `/docs`.

## 23. How Streamlit communicates with the backend

Streamlit re-runs the entire script from top to bottom on every interaction. On each run, `streamlit_app.py` calls `GET /health` and `GET /documents` to draw the sidebar, and button handlers call `POST /documents/upload`, `/documents/process`, `/search`, `/ask` and `DELETE /documents/{id}` via `requests`. The API URL comes from `DOCMIND_API_URL` (in Docker Compose, `http://api:8000`, the service name on the compose network). `api_request` turns connection errors, timeouts and HTTP errors (including FastAPI's 422 detail lists) into readable `st.error` messages. Forms (`st.form`) prevent a request from firing on every keystroke. The UI keeps no ML state of its own; restarting it loses nothing.

## 24. How Docker is used

- **`Dockerfile`**: `python:3.11-slim` base; installs the **CPU-only** PyTorch wheel first (the default wheel pulls in gigabytes of CUDA libraries), then `requirements.txt`; **pre-downloads the embedding model** during the build so containers start without network access; copies only the code it needs; runs as a non-root `docmind` user; the default command runs Uvicorn on port 8000.
- **`docker-compose.yml`**: two services from one image. `api` reads `.env` and mounts `./data` so uploads and indexes survive container restarts, and has a health check on `/health`. `ui` overrides the command to run Streamlit, points `DOCMIND_API_URL` at `http://api:8000`, and starts only after the API is healthy. Compose earns its place here because the app really is two processes that need to find each other.
- **`.dockerignore`** keeps `.env`, the virtual environment, user data and git history out of the build context, so no secrets or uploaded documents are baked into the image.
- The app runs identically without Docker (`python main.py api` / `ui`). Docker only adds reproducibility.
