# DocMind: Interview Preparation

Every model answer below describes what the code **actually** does. Where an honest answer includes "not implemented" or "not measured", say so in the interview; a precise limitation is more convincing than a vague claim. File references point into this repository; see `docs/CODE_WALKTHROUGH.md` for the detailed trace.

Format for each question: **Testing** (what the interviewer wants to learn) · **Key points** · **Model answer**.

---

## Part 15. "Explain this project" at four lengths

### 30 seconds
DocMind is a local app where you upload PDFs and then search them by meaning or ask questions about them. It extracts text page by page with PyMuPDF, cleans it, splits it into chunks, embeds them with a sentence-transformer and indexes them in FAISS. Questions are answered by an LLM using only the retrieved passages, with page-level citations that the code verifies. I built the RAG pipeline directly, without LangChain, so I could understand every step, and I wrote an evaluation script with retrieval metrics.

### 1 minute
The problem: keyword search fails when your wording differs from the document's, and a general chatbot hasn't seen your documents.

On upload, DocMind validates the file, hashes it for deduplication, and extracts text per page. It removes PDF artifacts like broken lines and repeated headers, then makes sentence-aware chunks of about 800 characters that never cross a page, so every citation points to one exact page. Chunks are embedded with all-MiniLM-L6-v2 into 384-dimensional unit vectors and stored in a FAISS inner-product index, so the scores are cosine similarities.

Search embeds the query and returns the top-k chunks. For questions, the top chunks are numbered as sources in a prompt that tells the LLM to answer only from them, cite them, or say it couldn't find the answer. The code then checks that every cited number really was provided.

There's also a zero-shot document classifier, a FastAPI backend serving a React interface with interactive citations and a settings page with an evaluation lab, 221 tests, and an evaluation script for Hit@K, Precision@K, Recall@K and MRR. It currently runs on a small demo dataset, so I don't treat those numbers as real performance.

### 3 minutes (technical)
1. **Architecture.** Three layers. A React single-page app is only a client of the FastAPI API under `/api`; in production FastAPI also serves the built app, so they share one origin. The routes are thin: they validate with Pydantic and call one method on a `DocMindService` class, which orchestrates the pipeline modules. The CLI, the evaluation script and the tests all use that same service, so there's one implementation of the pipeline.
2. **Ingestion.** Uploaded bytes are checked for a `.pdf` extension, the `%PDF-` magic bytes and a size limit, then SHA-256 hashed. The first 16 hex characters are the document ID, which gives duplicate detection, and the file is stored as `<hash>.pdf`, so user filenames never become paths. PyMuPDF extracts text per page; near-empty pages are recorded, and a fully textless PDF is reported as probably scanned, since there's no OCR.
3. **Preprocessing** is deliberately light: Unicode normalisation, joining words hyphenated across lines, merging layout-wrapped lines, and removing repeated headers and footers detected as short lines on at least 60% of pages. (An audit found that the original page-number rule deleted every number-only line, such as table cells. I fixed it: now only "Page N" labels, or a bare number at the top or bottom of a page that equals the page number, are removed, and there are regression tests.)
4. **Chunking.** A greedy sentence packer up to 800 characters with 150 characters of overlap made of whole trailing sentences, per page. It's deterministic, and the tests check the size limit, that the chunks are lossless, and the overlap.
5. **Embedding and index.** MiniLM is a 6-layer BERT with mean pooling and normalisation, 22.7M parameters, and 256-token truncation, which is why chunks are about 800 characters. FAISS `IndexIDMap2(IndexFlatIP)` does exact search, with custom IDs so documents can be deleted. Metadata sits in a dict keyed by the same IDs. Saving is atomic, and a manifest detects a changed embedding model or index/metadata drift on load.
6. **RAG.** Numbered `[Source n] (document, page)` blocks up to a 6,000-character budget, a strict system prompt, and a fixed abstention sentence. No LLM call is made when nothing is retrieved. The citations are parsed with a regex, and out-of-range numbers are reported as invalid instead of being shown. The LLM layer is an abstract class with an Anthropic SDK implementation and an OpenAI-compatible HTTP implementation, chosen by environment variables.
7. **Evaluation.** Page-level relevance labels, Hit@K, Precision@K, Recall@K and MRR, run on a temporary index. The demo set is 20 queries over 3 fictional PDFs I wrote, so I only use it as a smoke test.

### 5 minutes (deep walkthrough)
Everything in the 3-minute version, plus:

- **A concrete query.** For "What should I do if my work laptop is stolen?", the query is embedded (the tokenizer lowercases it and splits it into word-pieces; six transformer layers produce contextual token vectors; mean pooling and L2 normalisation give one vector). FAISS computes the dot product with all 11 stored vectors, and the top hit was page 3 of the policy at about 0.40 cosine. Scores are relative: they depend on the model and the corpus, which is why I rank rather than threshold.
- **Why cosine equals the inner product here.** Unit vectors make ‖a−b‖² = 2 − 2cos, so L2 and cosine give the same ranking. I chose inner product so the displayed score is the cosine itself.
- **Consistency engineering.** IDs are never reused, so stale metadata can't attach to a new vector. Processing removes a document's old vectors before adding new ones, so forced re-processing doesn't duplicate. Every file write is temp-then-rename. The manifest stores the model name and vector count and is checked at startup. A known gap: the document registry is saved separately from the index, so a crash can leave a "processed" document with no vectors.
- **Grounding honesty.** The sources returned are exactly the chunks in the prompt, so the UI can't show a source the model never saw. `answered_from_documents` is false if the model abstains or cites nothing real. What it can't catch is a real citation attached to a claim that source doesn't support; that would need claim-level verification such as an NLI model. I also haven't yet evaluated QA with a real LLM.
- **Classifier.** The document vector is the mean of its chunk vectors, reused from indexing. Zero-shot compares it with embedded category descriptions. There's an optional logistic regression trained on labelled texts, with stratified k-fold cross-validation. My only labelled data is 48 synthetic examples, and the trained model mislabelled my ML notes as a research paper, so the default stays zero-shot and I make no accuracy claim.
- **Evaluation results and why I don't trust them.** On the demo set: Hit@1 0.70, Hit@5 1.00, MRR 0.84. But I wrote both the documents and the queries, there are only 11 chunks, and there's no BM25 baseline. A proper evaluation would use real documents, independently written queries, a baseline, and a held-out split.
- **What I'd do next.** Hybrid BM25 + dense retrieval with a re-ranker, measured on a real evaluation set; OCR; background processing; claim-level citation checking.

---

## A. Easy

**A1. What does DocMind do?**
- Testing: can you summarise clearly.
- Key points: PDF upload; semantic search; grounded Q&A with citations; classification; local.
- Model answer: It lets you upload PDFs, search them by meaning, and ask questions that an LLM answers only from the retrieved passages, citing the document and page. It also assigns each document a category. It runs locally, with a FastAPI backend that also serves a React web interface.

**A2. What is semantic search?**
- Testing: the basic concept.
- Key points: meaning vs keywords; embeddings; similarity.
- Model answer: Finding text by meaning rather than exact words. In DocMind both the query and every chunk are turned into vectors by the same sentence-transformer, and chunks are ranked by cosine similarity. So "get my money back" can match "refund" (`app/retrieval.py`).

**A3. What is an embedding?**
- Testing: the core ML vocabulary.
- Key points: a learned vector; similar meaning → nearby vectors; 384 dimensions here.
- Model answer: A fixed-length vector a model produces for a piece of text, trained so that texts with similar meaning are close together. DocMind uses all-MiniLM-L6-v2, which outputs 384 numbers per chunk; the individual numbers aren't interpretable, only the distances are.

**A4. Why did you use PyMuPDF?**
- Testing: justifying a tool choice.
- Key points: speed; per-page API; tolerance of messy files.
- Model answer: It's a fast wrapper around the MuPDF C library, it gives text per page (I need page numbers for citations), it handles imperfect files reasonably, and `get_text(sort=True)` improves reading order. I didn't benchmark it against alternatives.

**A5. What is FAISS?**
- Testing: vector search basics.
- Key points: a similarity-search library; vectors + IDs only; exact or approximate.
- Model answer: A library from Meta for nearest-neighbour search over vectors. It stores vectors and integer IDs, not text. I use an exact inner-product index and keep the chunk text in a separate metadata dict with the same IDs.

**A6. What does top-k mean?**
- Testing: the retrieval parameter.
- Key points: k highest-scoring chunks; default 5; range 1–20.
- Model answer: The number of highest-similarity chunks returned. The default is `TOP_K=5`; the UI slider and the API accept 1–20. For Q&A, those k chunks are the candidate context, trimmed further by a 6,000-character budget.

**A7. What happens if no LLM key is configured?**
- Testing: graceful degradation.
- Key points: search and classification still work; `/ask` gives 503.
- Model answer: The LLM client is created lazily, so the app starts normally. Search and classification work; `/ask` returns 503 with a message to set `LLM_API_KEY`, and the UI disables the Ask button.

**A8. What frameworks did you use for the backend and frontend?**
- Testing: the stack.
- Key points: FastAPI + Pydantic + Uvicorn; React + TypeScript (Vite, Tailwind, Radix, Motion, React Three Fiber) talking to it over HTTP.
- Model answer: FastAPI with Pydantic models for validation, served by Uvicorn. The UI is a React + TypeScript app that only calls the API with `fetch` (TanStack Query for caching). FastAPI serves the built UI on the same origin, so there is no CORS and no token in the bundle. There is no ML code in the UI. (An earlier version used Streamlit; I replaced it to get proper interaction, such as citation popovers and real upload progress.)

## B. Intermediate

**B1. Why chunk documents instead of embedding them whole?**
- Testing: understanding of retrieval granularity.
- Key points: 256-token truncation; topic averaging; context budget; citations.
- Model answer: MiniLM truncates at 256 word-pieces, so a whole document would mostly be ignored. One vector for many topics matches everything weakly. The LLM should get a few relevant passages, not whole files. And per-page chunks give exact page citations.

**B2. How does your chunking algorithm work?**
- Testing: can you explain your own algorithm.
- Key points: sentence split; greedy packing; whole-sentence overlap; long-sentence fallback; per page.
- Model answer: `chunk_text` splits text into sentences with a regex, splits any sentence longer than the chunk size on word boundaries, then packs sentences greedily until adding the next would exceed 800 characters. The next chunk starts with the trailing whole sentences of the previous one, up to 150 characters, unless that would overflow. It runs per page and is deterministic.

**B3. What's the trade-off in chunk size and overlap?**
- Testing: engineering judgement.
- Key points: small = lost context; large = blurred vectors + more tokens; overlap = recall vs duplication.
- Model answer: Small chunks lose context ("it rose 6%": what did?). Large chunks mix topics, so similarity becomes vague, and they use more of the LLM budget. Overlap keeps facts that straddle a boundary intact, at the cost of a bigger index. 800/150 is a starting point; I haven't tuned it. The evaluation script is how I would.

**B4. Why cosine similarity?**
- Testing: the similarity metric.
- Key points: direction not magnitude; unit vectors; equivalence with L2.
- Model answer: Cosine compares direction, which is what sentence-transformers are trained on, and ignores vector length. I normalise every vector, so cosine equals the dot product, which is what FAISS `IndexFlatIP` computes. For unit vectors, ‖a−b‖² = 2 − 2cos, so L2 would give the same ranking.

**B5. How do you avoid re-embedding documents?**
- Testing: caching and idempotence.
- Key points: content hash; status check + `has_document`; force flag.
- Model answer: Document IDs are content hashes, so re-uploading the same file is detected as a duplicate. `process()` skips documents whose status is `processed` and whose vectors are in the index unless `force=True`, and a test checks the embedder isn't called. The embedding model itself is loaded once per process via `lru_cache`.

**B6. How are sources attached to answers?**
- Testing: attribution mechanics.
- Key points: numbered context; `[n]` citations; regex; `cited` flag.
- Model answer: `build_context` labels each chunk `[Source n] (document, page)`, and the prompt requires `[n]` citations. `extract_citations` parses them, and the API returns every source that was in the prompt, with `cited=true` for those referenced.

**B7. What preprocessing do you do, and why not more?**
- Testing: NLP judgement.
- Key points: artifact removal; no lowercasing, stemming or stop-word removal; transformers want natural text.
- Model answer: Unicode and ligature normalisation, rejoining hyphenated line breaks, merging wrapped lines, removing page-number lines and repeated headers or footers. I don't stem or remove stop words, because transformer embeddings use full context and the LLM needs the original wording. (The tokenizer lowercases for the embeddings anyway.) An audit found the original page-number rule deleted number-only lines (table values); I fixed it so that only explicit "Page N" labels, or a bare number at a page edge that matches the page number, are removed.

**B8. What does the Pydantic layer give you?**
- Testing: API design.
- Key points: validation; 422; response schemas; OpenAPI docs.
- Model answer: Requests like `SearchRequest` define types and constraints (query 1–2000 characters, not blank; top_k 1–20), so FastAPI rejects bad input with 422 before my code runs. `response_model` defines and documents the output, and `/docs` is generated from these models.

## C. Advanced

**C1. How do you keep the FAISS index and metadata synchronised?**
- Testing: systems thinking.
- Key points: `IndexIDMap2`; own IDs never reused; lock; atomic writes; manifest checks; the known registry gap.
- Model answer: Both are keyed by the same int64 IDs that I assign from a counter that never goes back, so deleted IDs aren't reused. Every mutation updates both under a lock. Each file is written temp-then-rename, and the manifest (written last) stores the vector count. On load I require index size = metadata count = manifest size, and the same embedding model. Otherwise it refuses to start. The gap: the document registry is separate, so a crash between registry and index saves can leave a "processed" document without vectors.

**C2. Your index is exact. When and how would you change it?**
- Testing: scaling knowledge.
- Key points: O(n·d); IVF/HNSW/PQ; recall trade-off; measure.
- Model answer: Flat search is O(n·d) per query, which is fine for tens of thousands of chunks. At millions I'd consider HNSW (a graph walk) or IVF (search only the nearest k-means clusters), possibly with PQ compression, and measure recall against the flat index as ground truth. I haven't benchmarked it, because the current scale doesn't need it.

**C3. How would you detect that a cited source doesn't actually support the claim?**
- Testing: the limits of your hallucination handling.
- Key points: current checks are number-level only; NLI / verifier ideas; not implemented.
- Model answer: Today I only verify that cited numbers exist. Supporting-evidence checking isn't implemented. I'd split the answer into sentences and run an NLI model (does the cited passage entail the sentence?), or a verifier LLM, and flag unsupported sentences, then validate that checker against human labels.

**C4. What's the failure mode of pure dense retrieval, and how would you address it?**
- Testing: retrieval depth.
- Key points: rare tokens, IDs, numbers; hybrid BM25; rank fusion; re-ranking.
- Model answer: Dense embeddings blur exact identifiers such as policy codes, names and numbers, and small models miss some paraphrases (my misses included "online" vs "reachable"). I'd add BM25, fuse the rankings (for example with reciprocal rank fusion), then re-rank the top candidates with a cross-encoder, and compare all variants on a real evaluation set. None of that is implemented.

**C5. Why is Precision@5 only 0.24 on your eval, and is that bad?**
- Testing: metric interpretation.
- Key points: one relevant page per query; 11 chunks; the maximum is bounded.
- Model answer: Most queries have exactly one relevant page, often only one or two chunks, so among 5 results at least 3–4 must be irrelevant. The achievable maximum is around 0.2–0.4, so 0.24 reflects the dataset, not a defect. Recall@K and Hit@K are more informative here. The whole set is too small and too easy to conclude much anyway.

**C6. What happens if someone changes `EMBEDDING_MODEL` after indexing?**
- Testing: robustness.
- Key points: manifest check; a loud failure; the reason.
- Model answer: `load_or_create` compares the manifest's model name and dimension with the configuration and raises `VectorStoreError` with instructions to re-index. Vectors from different models aren't comparable, so silently mixing them would give meaningless scores.

**C7. How does the Anthropic client handle model output?**
- Testing: LLM integration details.
- Key points: text blocks only; refusal; max_tokens warning; error mapping; untested live.
- Model answer: `AnthropicClient` concatenates only the `text` content blocks, ignoring non-text blocks such as thinking. It raises `LLMError` on `stop_reason == "refusal"` or an empty reply, logs a warning on `max_tokens` truncation, and maps authentication, rate-limit, API-status and connection errors to `LLMError`, which the API returns as 502. I should be clear: this client hasn't been tested with a mock or called live yet.

**C8. How would you evaluate the QA layer properly?**
- Testing: evaluation maturity.
- Key points: separate retrieval from generation; faithfulness; correctness; abstention; human or validated judges.
- Model answer: `evaluate.py --qa` already records token F1, abstention on answerable and unanswerable questions, whether a relevant page reached the context, citation precision and invalid citations, but it hasn't been run. Token F1 is crude. Properly, I'd have humans (or an LLM judge validated against humans) rate faithfulness per claim and correctness per answer, on independently written questions, and report context recall separately so retrieval failures aren't blamed on generation.

## D. Project-specific

**D1. Walk me through what happens when I upload a PDF.**
- Testing: end-to-end understanding.
- Key points: validate → hash → store → extract → clean → chunk → embed → index → classify → save.
- Model answer: `/documents/upload` sanitises the filename, checks the extension, `%PDF-` header and size, computes SHA-256 to get the document ID, reports duplicates, and saves the file as `data/raw/<id>.pdf` with status `uploaded`. `/documents/process` then removes any old vectors, extracts pages with PyMuPDF, cleans them, chunks them per page, embeds all chunks in batches, adds them to FAISS, classifies the document from its mean chunk vector, marks it `processed`, and saves the index.

**D2. Why is the document ID a hash?**
- Testing: design reasoning.
- Key points: dedup; path safety; determinism.
- Model answer: The same content always gets the same ID, so duplicates are detected even under another name. The stored filename is that hex string, so a malicious filename can never escape the data directory. It's also reproducible, which makes the sample evaluation deterministic.

**D3. Why don't chunks cross page boundaries?**
- Testing: an explicit trade-off.
- Key points: exact citations vs split context.
- Model answer: So every chunk, and therefore every citation, maps to exactly one page. The cost is that a passage continuing across a page break is split, and that's listed as a limitation.

**D4. How does the system avoid showing fake sources?**
- Testing: grounding UX.
- Key points: sources = included chunks; `invalid_citations`.
- Model answer: The sources list is built from the chunks actually placed in the prompt, not from the model's output. If the model cites `[9]` when only 5 sources exist, that number goes into `invalid_citations` and the UI warns about it. One quirk: a bracketed year like `[2024]` would also be flagged.

**D5. What happens when the documents don't contain the answer?**
- Testing: abstention.
- Key points: the fixed sentence; detection; the no-retrieval shortcut.
- Model answer: The system prompt instructs the model to reply with the exact sentence "I could not find the answer in the uploaded documents." `is_abstention` detects it and `answered_from_documents` becomes false, which shows a warning. If retrieval returns nothing at all (an empty index or filtered selection), the LLM isn't called. How reliably a real model complies is untested.

**D6. How did you test without calling real models?**
- Testing: test design.
- Key points: `HashingEncoder`; `FakeLLM`; `MockTransport`; real FAISS and PyMuPDF; a few real-model tests.
- Model answer: A deterministic bag-of-words hashing encoder stands in for the transformer, so tests are fast and texts sharing words really are similar. A `FakeLLM` records the prompts and returns canned answers. `httpx.MockTransport` fakes the OpenAI-compatible endpoint. FAISS and PyMuPDF are real, and three tests load the real MiniLM model and are skipped if it's unavailable.

**D7. What are the results of your evaluation?**
- Testing: honesty about metrics.
- Key points: numbers + caveats + what a real evaluation needs.
- Model answer: On the bundled demo set (20 queries, 3 fictional PDFs, 11 chunks) I measured Hit@1 0.70, Hit@3 0.95, Hit@5 1.00, MRR 0.84. I wrote both the documents and the queries, and the set is tiny, so it's a pipeline smoke test, not a quality claim. QA hasn't been evaluated.

**D8. What was the hardest bug or design issue?**
- Testing: reflection.
- Key points: pick a real one, such as the audit's numeric-line finding or index sync.
- Model answer: Keeping the index and metadata consistent across deletes and re-processing led me to `IndexIDMap2`, never-reused IDs, atomic writes and a manifest check. In a later audit I found bugs my 100 tests had missed: the page-number cleanup regex deleted any number-only line, so table values disappeared, and the registry could claim a document was indexed when the index save had not happened. I fixed both with regression tests that fail on the old code. It taught me that the tests only covered the inputs I thought of.

**D9. Why didn't you use LangChain?**
- Testing: the trade-off, and whether you understand what it would hide.
- Key points: learning goal; transparency; testability.
- Model answer: The pipeline is short enough to write directly, and I wanted to understand and test each step: extraction, chunking, embedding, indexing, prompting, citation checking. LangChain is fine for rapid prototyping, but here it would hide exactly those parts.

## E. ML/NLP theory

**E1. How does a transformer produce a sentence embedding?**
- Testing: model internals.
- Key points: tokenise; token + position embeddings; self-attention layers; mean pooling; normalise.
- Model answer: Text is split into word-pieces (MiniLM's tokenizer lowercases, and truncates at 256), then embedded. Six self-attention layers produce contextual token vectors. sentence-transformers averages them (mean pooling) and L2-normalises the result into one 384-dimensional vector.

**E2. What is self-attention, at a high level?**
- Testing: the core concept.
- Key points: query/key/value; softmax weights; context mixing.
- Model answer: Each token builds a query, key and value vector. The softmax of query·key scores gives weights for how much each token looks at every other token, and the output is the weighted sum of their values. That's how "bank" gets different vectors in "river bank" and "bank account". Multiple heads learn different relations.

**E3. Why can't you just use BERT's CLS token or averaged BERT outputs for search?**
- Testing: the training objective.
- Key points: MLM-trained BERT isn't trained for similarity; contrastive fine-tuning.
- Model answer: Plain BERT is trained on masked-language modelling, so its raw outputs aren't organised for cosine similarity. Sentence-transformer models like MiniLM are further trained with a contrastive objective on sentence pairs (per the model card), pulling matching pairs together and pushing others apart. That's what makes cosine similarity meaningful.

**E4. What is RAG and why use it instead of fine-tuning?**
- Testing: LLM system design.
- Key points: retrieval at query time; freshness; citations; cost.
- Model answer: RAG retrieves relevant passages and puts them in the prompt. New documents are usable immediately without retraining, answers can cite sources, and it's much cheaper. Fine-tuning is better for changing style or behaviour than for adding facts that you need to cite reliably. DocMind fine-tunes nothing.

**E5. Why do LLMs hallucinate?**
- Testing: an understanding of generation.
- Key points: next-token plausibility; no evidence tracking; retrieval gaps.
- Model answer: They generate the most plausible continuation, and nothing internal checks it against evidence. In RAG, hallucinations mostly come from retrieval misses, ambiguous or partial context, false-premise questions, or blending sources. DocMind reduces them with grounding instructions, an allowed abstention, verified citation numbers and visible sources, but it can't prove faithfulness.

**E6. What's the difference between Precision@K and Recall@K?**
- Testing: metrics.
- Key points: formulas; what each rewards.
- Model answer: Precision@K is the share of the top K results that are relevant (`sum(relevance[:k]) / k`). Recall@K is the share of all relevant pages found in the top K (`len(set(keys[:k]) & relevant) / len(relevant)`). Increasing K usually raises recall and lowers precision.

**E7. Explain logistic regression as used in your classifier.**
- Testing: classical ML.
- Key points: linear + softmax; cross-entropy; L2 regularisation via C; balanced weights.
- Model answer: A linear model on the 384-dimensional embedding. The softmax of Wx + b gives class probabilities, trained by minimising cross-entropy with L2 regularisation (`C=4.0` is the inverse strength), and `class_weight="balanced"` offsets class imbalance. It's a strong, cheap baseline on frozen embeddings.

**E8. What's zero-shot classification in your project?**
- Testing: distinguishing from NLI zero-shot.
- Key points: embedding similarity to descriptions, not NLI.
- Model answer: Not the NLI-based kind. I embed a one-sentence description per category once, and pick the category whose description has the highest cosine similarity with the document's mean chunk vector. The scores are similarities, not probabilities, and the margins can be tiny (0.2218 vs 0.2208 on my policy document).

## F. Software engineering

**F1. Why is there a service layer between the API and the pipeline?**
- Testing: architecture.
- Key points: one implementation; reuse; testability.
- Model answer: `DocMindService` is the only place the pipeline is orchestrated. The API, the CLI, `evaluate.py` and the tests all call it, so there's no duplicated logic, and I can test it without HTTP.

**F2. How is configuration handled?**
- Testing: 12-factor practices.
- Key points: env vars + .env; a validated dataclass; cached; injectable.
- Model answer: `config.py` builds a `Settings` dataclass from environment variables (with `.env` via python-dotenv), validates it at startup (for example, overlap must be smaller than chunk size), and caches it. Other modules receive `Settings` rather than reading the environment, so tests can pass a temp data directory.

**F3. How do you prevent corrupted files if the process crashes mid-save?**
- Testing: robustness.
- Key points: temp + `os.replace`; per-file atomicity; the manifest check across files.
- Model answer: `atomic_write_bytes` writes to a temp file in the same directory and `os.replace`s it over the target, which is atomic on one filesystem. Across the three index files it isn't transactional, but the manifest count check on load catches a partial save and refuses to start.

**F4. How is concurrency handled?**
- Testing: thread safety.
- Key points: a write lock; the store's RLock; the single-process limitation.
- Model answer: A `threading.Lock` serialises process and delete, and the vector store and registry use their own locks. FastAPI runs sync routes in a thread pool. This only works within one process; multiple Uvicorn workers would each have their own index copy, and I haven't tested concurrent load.

**F5. What makes your tests meaningful rather than superficial?**
- Testing: testing philosophy.
- Key points: behavioural assertions; edge cases; plus the limits.
- Model answer: They assert behaviour: chunks never exceed the size and are lossless without overlap, an identical text scores 1.0, re-processing doesn't call the embedder, hallucinated citations are flagged, validation returns 422. But 100 passing tests missed the numeric-line bug, and most tests use fake models, so they verify logic, not retrieval or answer quality.

**F6. Which important parts are untested?**
- Testing: self-awareness.
- Key points: list them honestly.
- Model answer: Since the audit I added tests for the Anthropic client (real SDK, mocked HTTP), encrypted PDFs, oversized uploads, registry/index consistency, runtime settings and the UI's safe rendering. A live provider (OpenRouter) has been spot-checked by hand, not under automated tests. Still untested: the CLI, an end-to-end browser test suite, and the Docker build.

**F7. How do you handle errors in document processing?**
- Testing: fault isolation.
- Key points: per-document try/except; status `failed` + message; index cleanup.
- Model answer: `_process_one` catches ingestion errors, a missing raw file, and unexpected exceptions separately. The document is marked `failed` with a readable message (the unexpected case is logged with a traceback), its vectors are removed, and the rest of the batch continues.

**F8. What would you refactor first?**
- Testing: judgement.
- Key points: real items from the audit.
- Model answer: The audit's top items (the number-only-line removal, registry/index reconciliation, damaged-index handling and the `[2024]` citation false positive) are already fixed. Next: hide the API key from `Settings.__repr__`, add tests for the Anthropic client, and run the QA evaluation with a real LLM.

## G. API/deployment

**G1. List your endpoints.**
- Testing: API knowledge.
- Key points: 8 routes.
- Model answer: `GET /health`, `POST /documents/upload`, `POST /documents/process`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`, `POST /search`, `POST /ask`.

**G2. Which status codes does your API return, and when?**
- Testing: HTTP semantics.
- Key points: 201/204/400/404/422/502/503/500.
- Model answer: 201 for uploads, 204 for delete, 400 when every uploaded file is rejected or there are more than 20, 404 for unknown documents, 422 for validation errors, 503 when no LLM is configured, 502 when the LLM call fails, and 500 for internal errors with a generic message.

**G3. How does the web UI talk to the backend?**
- Testing: the client/server split.
- Key points: same origin under `/api`; typed client; TanStack Query; token handling; error mapping; safe rendering.
- Model answer: Only through a typed client (`web/src/lib/api.ts`) calling `/api` on the same origin; Vite proxies it in development and FastAPI serves the built UI in production. TanStack Query caches server state. A 401 opens a token dialog, and the token is kept in browser storage, never in the build. Errors map to friendly messages, and 5xx details are never shown because they can contain server paths. Upload uses XHR for real progress. Answers are rendered from a tiny Markdown subset as React text, so injected links or images can't load.

**G4. How are uploaded files validated?**
- Testing: input security.
- Key points: extension; magic bytes; size; sanitising; hash storage; the spooling caveat.
- Model answer: The filename is sanitised; the file must end in `.pdf`, contain `%PDF-` in its first kilobyte, and be under `MAX_UPLOAD_MB`. It's stored under its hash. A caveat: Starlette receives the full upload to a temp file before my check, so the limit doesn't stop large uploads reaching the server.

**G5. How do you handle secrets?**
- Testing: security basics.
- Key points: env only; .gitignore/.dockerignore; not logged; the repr caveat.
- Model answer: API keys come only from environment variables or `.env`, which is excluded from git and the Docker build context, and they're never logged. One improvement: the `Settings` dataclass repr includes the key, so it should be hidden in case settings are ever logged.

**G6. How is the app containerised? Does it work?**
- Testing: honesty about deployment.
- Key points: what the files do; that it's unverified.
- Model answer: There's a `python:3.11-slim` Dockerfile that installs CPU-only PyTorch, bakes in the embedding model, runs as a non-root user and starts Uvicorn. It is a two-stage build: Node builds the React app, and the Python image serves it together with the API, so docker-compose runs one container with `./data` mounted. I haven't been able to build or run it yet, so I'd call it "Docker configuration, untested" rather than a working deployment.

**G7. Is this production-ready? What's missing?**
- Testing: maturity.
- Key points: auth; rate limits; job queue; scalable storage; evaluation; OCR; monitoring.
- Model answer: No. It has no authentication or rate limiting, processing runs synchronously in the request, it's a single process with a JSON registry, there's no OCR, it has no real-world evaluation, and it has no monitoring. It's a well-structured local prototype.
