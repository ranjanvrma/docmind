# DocMind: Code Walkthrough and Audit

> **Historical document.** Written on 2026-09-26, when the interface was a Streamlit app (`frontend/streamlit_app.py`) and the API had no `/api` prefix. The Streamlit UI was later replaced by a React frontend (`web/`, see [FRONTEND.md](FRONTEND.md)); API routes moved under `/api`; Docker became a single two-stage image. Findings about the pipeline, retrieval and evaluation still apply unless noted elsewhere.

This is an audit of the code **as it exists**, written for studying and defending the project. Each claim points at a file and function. Where the README, PROJECT_GUIDE or code comments disagree with the code, the disagreement is listed in [§0](#0-audit-findings-read-first) rather than silently accepted.

How this was checked: by reading the code, running the 100 tests, re-running `evaluation/evaluate.py` (it reproduced the README numbers exactly), inspecting the embedding model object in Python, and running small read-only probe scripts against the existing functions. **No application code was changed.**

Line numbers refer to the commit `9b15cf0`.

---

## 0. Audit findings (read first)

> **Update after the audit:** F1, F3, F4 and F5 have since been **fixed**, with regression tests (`tests/test_preprocessing.py`, `tests/test_consistency.py`, `tests/test_qa.py`; 124 tests in total). The rows below describe the code *as audited* at `9b15cf0`. F2, F6 and F7 remain open. The README and PROJECT_GUIDE discrepancies in §0.2 have been corrected in those files. A later production-hardening pass also fixed F6 (abstention now detected only at the start of an answer) and F7 (the sidebar refreshes after upload), and changed several Part 11 security statuses: there is now an optional API token, a request-size limit enforced before the body is read, a page-count limit, prompt-injection mitigations, and secrets hidden from `Settings.__repr__`. See README > Security model for the current state (160 tests).

### 0.1 Bugs and behaviour problems (verified by running the code)

| # | Finding | Evidence | Severity |
|---|---|---|---|
| F1 *(fixed)* | **Number-only lines are deleted during preprocessing.** `_PAGE_NUMBER_LINE` (`app/preprocessing.py:23`) matches any line consisting of 1–4 digits, so table cells and years on their own line are removed, not just page numbers. | `clean_text("Year\n2023\n2024\nRevenue\n1480\n1570")` returns `'Year Revenue'`. | **High for tables/financial PDFs.** It contradicts the README ("numbers … are preserved"), and no test covers it. |
| F2 | **Hyphenated compounds are merged when they break across a line.** `_HYPHEN_LINEBREAK` (`preprocessing.py:22`) turns `well-\nknown` into `wellknown`. The code comment calls this a rare casualty; for compound words it is common. | `clean_text("a well-\nknown result")` returns `'a wellknown result'`. | Low. |
| F3 *(fixed)* | **The registry and the index can disagree, and "Process pending documents" won't repair it.** `_process_one` writes the registry per document (`service.py`), but the index is saved once after the loop (`service.py:123`). If the process dies in between, or `data/index/` is lost, the registry still says `processed`. `process()` with no IDs only selects documents whose status is not `processed` (`service.py:103`), so it does nothing. | Probe: after deleting `data/index/`, `process()` returned `[]`, the index size was 0, and the status was `processed`. `process([doc_id])` with an explicit ID does repair it (via the `has_document` check). | Medium (only after crashes or manual deletion). |
| F4 *(fixed)* | **A missing `index.faiss` next to an existing `manifest.json` crashes startup with a raw `FileNotFoundError`** instead of the friendly `VectorStoreError` used for other inconsistencies (`vector_store.py:152+`). | Probe: `FileNotFoundError` was raised from `DocMindService(...)`. | Low. |
| F5 *(fixed)* | **Bracketed numbers that aren't citations are flagged as invalid citations.** `_CITATION_GROUP` (`qa.py:26`) matches `[2024]`. | `extract_citations("In [2024] revenue rose [1].")` returns `[2024, 1]`, so the UI would warn "cited source numbers that were not provided: [2024]". | Low (a false warning, never a fake source). |
| F6 | **Partial answers containing the abstention sentence are marked as not grounded.** `is_abstention` is a substring check (`qa.py:47`), and `answered_from_documents` requires no abstention (`qa.py`). | `is_abstention("X is 5 [1]. I could not find the answer … for Y.")` returns `True`. | Low; conservative by design, but worth knowing. |
| F7 | **The Streamlit sidebar is stale right after uploading or processing.** The sidebar and document list are drawn from `/documents` at the top of the script (`streamlit_app.py:59–63`), *before* the button handlers run (`:97`, `:120`), so new statuses appear only on the next interaction. | Code order. | Low (UX). |

### 0.2 Documentation vs code discrepancies

| Where | Doc says | Code actually does |
|---|---|---|
| README → Features; PROJECT_GUIDE §3 | "Punctuation, numbers and case are preserved." | Numbers on their own line are deleted (F1). Case is preserved *in the text*, but **the embedding model lowercases everything**: its tokenizer is uncased (`"Hello WORLD"` → `['hello', 'world']`). Case matters only for the text the LLM sees. |
| PROJECT_GUIDE §12 | The upload read is capped "so an oversized file is detected without reading all of it". | Starlette's multipart parser receives the **entire** file and spools it to a temp file (1 MB in memory, then disk) *before* the route runs. `upload.read(limit + 1)` only limits the copy into Python memory. The comment in `api.py` ("without loading all of it into memory") is technically true; the PROJECT_GUIDE wording is not. |
| PROJECT_GUIDE §15 | "sentence-transformers then L2-normalises it (we pass `normalize_embeddings=True`)." | The loaded model pipeline already ends in a `Normalize` module (`Transformer → Pooling → Normalize`), so the output is unit-length even without the flag (verified: norm = 1.0). DocMind normalises three times in total (model, flag, `normalize_rows`); harmless and redundant. |
| PROJECT_GUIDE §16 | Strong matches score "0.5 or more". | In this repo's own runs, correct top-1 hits scored 0.35–0.47 (e.g. "laptop stolen" 0.40, "desk" 0.467, "internet reimbursed" 0.355). Treat score ranges as corpus-dependent; don't quote 0.5 as a rule. |
| `config.py` comment on `llm_temperature` | "ignored by providers/models that don't accept it" | It is **always** ignored by `AnthropicClient` (never passed) and always sent by `OpenAICompatibleClient`. `.env.example` lists `LLM_TEMPERATURE` without saying this. |
| README → "Provider-agnostic LLM layer … any OpenAI-compatible endpoint" | Works with any compatible API. | The client always sends `max_tokens` and `temperature`. Some newer OpenAI models reject these parameters (they expect `max_completion_tokens` / a default temperature). **No real provider has been called from this code**, so "any" is unverified. |
| README → `CLASSIFIER_LABELS` "configurable" | Categories are configurable. | Only in zero-shot mode. A trained model uses the classes it was trained on (`classifier.py:92–97`) and ignores `CLASSIFIER_LABELS`. |
| Streamlit upload limit | `MAX_UPLOAD_MB` controls the upload limit. | The API uses `MAX_UPLOAD_MB`; the Streamlit widget limit is hard-coded to 25 in `.streamlit/config.toml`. They can drift apart. |
| PROJECT_GUIDE §15 | "fine-tuned … on over a billion sentence pairs" | Comes from the public model card; it cannot be verified from this repository. Say "according to the model card". |

### 0.3 Things that have never been exercised

- **`AnthropicClient` has never been called**, neither by a test nor live. All QA tests use `FakeLLM`; the OpenAI-compatible client is tested only with `httpx.MockTransport`.
- **The `--qa` evaluation has never been run.** No QA numbers exist.
- **Docker has never been built or run** (Docker was not installed).

---

## Part 1. Complete execution flow

### End-to-end data flow

```
Browser
  │  (Streamlit widgets)
  ▼
frontend/streamlit_app.py ──requests──▶ FastAPI app/api.py ──▶ DocMindService app/service.py
                                                              │
 UPLOAD   /documents/upload ─▶ service.upload ─▶ sanitize_filename ─▶ validate_pdf_upload ─▶ sha256 → doc_id
                                                 └─▶ data/raw/<doc_id>.pdf + registry(status=uploaded)
 PROCESS  /documents/process ─▶ service.process ─▶ _process_one:
            extract_pages (PyMuPDF) ─▶ preprocess_pages ─▶ chunk_pages ─▶ Embedder.embed (MiniLM, 384-d, unit)
            ─▶ FaissVectorStore.add ─▶ classifier.classify(document_embedding) ─▶ registry(processed)
            ─▶ store.save()  [index.faiss + metadata.json + manifest.json]
 SEARCH   /search ─▶ service.search ─▶ Retriever.search ─▶ embed_query ─▶ store.search (IndexFlatIP) ─▶ SearchResult[]
 ASK      /ask ─▶ service.ask ─▶ answer_question ─▶ Retriever.search ─▶ build_context ─▶ build_user_prompt
            ─▶ LLMClient.generate ─▶ extract_citations ─▶ QAResult(answer, sources, cited, invalid)
  ▲                                                                                        │
  └──────────── JSON (Pydantic response models) ◀──────────────────────────────────────────┘
```

### Stage-by-stage

| Stage | File → function | Input | Processing | Output | Key design decision |
|---|---|---|---|---|---|
| **A. Upload** | `frontend/streamlit_app.py:97` → `api.upload_documents` (`api.py:93`) → `DocMindService.upload` (`service.py:76`) | multipart files | Cap of 20 files; read ≤ limit+1 bytes; `sanitize_filename`; `validate_pdf_upload` (extension, `%PDF-` within the first 1024 bytes, size); `compute_document_id` = `sha256[:16]`; duplicate check in the registry; atomic write to `data/raw/<doc_id>.pdf`; `DocumentRecord(status="uploaded")` | `UploadResponse{items: [uploaded / duplicate / rejected]}`, HTTP 201 (or 400 if all rejected) | Files stored under their **content hash**, never the user's filename, which gives dedup for free and makes path traversal impossible. |
| **B. Process** | `api.process_documents` (`api.py:128`) → `service.process` (`service.py:97`) → `_process_one` (`service.py:126`) | `{"doc_ids"?, "force"}` | Selects targets; under `_write_lock`, skips documents already processed *and* present in the index; for the others: remove old vectors → extract → preprocess → chunk → embed → add → classify → update the registry; then `store.save()` once | `ProcessResponse{items, indexed_chunks}` | Never re-embeds processed documents; per-document failures become `status="failed"` with a readable error instead of crashing the batch. |
| **C. Extract** | `ingestion.extract_pages` (`ingestion.py:60`) | PDF bytes, name, id | `pymupdf.open(stream=…)`; reject encrypted (`needs_pass`) or zero-page files; for each page `get_text("text", sort=True)`; pages with fewer than `MIN_CHARS_PER_PAGE` non-whitespace characters go to `empty_pages`; warnings for textless or mostly empty PDFs | `ExtractionResult{pages: [PageText], empty_pages, warnings, page_count}` | Page-by-page extraction keeps the page number that citations need; `sort=True` gives a more natural reading order. |
| **D. Preprocess** | `preprocessing.preprocess_pages` (`:86`) → `find_repeated_lines` (`:74`), `clean_text` (`:57`) | `[PageText]` | Drops short lines repeated on ≥60% of pages (3+ page docs); then NFKC + ligature fix, invisible characters removed, de-hyphenation, number-only lines removed (see F1), spaces collapsed, wrapped lines joined into paragraphs (bullets kept on their own line) | cleaned `[PageText]` (pages that end up empty are dropped) | Deliberately light cleaning: no lowercasing, stop-word removal or stemming. |
| **E. Chunk** | `chunking.chunk_pages` (`:95`) → `chunk_text` (`:61`) | cleaned pages, `CHUNK_SIZE=800`, `CHUNK_OVERLAP=150` | Split into sentences (`_SENTENCE_BOUNDARY`, `:27`); split over-long sentences on words; greedily pack sentences up to the size; carry trailing whole sentences as overlap | `[Chunk(chunk_id="doc:p3:c0", doc_id, doc_name, page_number, chunk_index, text)]` | Chunks **never cross pages**, so citations are exact; deterministic output. |
| **F. Embed** | `embeddings.Embedder.embed` (`:66`), model cached by `load_sentence_transformer` (`:27`, `lru_cache`) | list of chunk texts | `SentenceTransformer.encode(batch_size=32, normalize_embeddings=True)` → float32 → `normalize_rows` | `ndarray (n, 384)`, unit rows | Unit vectors make inner product = cosine; the model is loaded once per process. |
| **G. Store** | `vector_store.FaissVectorStore.add` (`:67`), `save` (`:130`) | chunks + embeddings | Assign new int64 IDs from `_next_id`; `IndexIDMap2.add_with_ids`; metadata dict `{id: chunk.to_dict()}`; save = `serialize_index` + atomic writes; manifest written last | files in `data/index/` | IDs never reused; a manifest check on load catches drift or a model change. |
| **H. Search** | `api.search` (`api.py:169`) → `service.search` (`:205`) → `Retriever.search` (`retrieval.py:20`) → `store.search` (`vector_store.py:97`) | `{"query", "top_k"?, "doc_ids"?}` | Pydantic validation; clamp top_k to 1..20; `embed_query`; `IndexFlatIP.search`; map IDs → metadata → `Chunk`; optional filter by document | `SearchResponse{results: [SearchHit(rank, score, chunk_id, doc_name, page_number, text)]}` | Same model for queries and documents; exact search. |
| **I. Ask** | `api.ask` (`api.py:175`) → `service.ask` (`:208`) → `qa.answer_question` (`qa.py:51`) | `{"question", "top_k"?, "doc_ids"?}` | Lazy LLM creation (503 if unconfigured); retrieve; if nothing is retrieved, return `NOT_FOUND_ANSWER` with no LLM call | see J/K | Search works without a key. |
| **J. Chunks → LLM** | `prompts.build_context` (`:28`), `build_user_prompt` (`:50`), `SYSTEM_PROMPT` (`:12`), `llm.timed_generate` (`:157`) | ranked results | Number the sources `[Source n] (document, page)` until `MAX_CONTEXT_CHARS=6000`; wrap them in `<sources>`; system rules require grounding and citations | answer string from the LLM | Bounded prompt; only included sources can be displayed. |
| **K. Answer + sources** | `qa.extract_citations` (`:40`), `is_abstention` (`:47`), `api.ask` builds `SourceOut` | answer text, included results | Parse `[n]` markers; split into valid ones (1..n) and `invalid_citations`; `answered_from_documents = not abstained and at least one valid citation` | `AskResponse{answer, sources[source_number, cited, …], invalid_citations, answered_from_documents, model}` | Sources are exactly what was in the prompt; hallucinated citation numbers are surfaced, not shown as sources. |
| **L. UI display** | `streamlit_app.py` tabs (`:130`) | JSON | Search: expanders labelled rank · doc · page · score. Ask: answer, warnings, sources sorted cited-first. Documents: pandas table, classification bar chart | rendered page | No ML logic in the UI. |
| **M. API exposure** | `api.create_app` (`api.py:43`) | HTTP | `lifespan` builds one service; `Depends(get_service)`; exception handlers | JSON / status codes | Routes are thin adapters over the service (Part 9). |

---

## Part 2. Codebase map

| File | Responsibility | Key functions/classes | Called by | Calls | Receives → returns | Why separate |
|---|---|---|---|---|---|---|
| `app/config.py` | Read and validate configuration | `Settings`, `load_settings`, `get_settings` (cached), `validate`, `ensure_dirs`, derived paths | service, api lifespan, main, evaluate | `python-dotenv`, `os.getenv` | env vars → `Settings` | One place that reads the environment; everything else takes `Settings`, so tests can inject temp paths. |
| `app/ingestion.py` | Accept or reject bytes; extract page text | `validate_pdf_upload`, `compute_document_id`, `extract_pages`, `ExtractionResult`, `IngestionError` | service | PyMuPDF, `utils.sha256_bytes` | bytes → `ExtractionResult` | Isolates the PDF library; could be swapped for another extractor. |
| `app/preprocessing.py` | Clean PDF artifacts | `clean_text`, `find_repeated_lines`, `preprocess_pages`, `normalize_unicode` | service, notebook | `re`, `unicodedata` | `[PageText]` → `[PageText]` | Pure functions: easy to unit-test. |
| `app/chunking.py` | Split text into retrievable units | `chunk_text`, `chunk_pages`, `split_sentences`, `make_chunk_id` | service, notebook | – | pages → `[Chunk]` | Chunking is a tunable, testable algorithm on its own. |
| `app/embeddings.py` | Text → vectors | `Embedder` (`embed`, `embed_query`, `dimension`), `load_sentence_transformer`, `normalize_rows`, `EncoderModel` protocol | service, retriever, classifier, evaluate, notebook | sentence-transformers (→ PyTorch, HF Hub) | `[str]` → `ndarray (n, 384)` | Hides the model; tests inject `HashingEncoder`. |
| `app/vector_store.py` | Vector index + metadata + persistence | `FaissVectorStore` (`add`, `search`, `remove_document`, `save`, `load_or_create`), `VectorStoreError` | service, retriever | FAISS, NumPy, `utils` atomic writes | vectors/chunks ↔ `[(Chunk, score)]` | Keeps FAISS details and the sync logic in one place. |
| `app/retrieval.py` | Query → ranked results | `Retriever.search` | service, qa | `Embedder`, `FaissVectorStore` | `str, k` → `[SearchResult]` | A shared step for search and RAG. |
| `app/prompts.py` | Prompt text + context building | `SYSTEM_PROMPT`, `NOT_FOUND_ANSWER`, `build_context`, `build_user_prompt`, `format_source` | qa, evaluate (`is_abstention` via qa) | – | results → `(context, included)` | Prompts change often; keeping them apart from logic makes that safe. |
| `app/llm.py` | Provider abstraction | `LLMClient` (ABC), `AnthropicClient`, `OpenAICompatibleClient`, `create_llm_client`, `timed_generate`, `LLMError`, `LLMNotConfiguredError` | service, qa | `anthropic` SDK, `httpx` | `(system, user)` → `str` | Provider logic lives in one file; the rest of the app is provider-neutral. |
| `app/qa.py` | The RAG step + citation checks | `answer_question`, `extract_citations`, `is_abstention`, `QAResult` | service | retriever, prompts, llm | question → `QAResult` | Separates "RAG logic" from "how to call a model". |
| `app/classifier.py` | Document category | `DocumentClassifier` (`classify`, `classify_text`, `mode`), `document_embedding`, `train_classifier`, `load_training_data`, `CATEGORY_DESCRIPTIONS` | service, main (training) | Embedder, scikit-learn, joblib, pandas | doc vector → `ClassificationResult` | Optional ML component, independent of search. |
| `app/models.py` | Data shapes | Dataclasses `PageText`, `Chunk`, `SearchResult`, `ClassificationResult`, `DocumentRecord`; Pydantic `*Request`/`*Response`/`SearchHit`/`SourceOut`/`DocumentOut` | everything | pydantic | – | One place to see internal objects next to the API contract. |
| `app/registry.py` | Persist document records | `DocumentRegistry` (`get`, `all`, `upsert`, `delete`) | service | `utils` atomic JSON | records ↔ `documents.json` | Keeps document status separate from vectors. |
| `app/service.py` | Orchestrate everything | `DocMindService` (`upload`, `process`, `_process_one`, `search`, `ask`, `list/get/delete_document`, `llm` property), `DocumentNotFoundError` | api, main, evaluate, tests | all of the above | – | **Single implementation** of the pipeline, reused by every entry point. |
| `app/api.py` | HTTP layer | `create_app`, `lifespan`, routes, exception handlers; module-level `app` | uvicorn, tests | service, models | HTTP ↔ Pydantic | Transport concerns only. |
| `app/utils.py` | Shared helpers | `setup_logging`, `sha256_bytes`, `sanitize_filename`, `atomic_write_bytes/json`, `read_json` | many | stdlib | – | Avoids duplicating small utilities. |
| `frontend/streamlit_app.py` | UI | `api_request`, `show_passage`, sidebar/tabs script | the user | the API over HTTP | widgets ↔ JSON | UI knows nothing about ML. |
| `main.py` | CLI | `run_api`, `run_ui`, `run_ingest`, `run_train_classifier`, `main` | the user | uvicorn, streamlit subprocess, service, classifier | args → exit code | Convenience entry points. |
| `evaluation/evaluate.py` | Measure quality | `precision_at_k`, `recall_at_k`, `hit_at_k`, `reciprocal_rank`, `token_f1`, `build_eval_service`, `evaluate_retrieval`, `evaluate_qa` | the user, tests (metrics only) | service, pandas | dataset → CSV / JSON | Measures the real pipeline in an isolated temp dir. |
| `notebooks/pipeline_walkthrough.ipynb` | Learning aid | cells calling `extract_pages`, `preprocess_pages`, `chunk_pages`, `Embedder`, manual cosine | the user | app modules | – | Shows the intermediate outputs; does not re-implement anything. Requires Jupyter (not in `requirements.txt`). |

---

## Part 3. NLP concepts actually used

| Concept | Meaning | Where in DocMind | Why needed | Without it | Likely interview question |
|---|---|---|---|---|---|
| Text preprocessing | Normalising raw text before modelling | `preprocessing.clean_text`, `find_repeated_lines` | PDF layout artifacts (broken lines, hyphenation, headers) pollute chunks and embeddings | Headers repeated in every chunk; words split in two; worse matches | "Why didn't you lowercase or remove stop words?" (the model's own tokenizer lowercases; stop words carry meaning for transformers) |
| Unicode normalisation | Mapping equivalent characters to one form | `normalize_unicode` (NFKC, ligatures) | `ﬁ` vs `fi` would tokenise differently | "ﬁnance" might not match "finance" | "What is NFKC?" |
| Sentence segmentation (rule-based) | Splitting text into sentences | `chunking._SENTENCE_BOUNDARY` regex | Chunk boundaries at sentence ends keep statements intact | Chunks cut mid-sentence | "How does your splitter handle 'e.g.'?" (badly: it splits there; a known limitation) |
| Chunking with overlap | Fixed-budget segments sharing some text | `chunk_text` | Model input limit (256 word-pieces); focused vectors; exact citations | Truncated embeddings, vague matches | "What trade-off does overlap make?" |
| Tokenisation (WordPiece, inside the model) | Splitting into subword units | inside `SentenceTransformer` (uncased BERT tokenizer) | Lets the model handle unseen words (`refunds` → `ref`, `##unds`) | – (not implemented by DocMind itself) | "What happens to text longer than 256 tokens?" (truncated) |
| Transformer sentence embeddings | A dense vector of a text's meaning from a transformer encoder | `Embedder.embed` with `all-MiniLM-L6-v2` | Enables matching by meaning | Keyword search only | "How is a sentence vector produced from token vectors?" (mean pooling) |
| Semantic similarity | How close two texts are in meaning | the scores in `store.search` | Ranking | – | "Is a score of 0.4 good?" (relative, corpus-dependent) |
| Cosine similarity | Angle-based similarity | normalised vectors + `IndexFlatIP` | Scale-invariant comparison | – | "Why inner product instead of L2?" |
| Semantic search | Retrieval by embedding similarity | `Retriever.search`, `/search` | Vocabulary mismatch ("money back" vs "refund") | Ctrl+F behaviour | "Semantic vs keyword search: when does each win?" |
| Dense retrieval (top-k) | Selecting the k nearest chunks | `store.search`, `TOP_K` | Bounded context for RAG | – | "How do you choose k?" |
| Context construction | Assembling retrieved text into a prompt | `prompts.build_context` | Numbered, attributed, bounded context | Unattributable answers, unbounded prompts | "What happens when the context is too long?" |
| Prompt engineering (instructional) | Rules given to the LLM | `SYSTEM_PROMPT`, `build_user_prompt` | Grounding, citation format, abstention | Ungrounded answers | "Why a fixed abstention sentence?" |
| RAG | Retrieve, then generate from the retrieved text | `qa.answer_question` | Answers about private documents, with sources | The LLM answers from memory | "RAG vs fine-tuning?" |
| Source attribution | Linking answer claims to sources | `[n]` citations, `extract_citations`, `SourceOut.cited` | Verifiability | The user can't check claims | "Can a valid citation still be wrong?" (yes) |
| Document classification | Assigning a category | `classifier.py` | Organising documents; demonstrates an ML pipeline | – | "Zero-shot vs supervised?" |
| Mean pooling (document level) | Averaging vectors | `document_embedding` | One vector per document | – | "What's lost by averaging?" |
| Lexical answer overlap (token F1) | A SQuAD-style evaluation metric | `evaluate.token_f1` | A crude QA score | – | "Why is token F1 a weak metric?" |

**Not used** (don't claim these): stemming or lemmatisation, stop-word removal, TF-IDF or BM25, named-entity recognition, query expansion, re-ranking, OCR, fine-tuning, language detection, NLI-based fact checking.

---

## Part 4. Deep learning and transformers

Verified by inspecting the loaded model object:

| Question | Answer (from the code and the loaded model) |
|---|---|
| Which model? | `sentence-transformers/all-MiniLM-L6-v2` (default in `config.py`, configurable via `EMBEDDING_MODEL`) |
| Architecture | `BertModel`, **6 layers, 12 attention heads, hidden size 384**, **22.7M parameters**; pipeline `Transformer → Pooling(mean) → Normalize` |
| Why selected | Small and fast on CPU, trained for sentence similarity, 384 dimensions keeps the index small. (No comparative evaluation against other models was done.) |
| Input | Raw strings (chunk texts or a query). The tokenizer is **uncased** WordPiece, and inputs are truncated at `max_seq_length = 256` tokens. |
| Output | One 384-dimensional float32 vector per input |
| Normalised? | Yes: by the model's own `Normalize` layer, by `normalize_embeddings=True`, and by `normalize_rows` (redundant but harmless) |
| Similarity | Inner product in FAISS `IndexFlatIP` = cosine similarity, because the vectors are unit length. The classifier's zero-shot mode also uses a dot product (`classifier.py:99`). |
| Pretrained? | Yes, downloaded from the Hugging Face Hub on first use and cached |
| Fine-tuned in this project? | **No.** Nothing in the repo trains or updates transformer weights. The only training is scikit-learn logistic regression on frozen embeddings. |
| PyTorch involved? | Only **indirectly**: sentence-transformers runs the model in PyTorch (CPU build installed). DocMind has no `import torch`. |
| Hugging Face involved? | Indirectly: sentence-transformers uses `transformers` + `huggingface_hub` to download and run the model. DocMind never calls `transformers` directly. |

### The theory you need (only as much as the implementation uses)

- **Neural representation / embeddings.** A neural network maps its input to vectors of numbers; after training, similar inputs map to nearby vectors. An *embedding* is such a learned vector. The individual 384 dimensions have no human meaning; only distances between vectors do.
- **Token embeddings → contextual representations.** The tokenizer turns text into word-piece IDs, and each ID starts as a lookup-table vector. Those are *static*: `bank` gets the same vector everywhere.
- **Attention (high level).** In each layer, every token computes how much to "attend to" every other token (a softmax over query·key scores) and takes a weighted mix of their value vectors. After 6 such layers, the vector for `bank` in "river bank" differs from the one in "bank account". That is a **contextual representation**.
- **Transformer encoder.** Stacked blocks of multi-head self-attention plus feed-forward layers, with residual connections and layer normalisation. MiniLM is a small encoder *distilled* from a larger model.
- **Sentence embeddings.** A transformer outputs one vector per token. sentence-transformers **mean-pools** them into one vector per text, and the model was trained (contrastively, per its model card) so that texts with similar meaning have high cosine similarity. That training objective is what makes the vectors useful for search; a plain BERT mean-pooled without it performs much worse at similarity.
- **Limits that matter here.** 256-token truncation (hence ~800-character chunks); English-centric training; lowercased input; no knowledge of your domain beyond pre-training.

---

## Part 5. FAISS

| Aspect | This implementation (`app/vector_store.py`) |
|---|---|
| What FAISS is | A C++ library (with Python bindings) for nearest-neighbour search over dense vectors. It stores vectors and integer IDs only, never text. |
| Index type | `faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))`, created in `__init__` (`:45`) |
| Why | `IndexFlatIP` gives **exact** inner-product search with no training step; `IndexIDMap2` allows custom 64-bit IDs and `remove_ids` (needed for delete and force re-processing). Approximate indexes (IVF, HNSW) only pay off at far larger scale. |
| What's stored | One unit-length 384-d float32 vector per chunk |
| Adding (`add`, `:67`) | Checks the counts match and the dimension equals `self.dimension`; `ids = arange(_next_id, _next_id + n)`; `add_with_ids(embeddings, ids)`; `metadata[id] = chunk.to_dict()`; `_next_id += n`, under an `RLock` |
| Searching (`search`, `:97`) | Reshape the query to (1, d), check the dimension, `self._index.search(query, fetch)` where `fetch = top_k` (or the whole index if a document filter is given); skip `-1` padding IDs; map each ID → metadata → `Chunk`; filter; stop at top_k |
| Returned scores | Inner products. Because both vectors are unit length, **score = cosine similarity** in [−1, 1], and higher is better. |
| Top-k | FAISS returns the k highest scores in descending order; `Retriever` numbers them rank 1..k; the service clamps k to 1..`max_top_k` (20). |
| Metadata mapping | `self._metadata: dict[int, dict]`, keyed by the same int IDs used in FAISS. IDs are never reused after deletion, so a stale ID can't point at a new chunk. |
| Persistence (`save`, `:130`) | `faiss.serialize_index(index)` → bytes → `atomic_write_bytes(index.faiss)`; `metadata.json`; `manifest.json` last (model, dim, next_id, size). Serialising to bytes avoids FAISS's own file I/O (which has trouble with non-ASCII Windows paths). |
| Loading (`load_or_create`, `:152`) | No manifest → new empty index. Otherwise: model or dimension mismatch → `VectorStoreError`; `deserialize_index`; load metadata; check `index.ntotal == len(metadata) == manifest.size`, else `VectorStoreError`. (A missing `index.faiss` gives a raw `FileNotFoundError`; see F4.) |

Each file write is atomic, but the three files are not written as one transaction. If a crash happens between writes, the size check on the next load detects the mismatch and refuses to start rather than serving wrong results.

**Cosine vs Euclidean here.** For unit vectors, ‖a − b‖² = ‖a‖² + ‖b‖² − 2a·b = 2 − 2cos(a, b). Ranking by the smallest L2 distance therefore gives exactly the same order as ranking by the largest cosine. DocMind uses an inner-product index so the returned number *is* the cosine (easy to show in the UI), rather than a distance you would have to convert. Without normalisation, inner product would favour vectors with a large norm, and L2 would be affected by norm too; normalisation removes that effect.

---

## Part 6. RAG, traced

| Step | Code |
|---|---|
| Question | `AskRequest.question` (strip + non-blank validator, `models.py:216`) |
| Query embedding | `Retriever.search` → `Embedder.embed_query` (`retrieval.py`, `embeddings.py:83`) |
| Vector search | `FaissVectorStore.search` (`vector_store.py:97`) |
| Retrieved chunks | `[SearchResult]`; if empty, `answer_question` returns `NOT_FOUND_ANSWER` with **no LLM call** (`qa.py`) |
| Context construction | `build_context(results, MAX_CONTEXT_CHARS)` (`prompts.py:28`): `[Source n] (document: X, page: Y)\n<text>` blocks in rank order, at least one included, stops at the budget, returns the `included` list |
| Prompt | `SYSTEM_PROMPT` (`prompts.py:12`) + `build_user_prompt` (`:50`): the context inside `<sources>` tags, then the question |
| LLM | `timed_generate` → `AnthropicClient.generate` or `OpenAICompatibleClient.generate` (`llm.py`) |
| Answer | Text blocks concatenated (Anthropic: non-text blocks such as thinking are ignored) |
| Citation validation | `extract_citations` (`qa.py:40`) → valid if 1 ≤ n ≤ len(included), otherwise listed in `invalid_citations`; `answered_from_documents = not is_abstention(answer) and bool(valid)` |
| Returned | `api.ask` builds `SourceOut` for **every included source** with `cited=(n in cited_numbers)` |

**Why RAG.** The LLM has never seen your PDFs. RAG supplies the relevant passages at question time, so answers can use private or new documents and point to their sources.

**Why not send the whole PDF.** Cost and latency grow with prompt length; a long document may exceed the context window; long contexts dilute the model's attention; and citations become vague. DocMind sends at most about 6,000 characters of the most relevant chunks.

**Hallucination** is fluent output not supported by the given sources (or by reality). Common causes: the relevant passage wasn't retrieved, the context is ambiguous, the question has a false premise, or the model over-generalises.

**How this implementation reduces it:**
1. Only retrieved passages are in the prompt.
2. The system prompt forbids outside knowledge and requires `[n]` citations.
3. There is an explicit, fixed "not found" sentence the model is allowed to use.
4. No LLM call is made when nothing is retrieved.
5. Citation numbers are checked, and invented ones are surfaced.
6. The UI shows the exact passages, cited ones first.
7. `answered_from_documents` flags answers that abstained or cited nothing.

**What remains:**
- A real source number can be cited for a claim that source doesn't support; there is no claim-level check.
- The model can still use outside knowledge; the prompt asks it not to, but nothing enforces that.
- There is no relevance threshold: top-k chunks are sent even if they are all weakly related, which the prompt must handle.
- F5 and F6 cause false warnings.
- Prompt injection from document text isn't handled.
- The LLM path has never been run against a real model.

**When the context doesn't contain the answer:** the prompt tells the model to reply with `NOT_FOUND_ANSWER`. `is_abstention` detects that sentence, so `answered_from_documents=False` and the UI shows a warning. Whether the model actually complies is untested.

---

## Part 7. Classification

| Aspect | Implementation (`app/classifier.py`) |
|---|---|
| Approaches | **Zero-shot** (default) and **supervised** logistic regression (when `data/classifier/classifier.joblib` exists and was trained with the same embedding model) |
| Model | Zero-shot: no trained model, just MiniLM embeddings of category descriptions. Supervised: `sklearn.linear_model.LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")` on frozen MiniLM embeddings |
| Input representation | `document_embedding(chunk_embeddings)` = normalised mean of the document's chunk vectors (reuses the vectors already computed for indexing) |
| Categories | `DEFAULT_CATEGORIES` in `config.py`: Research Paper, Report, Assignment, Notes, Policy, Other (configurable via `CLASSIFIER_LABELS`, zero-shot only) |
| Training | `python main.py train-classifier data.csv` → `load_training_data` (needs `text`/`label` columns; strip, drop blanks, dedupe, ≥2 labels) → embed the texts → `StratifiedKFold(n_splits=min(5, smallest class))` + `cross_val_predict` → accuracy, macro-F1, per-class report → fit on all data → `joblib.dump({"model", "embedding_model"})` → report JSON |
| Inference | `DocumentClassifier.classify` (`:92`). Supervised: `predict_proba` → label = argmax, and the scores are probabilities. Zero-shot: `label_vectors @ doc_vector` → label = argmax, and the scores are raw cosine similarities (not probabilities; the UI says so) |
| Zero-shot vs trained | Zero-shot needs no labels but depends on hand-written description wording and gives tiny margins (in the sample run, Policy 0.2218 vs Report 0.2208). Supervised learns a decision boundary from labelled examples, but is only as good as those examples. |
| Train/inference mismatch | Training uses embeddings of **short single paragraphs**; inference uses the **mean of many chunk embeddings of a whole document**. These are different input distributions. |

**Why the synthetic dataset is insufficient:** 48 texts (8 per class), all written by one person for this project, short, clean and stereotypical ("Abstract. We propose…"). Cross-validation on it (accuracy 0.81, macro-F1 0.81) measures how separable these particular texts are, not how the classifier performs on real PDFs. There is no held-out real test set. In the one observed trial, the supervised model labelled the ML lecture notes as "Research Paper", which shows it had picked up *topic* more than *document form*.

**Why the default behaviour is zero-shot.** The code was never changed. `DocumentClassifier` has always fallen back to zero-shot when no model file exists. During development a model was trained on the synthetic CSV; it then mislabelled one of the three sample documents. The trained artifact (`classifier.joblib`) was **deleted** so the app doesn't silently rely on a model trained on synthetic data. It is git-ignored and is only created if you run the training command.

**Status:** both modes are **demo functionality**. Neither has a measured accuracy on real documents.

---

## Part 8. Evaluation

### How retrieval is evaluated (`evaluation/evaluate.py`)
1. `main` loads `datasets/sample_eval.json` and copies the settings with `data_dir` set to a `tempfile.TemporaryDirectory`.
2. `build_eval_service` creates a fresh `DocMindService`, uploads every PDF in `evaluation/sample_docs/` (generating them if missing), and processes them. Any failure aborts the run.
3. `evaluate_retrieval` (`:131`): for each query, `service.search(query, top_k=max(K))`. Relevance labels are `(document, page)` pairs, or `relevant_chunk_ids` if given. The result is a boolean `relevance` list in rank order.
4. Per query and per K it computes the metrics below; `summary` averages them over queries; per-query rows go to `results/retrieval_per_query.csv`; `summary.json` records the run time, model, chunk settings and results.

### Definitions mapped to the code
| Metric | Definition | Code |
|---|---|---|
| top-k retrieval | Return the k chunks with the highest cosine similarity | `service.search(..., top_k=max_k)` then slicing `[:k]` |
| **Hit rate / Hit@K** | Fraction of queries with at least one relevant chunk in the top K | `hit_at_k` → `1.0 if any(relevance[:k])`, averaged as `hit_rate` |
| **Precision@K** | (# relevant chunks in top K) / K; divides by K even if fewer than K were returned | `precision_at_k` → `sum(relevance[:k]) / k` |
| **Recall@K** | (# distinct relevant pages in top K) / (# relevant pages); two chunks from one page count once | `recall_at_k` → `len(set(keys[:k]) & relevant) / len(relevant)` |
| MRR | Mean of 1 / rank of the first relevant chunk (0 if none within max K) | `reciprocal_rank` |

QA (`evaluate_qa`, only with `--qa` and a key; **never run**): token F1 vs the reference (answerable items), abstention flags, whether the context contained a relevant page, citation precision, count of invalid citations.

### Current dataset and its limitations
- 20 retrieval queries and 9 QA items (3 unanswerable) over **3 fictional PDFs, 9 pages, 11 chunks**, all written by the same author as the queries.
- Measured (reproduced during this audit): Hit@1 0.70, Hit@3 0.95, Hit@5 1.00, P@5 0.24, R@5 1.00, MRR 0.838.
- Why this is **not** evidence of production quality:
  - The sample is tiny; one query changes Hit@1 by 5 points.
  - The author knew the documents while writing the queries, so wording overlaps unrealistically.
  - With only 11 chunks, even a random ranker would often hit within top-5. A random ordering has P(relevant page in top-5) of roughly 5/11 per single-chunk page.
  - The documents are clean, single-column, synthetic text, with no tables or scans.
  - The labels were never independently checked.
  - There is no baseline (such as BM25) to compare against.
- Precision@5 = 0.24 is a property of the data: with one relevant page and 5 results, the maximum is about 0.2–0.4.

### What a better evaluation would look like
1. Real PDFs of the kinds the app targets (reports, policies, papers, including tables and multi-column layouts): 20+ documents, hundreds of pages.
2. Queries written by people who didn't write the documents (or collected from real users), 100+ of them, including unanswerable ones.
3. Relevance labelled by two annotators, with agreement measured.
4. Baselines: BM25 and random. Report the dense model's gain over them.
5. Compare configurations (chunk size and overlap, embedding model, top-k), choosing on a dev split and reporting on a held-out test split.
6. Report confidence intervals (e.g. bootstrap), not single numbers.
7. For QA: human or validated LLM-judge ratings of faithfulness (is each claim supported by its cited passage?) and correctness, not just token F1.
8. Error analysis: categorise the failures (vocabulary mismatch, table content, page-split answers).

---

## Part 9. API architecture (`app/api.py`)

| Method | Path | Request | Response | Validation | Status codes | Service call |
|---|---|---|---|---|---|---|
| GET | `/health` | – | `HealthResponse` (version, embedding model, LLM provider/model, `llm_configured`, documents, indexed_chunks) | – | 200 | reads `svc.settings`, `svc.registry`, `svc.store` |
| POST | `/documents/upload` | multipart `files` (≥1 required) | `UploadResponse{items}` | ≤20 files; per file: sanitise, extension, magic bytes, size, dedup | 201; 400 (>20 files, or all rejected); 422 (no files) | `svc.upload` |
| POST | `/documents/process` | optional `ProcessRequest{doc_ids?, force}` | `ProcessResponse{items, indexed_chunks}` | Pydantic | 200; 404 unknown ID | `svc.process` |
| GET | `/documents` | – | `list[DocumentOut]` | – | 200 | `svc.list_documents` |
| GET | `/documents/{doc_id}` | path | `DocumentOut` | – | 200; 404 | `svc.get_document` |
| DELETE | `/documents/{doc_id}` | path | empty | – | 204; 404 | `svc.delete_document` |
| POST | `/search` | `SearchRequest{query 1–2000 chars non-blank, top_k 1–20?, doc_ids?}` | `SearchResponse` | Pydantic field constraints + `_not_blank` | 200; 422 | `svc.search` |
| POST | `/ask` | `AskRequest{question, top_k?, doc_ids?}` | `AskResponse` | same | 200; 422; 503 no LLM; 502 LLM failure | `svc.ask` |

Global handlers: `VectorStoreError` → 500 with its message; any other exception → 500 "Internal server error" (logged with a traceback).

**Why routes contain no business logic.** Every route follows the same pattern: validate, call one service method, convert the result or exception into HTTP. The pipeline lives in `DocMindService`, so the CLI (`main.py ingest`), `evaluate.py` and the tests run the *same* code without HTTP. Changing the web framework or adding a CLI command doesn't touch the ML logic, and the logic can be unit-tested without a server.

**Role of Pydantic.**
- Requests are parsed and validated from JSON (types, lengths, ranges, custom validators), and FastAPI returns 422 automatically with field-level errors.
- `response_model` filters and serialises outputs and documents them in OpenAPI (`/docs`).
- Converters (`DocumentOut.from_record`, `SearchHit.from_result`) keep the mapping from internal dataclasses to API objects explicit.

Other details:
- **App factory + lifespan.** One service (model + index) per process; tests inject a fake service.
- **Dependency injection.** `Depends(get_service)` hands each route the service.
- **Sync vs async.** Sync `def` routes run in a thread pool. The upload route is `async` but calls the synchronous `svc.upload`, which does hashing and a disk write, so it briefly blocks the event loop. That is negligible for a local app.

---

## Part 10. Streamlit (`frontend/streamlit_app.py`)

- **Page structure:**
  - Title.
  - **Sidebar** (`:59`): backend status from `/health`, a warning if no LLM, a top-k slider (1–20, default 5), a document-filter multiselect (processed docs only), and the document list with status, category, pages and chunks.
  - **Section 1:** uploader, *Upload & process* and *Process pending documents* buttons.
  - **Section 2:** three tabs (`:130`): *Semantic search*, *Ask a question*, *Documents & classification*.
- **Upload flow** (`:97`): `POST /documents/upload` with the bytes of every selected file → info or warning per item → collect the returned `doc_id`s (including duplicates) → `POST /documents/process {"doc_ids": ids}` with a 900 s timeout under a spinner → success, "already indexed" or error per document, plus extraction warnings.
- **Processing flow** (`:120`): the *Process pending documents* button calls `/documents/process {}` (every document not yet processed). It is enabled only if some document isn't processed, judged by the list loaded at the top of the run.
- **Search flow** (`:133`): `st.form` → `POST /search` → one expander per hit (`show_passage`) showing rank, document, page, score and the passage text.
- **QA flow** (`:153`): the form's submit button is disabled without an LLM → `POST /ask` (180 s timeout) → answer markdown; warnings for `answered_from_documents=False` and `invalid_citations`; sources sorted cited-first, each an expander labelled "cited" or "retrieved, not cited".
- **Classification flow** (Documents tab): a pandas table of all documents; a selectbox to inspect one; its errors and warnings; predicted label, method, and a bar chart of the scores, with a caption explaining probabilities vs similarities; a *Delete* button (`:227`, no confirmation) → `DELETE` → `st.rerun()`.
- **Communication:** only HTTP via `requests` to `DOCMIND_API_URL`. No `app.*` imports.
- **State management:** no `st.session_state` is used. Streamlit re-runs the script on every interaction, and state lives in the API. Forms batch inputs so typing doesn't trigger requests. Results are not kept across re-runs, and the sidebar can be one step stale (F7).
- **Error handling:** `api_request` converts connection errors ("Is it running?"), timeouts and HTTP errors (including FastAPI's 422 detail lists) into `APIError`, and each handler shows it with `st.error`. If `/health` fails, the page stops after the sidebar (`st.stop()`, `:91`).

---

## Part 11. Security audit

| Item | Status | Details |
|---|---|---|
| Path traversal | **SECURE** | Uploads are stored as `raw_dir / f"{doc_id}.pdf"`, where `doc_id` is a hex hash (`service._raw_path`). Path parameters (`/documents/{doc_id}`) are looked up in the registry first and give 404 if unknown, so an arbitrary string never reaches a filesystem path. |
| Unsafe filenames | **SECURE** | `sanitize_filename` strips directories (both separators), allows only `[A-Za-z0-9._ -]`, trims length, and is tested with traversal inputs. The sanitised name is used only for display and in prompts. |
| File type validation | **SECURE** (for its purpose) | Extension check + `%PDF-` magic bytes in the first 1 KB + parse attempt. Files are never executed. The remaining risk is the PDF *parser* (MuPDF, C code) processing untrusted input in-process, with no sandbox. |
| File size limits | **NEEDS ATTENTION** | The per-file `MAX_UPLOAD_MB` check happens *after* Starlette has received and spooled the whole upload (to disk above 1 MB). There is no request-body limit at the server, and 20 × 25 MB per request is allowed. There is no page-count or processing-time limit, so a small PDF with a huge number of pages could tie up the CPU. The Streamlit limit is a separate hard-coded value. |
| API key handling | **NEEDS ATTENTION** (minor) | The key is read only from the environment and never logged, and it is sent only as an auth header. However, `Settings` is a plain dataclass whose `repr` **includes `llm_api_key`** (verified), so any future `logger.info(settings)` or traceback that prints locals would leak it. Nothing does this today. |
| Environment variables | **SECURE** | `.env` is git-ignored and docker-ignored, and it was verified not committed. `.env.example` has empty placeholders. Compose passes the whole `.env` to the API container only. |
| Sensitive logging | **SECURE** | Queries and document text are not logged (only lengths, counts, IDs, timings). LLM calls log prompt and answer *sizes*. Up to 300 characters of an LLM provider's error body can be logged and returned in a 502. Uvicorn access logs contain paths (document IDs). |
| Arbitrary file execution | **SECURE**, with one caveat | No `eval`, `exec` or shell on user input. `subprocess.call` in `main.run_ui` uses fixed arguments. The caveat: `joblib.load` (pickle) of the classifier file would execute code from a malicious file, so only use model files you created (the code comment says so). |
| Unsafe file paths | **SECURE** | All paths derive from `DATA_DIR` (trusted configuration) plus fixed names or hashes. Atomic writes use `tempfile.mkstemp` in the target directory. |
| Authentication / authorisation | **NOT IMPLEMENTED** | Anyone who can reach the API can upload, list, read passages from, and delete documents. `main.py api` binds to 127.0.0.1 (safe by default), but the Docker/compose setup binds 0.0.0.0 and publishes ports 8000 and 8501. |
| Rate limiting | **NOT IMPLEMENTED** | Unlimited `/ask` calls spend the owner's LLM credits. |
| Prompt injection via document content | **NEEDS ATTENTION** | Retrieved text is placed in the prompt verbatim. A PDF containing "ignore previous instructions…" could steer the answer. Mitigation is limited to the system prompt and the `<sources>` delimiters. |
| CORS | Not configured | Not needed, because Streamlit calls the API server-side. |

**No critical bug was found, so no code was changed.**

---

## Part 12. Testing

| File (count) | Covers | Mocked / real |
|---|---|---|
| `test_ingestion.py` (18) | Page-by-page extraction and metadata; empty pages; content-hash IDs; textless and mostly-empty warnings; malformed PDF; invalid extension, empty, fake-PDF, oversized; filename sanitising (traversal); service dedup + hash storage; textless PDF → `failed` | Real PyMuPDF on PDFs generated in memory; fake embedder |
| `test_preprocessing.py` (10) | Empty input; wrapped lines; de-hyphenation; punctuation preserved; page-number lines; ligatures and invisible characters; bullets; repeated headers; page numbering kept | Pure functions |
| `test_chunking.py` (14) | Size limit; lossless with no overlap; overlap = trailing sentence; determinism; long sentence; giant token; empty/short input; invalid parameters; metadata + page boundaries + unique IDs | Pure functions |
| `test_embeddings.py` (7) | Wrapper normalisation, including zero vectors; empty input; query shape; document mean pooling; **real model**: shape + unit norm, determinism, one paraphrase-vs-unrelated similarity check | Real MiniLM (skipped if unavailable) + fake encoders |
| `test_retrieval.py` (14) | Ranking; score = cosine (identical text → 1.0); top-k cap; doc filter; empty index; invalid queries; add validation; save/load round trip; remove + no ID reuse; model-mismatch refusal; manifest-size mismatch; **no re-embedding** of processed docs; force re-process doesn't duplicate | Real FAISS; `HashingEncoder` |
| `test_qa.py` (13) | Citation parsing formats; abstention detection; context budget + numbering; at least one source; full ask with prompt contents, page, cited and invalid citations; empty index → no LLM call; abstention not grounded; OpenAI-compatible request and 5 error cases | `FakeLLM`; `httpx.MockTransport` |
| `test_classifier.py` (5) | Zero-shot scores all labels; training saves the model and reports CV; supervised prediction; embedding-model mismatch ignored; CSV validation and cleaning; ≥2 labels | Fake encoder, real scikit-learn |
| `test_api.py` (15) | Health; **full flow** upload→process→documents→search→ask; duplicate; non-PDF → 400; mixed upload; no files → 422; 5 search validation cases; ask validation; process unknown → 404; get/delete lifecycle; no LLM → 503 | `TestClient` in-process, fake embedder, fake LLM |
| `test_evaluation.py` (4) | Precision/hit/MRR; precision divides by K; recall counts distinct pages; token F1 normalisation | Pure functions |

**End-to-end:** `test_api.py::test_full_flow_upload_process_search_ask` exercises every layer except Streamlit, but with a *hashing* embedder and a *fake* LLM, so it proves the plumbing works, not that the answers are good.

**Not tested:**
- `AnthropicClient` (at all).
- Real LLM behaviour (grounding, abstention, citation format).
- Streamlit.
- The `main.py` CLI.
- `evaluate_retrieval`, `evaluate_qa` and `build_eval_service` (only the metric functions are tested).
- Encrypted PDFs.
- Oversized uploads through the API.
- Service restart with an existing data dir (registry + index together), including the F3 drift case.
- A missing index file (F4).
- Numeric content surviving preprocessing (F1 went unnoticed because of this).
- Header removal on real PDFs.
- Retrieval quality with the real model beyond one sanity check.
- Concurrency.
- Docker.

**Why 100 passing tests ≠ a correct application.**
- Tests only check what someone thought to assert. F1 deletes table numbers, yet every preprocessing test passes because none of them contains a table.
- Most tests use fake embeddings and a fake LLM, so they verify control flow, not semantic quality.
- The test count measures effort, not coverage or correctness.
- Retrieval quality and answer quality are *empirical* properties that need evaluation data, not unit tests.

### The 5 most important missing tests (not added)
1. **Preprocessing preserves numeric content.** Table-like input (years, amounts on their own lines) must survive `clean_text`. This would have caught F1.
2. **`AnthropicClient` with a mocked SDK.** Joins only text blocks (ignores thinking blocks); `stop_reason="refusal"` → `LLMError`; empty response; auth, rate-limit and connection error mapping.
3. **Restart and consistency at the service level.** Process, construct a new `DocMindService` on the same data dir, then search works and registry = index; plus the drift case (F3) and a missing `index.faiss` (F4).
4. **Retrieval regression with the real model.** Run the sample evaluation in a test and assert Hit@3 stays above a floor, so changes to chunking or preprocessing can't silently degrade retrieval.
5. **Upload and processing edge cases via the API.** An oversized file through `/documents/upload` → rejected; an encrypted PDF → `failed` with the password message; more than 20 files → 400.

---

## Part 13. Docker (unverified)

| Aspect | `Dockerfile` / `docker-compose.yml` |
|---|---|
| Base image | `python:3.11-slim` |
| Dependencies | `pip install --index-url https://download.pytorch.org/whl/cpu torch` first (avoids the CUDA wheels), then `requirements.txt`. The image includes `pytest`, which isn't needed at runtime. |
| Model | Build arg `EMBEDDING_MODEL`; a `RUN` step downloads it into `HF_HOME=/app/.cache/huggingface` at build time |
| Code copied | `app/`, `frontend/`, `evaluation/`, `main.py`, `.streamlit/`, sample classifier CSV + README |
| User | A non-root `docmind` user; `/app` is chown'd to it |
| Startup | `CMD uvicorn app.api:app --host 0.0.0.0 --port 8000` |
| Ports | 8000 (API), 8501 (UI) |
| Compose `api` | `build: .`, `env_file: .env` (**the file must exist**), `DATA_DIR=/app/data`, bind mount `./data:/app/data`, healthcheck calling `/health` with Python's urllib |
| Compose `ui` | Same image; `command: streamlit run … --server.address 0.0.0.0`; `DOCMIND_API_URL=http://api:8000` (compose DNS name); `depends_on: api: service_healthy` |
| Relationship | Two containers; the UI calls the API over the compose network; only the API has the data volume and the `.env` secrets |

**Unverified, because Docker was not available:**
- Whether the image builds at all: the CPU wheel index, the dependency resolution, and the model download step.
- The image size.
- Whether the container starts and loads the baked model without network access (sentence-transformers may still contact the Hub).
- Whether the non-root user can write to the bind-mounted `./data`. On Linux hosts, UID mismatches commonly cause permission errors; Docker Desktop on Windows/macOS usually doesn't.
- Whether the healthcheck passes within its timing.
- Whether the UI container reaches `http://api:8000`, and whether `.streamlit/config.toml` is picked up (it depends on the working directory being `/app`).
- The `ui` service reuses `image: docmind:latest` built by `api`; this relies on compose building `api` first, which it should but hasn't been observed.

Do not claim "Dockerized" or "containerized deployment" until `docker compose up --build` has been run successfully and the full flow tested in the containers.
