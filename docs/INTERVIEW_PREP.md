# DocMind: Interview Preparation

Every model answer below describes what the code **actually** does. Where an honest answer includes "not implemented" or "not measured", say so in the interview; a precise limitation is more convincing than a vague claim. File references point into this repository; see `docs/CODE_WALKTHROUGH.md` for the detailed trace.

Format for each question: **Testing** (what the interviewer wants to learn) · **Key points** · **Model answer**.

---

## Part 15. "Explain this project" at four lengths

### 30 seconds
DocMind is a local app where you upload PDFs and then search them by meaning or ask questions about them. It extracts text page by page with PyMuPDF, cleans it, splits it into chunks, embeds them with a sentence-transformer model run on ONNX Runtime and indexes them in FAISS. Questions are answered by an LLM using only the retrieved passages, with page-level citations that the code verifies; a reply that cites nothing is never presented as an answer. I built the RAG pipeline directly, without LangChain, so I could understand every step, and I wrote an evaluation script with retrieval metrics.

### 1 minute
The problem: keyword search fails when your wording differs from the document's, and a general chatbot hasn't seen your documents.

On upload, DocMind validates the file, hashes it for deduplication, and extracts text per page. It removes PDF artifacts like broken lines and repeated headers, then makes sentence-aware chunks of about 600 characters that never cross a page, so every citation points to one exact page. Chunks are embedded with all-MiniLM-L6-v2, run on ONNX Runtime instead of PyTorch, into 384-dimensional unit vectors and stored in a FAISS inner-product index, so the scores are cosine similarities. Processing runs on a background worker so large PDFs don't hit request timeouts.

Search embeds the query and returns the top-k chunks. For questions, passages below a low relevance floor are dropped, and the rest are numbered as sources in a prompt that tells the LLM to answer only from them, cite them, or say it couldn't find the answer. The code then checks that every cited number really was provided, and classifies the reply as grounded, not found or ungrounded; an ungrounded reply is retried once and otherwise withheld.

There's also a zero-shot document classifier, a FastAPI backend serving a React interface with interactive citations and an admin-only settings page with an evaluation lab, a public mode where anonymous visitors each see only their own documents, 300 tests (252 backend, 48 frontend), and an evaluation script for Hit@K, Precision@K, Recall@K and MRR. It currently runs on a small demo dataset, so I don't treat those numbers as real performance.

### 3 minutes (technical)
1. **Architecture.** Three layers. A React single-page app is only a client of the FastAPI API under `/api`; in production FastAPI also serves the built app, so they share one origin. The routes are thin: they validate with Pydantic and call one method on a `DocMindService` class, which orchestrates the pipeline modules. The CLI, the evaluation script and the tests all use that same service, so there's one implementation of the pipeline.
2. **Ingestion.** Uploaded bytes are checked for a `.pdf` extension, the `%PDF-` magic bytes and a size limit, then SHA-256 hashed. The first 16 hex characters are the document ID, which gives duplicate detection, and the file is stored as `<hash>.pdf`, so user filenames never become paths. PyMuPDF extracts text per page; near-empty pages are recorded, and a fully textless PDF is reported as probably scanned, since there's no OCR.
3. **Preprocessing** is deliberately light: Unicode normalisation, joining words hyphenated across lines, merging layout-wrapped lines, and removing repeated headers and footers detected as short lines on at least 60% of pages. (An audit found that the original page-number rule deleted every number-only line, such as table cells. I fixed it: now only "Page N" labels, or a bare number at the top or bottom of a page that equals the page number, are removed, and there are regression tests.)
4. **Chunking.** A greedy sentence packer up to 600 characters (the default; it was 800 until a chunk-size sweep on the demo set) with 150 characters of overlap made of whole trailing sentences, per page. It's deterministic, and the tests check the size limit, that the chunks are lossless, and the overlap.
5. **Embedding and index.** MiniLM is a 6-layer BERT with mean pooling and normalisation, 22.7M parameters, and 256-token truncation, which is why chunks are about 600 characters and capped at 1200. It runs as the model's official ONNX export on ONNX Runtime, with tokenisation, pooling and normalisation re-implemented and checked against sentence-transformers. FAISS `IndexIDMap2(IndexFlatIP)` does exact search, with custom IDs so documents can be deleted. Metadata sits in a dict keyed by the same IDs. Saving is atomic, and a manifest detects a changed embedding model or index/metadata drift on load.
6. **RAG.** Passages below a cosine floor of 0.15 and exact duplicates are dropped, then numbered `[Source n] (document, page)` blocks up to a 6,000-character budget, a strict system prompt, and a fixed abstention sentence. No LLM call is made when nothing passes the floor. The citations are parsed with a regex, and out-of-range numbers are reported as invalid instead of being shown. Every reply is classified on the server as grounded, not found or ungrounded; an ungrounded one gets exactly one retry with a reminder, and if it is still uncited the user sees a fixed "could not verify" message, with the raw reply only in a collapsed "unverified" section. The LLM layer is an abstract class with an Anthropic SDK implementation and an OpenAI-compatible HTTP implementation, chosen by environment variables.
7. **Evaluation.** Page-level relevance labels, Hit@K, Precision@K, Recall@K and MRR, run on a temporary index. The demo set is 20 queries over 3 fictional PDFs I wrote, so I only use it as a smoke test.

### 5 minutes (deep walkthrough)
Everything in the 3-minute version, plus:

- **A concrete query.** For "What should I do if my work laptop is stolen?", the query is embedded (the tokenizer lowercases it and splits it into word-pieces; six transformer layers produce contextual token vectors; mean pooling and L2 normalisation give one vector). FAISS computes the dot product with all 11 stored vectors, and the top hit was page 3 of the policy at about 0.40 cosine. Scores are relative: they depend on the model and the corpus, which is why I rank, and only use a low floor (0.15) for Q&A to drop clearly off-topic passages.
- **Why cosine equals the inner product here.** Unit vectors make ‖a−b‖² = 2 − 2cos, so L2 and cosine give the same ranking. I chose inner product so the displayed score is the cosine itself.
- **Consistency engineering.** IDs are never reused, so stale metadata can't attach to a new vector. Processing removes a document's old vectors before adding new ones, so forced re-processing doesn't duplicate. Every file write is temp-then-rename. The manifest stores the model name and vector count and is checked at startup. An audit found that the document registry could say "processed" for a document whose vectors were never saved; now the index is saved before the registry commits, and startup reconciles the two.
- **Grounding honesty.** The sources returned are exactly the chunks in the prompt, so the UI can't show a source the model never saw. The server classifies each reply: `grounding` is `grounded` only if it cites at least one real source, and `answered_from_documents` is exactly that. An ungrounded reply is retried once and then withheld. What it can't catch is a real citation attached to a claim that source doesn't support; that would need claim-level verification such as an NLI model. I've spot-checked real LLMs by hand (OpenRouter), but I haven't run the QA evaluation script.
- **Classifier.** The document vector is the mean of its chunk vectors, reused from indexing. Zero-shot compares it with embedded category descriptions. There's an optional logistic regression trained on labelled texts, with stratified k-fold cross-validation. My only labelled data is 48 synthetic examples, and the trained model mislabelled my ML notes as a research paper, so the default stays zero-shot and I make no accuracy claim.
- **Evaluation results and why I don't trust them.** On the demo set: Hit@1 0.85, Hit@5 1.00, MRR 0.917 at the current 600/150 default (0.70 and 0.838 at the previous 800/150). But I wrote both the documents and the queries, there are only 20 queries and a handful of chunks, and there's no BM25 baseline; the difference between those settings is 3 queries. A proper evaluation would use real documents, independently written queries, a baseline, and a held-out split.
- **Deployment footprint.** I replaced PyTorch with ONNX Runtime for the embedding model. On my machine that took the model load from 15.3 s to 3.0 s and the working set after embedding 300 chunks from 632 MB to 232 MB, with identical vectors, so the app fits a 512 MB instance.
- **What I'd do next.** Hybrid BM25 + dense retrieval with a re-ranker, measured on a real evaluation set; OCR; claim-level citation checking; actually building and deploying the Docker image.

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
- Model answer: The number of highest-similarity chunks returned. The default is `TOP_K=5`; the UI slider and the API accept 1–20. For Q&A, those k chunks are the candidate context, filtered by the relevance floor and de-duplicated, then trimmed further by a 6,000-character budget.

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
- Model answer: `chunk_text` splits text into sentences with a regex, splits any sentence longer than the chunk size on word boundaries, then packs sentences greedily until adding the next would exceed the chunk size (600 characters by default). The next chunk starts with the trailing whole sentences of the previous one, up to 150 characters, unless that would overflow. It runs per page and is deterministic.

**B3. What's the trade-off in chunk size and overlap?**
- Testing: engineering judgement.
- Key points: small = lost context; large = blurred vectors + more tokens; overlap = recall vs duplication.
- Model answer: Small chunks lose context ("it rose 6%": what did?). Large chunks mix topics, so similarity becomes vague, and they use more of the LLM budget. Overlap keeps facts that straddle a boundary intact, at the cost of a bigger index. I started at 800/150, then swept sizes from 400 to 1000 with the evaluation script. Smaller chunks did better with MiniLM, which was trained on short texts, and 600/150 had the best MRR (0.917 vs 0.838), so it became the default. But that's 20 queries I wrote myself, where one query is 0.05 Hit@1, so it's a weak signal. I also capped chunk size at 1200, because the model only reads about 256 tokens.

**B4. Why cosine similarity?**
- Testing: the similarity metric.
- Key points: direction not magnitude; unit vectors; equivalence with L2.
- Model answer: Cosine compares direction, which is what sentence-transformers are trained on, and ignores vector length. I normalise every vector, so cosine equals the dot product, which is what FAISS `IndexFlatIP` computes. For unit vectors, ‖a−b‖² = 2 − 2cos, so L2 would give the same ranking.

**B5. How do you avoid re-embedding documents?**
- Testing: caching and idempotence.
- Key points: content hash (per owner); status check + `has_document`; force flag.
- Model answer: Document IDs are hashes of the uploader's owner key plus the content, so re-uploading the same file in the same session is detected as a duplicate (two visitors uploading the same file get separate documents). `process()` skips documents whose status is `processed` and whose vectors are in the index unless `force=True`, and a test checks the embedder isn't called. The embedding model itself is loaded once per process via `lru_cache`.

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
- Key points: `IndexIDMap2`; own IDs never reused; lock; atomic writes; manifest checks; registry committed after the index; startup reconciliation.
- Model answer: Both are keyed by the same int64 IDs that I assign from a counter that never goes back, so deleted IDs aren't reused. Every mutation updates both under a lock. Each file is written temp-then-rename, and the manifest (written last) stores the vector count. On load I require index size = metadata count = manifest size, and the same embedding model. Otherwise the API reports 503 with recovery instructions. The document registry is a separate file; an audit showed a crash could leave a "processed" document without vectors, so now the index is saved before the registry commits, and startup puts any document missing from the index back to `uploaded`.

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
- Key points: text blocks only; refusal; max_tokens notice; error mapping; SDK retries; tested with a mocked transport, never live.
- Model answer: `AnthropicClient` concatenates only the `text` content blocks, ignoring non-text blocks such as thinking. It raises `LLMError` on `stop_reason == "refusal"` or an empty reply, appends a truncation notice and logs a warning on `max_tokens`, and maps authentication, rate-limit, API-status and connection errors to `LLMError`, which the API returns as 502. Retries are left to the SDK's built-in retries. It's tested with the real SDK against a mocked HTTP transport, but I should be clear: it has never been called against the live Anthropic API.

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
- Model answer: The sources list is built from the chunks actually placed in the prompt, not from the model's output. If the model cites `[9]` when only 5 sources exist, that number goes into `invalid_citations` and the UI warns about it; if those are its only citations, the reply counts as ungrounded. Citation markers are limited to one or two digits, so a bracketed year like `[2024]` is ordinary text (an audit found it used to be flagged).

**D5. What happens when the documents don't contain the answer?**
- Testing: abstention.
- Key points: the fixed sentence; detection; the relevance-floor shortcut; spot-check results.
- Model answer: The system prompt instructs the model to begin with the exact sentence "I could not find the answer in the uploaded documents." `is_abstention` detects it, `grounding` becomes `not_found`, and the UI shows "Not found in your documents". If retrieval returns nothing, or nothing passes the 0.15 relevance floor, the LLM isn't called. In a live spot-check through `openrouter/free`, all 4 unanswerable questions abstained, 2 of them without an LLM call. That's 4 questions, not a measured abstention rate.

**D6. How did you test without calling real models?**
- Testing: test design.
- Key points: `HashingEncoder`; `FakeLLM`; `MockTransport`; real FAISS and PyMuPDF; a few real-model tests.
- Model answer: A deterministic bag-of-words hashing encoder stands in for the transformer, so tests are fast and texts sharing words really are similar. A `FakeLLM` records the prompts and returns canned answers. `httpx.MockTransport` fakes the OpenAI-compatible endpoint. FAISS and PyMuPDF are real, and a few tests load the real MiniLM model through ONNX Runtime and are skipped if it's unavailable; one of them compares its vectors with sentence-transformers when that package is installed.

**D7. What are the results of your evaluation?**
- Testing: honesty about metrics.
- Key points: numbers + caveats + what a real evaluation needs.
- Model answer: On the bundled demo set (20 queries, 3 fictional PDFs) I measured Hit@1 0.70, Hit@3 0.95, Hit@5 1.00, MRR 0.84 at the original 800/150 chunking, and Hit@1 0.85, Hit@3 1.00, MRR 0.92 at 600/150, which is now the default. I wrote both the documents and the queries, and the set is tiny, so it's a pipeline smoke test, not a quality claim. QA hasn't been evaluated beyond hand spot-checks.

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
- Model answer: Text is split into word-pieces (MiniLM's tokenizer lowercases, and truncates at 256), then embedded. Six self-attention layers produce contextual token vectors. These are averaged over the real (non-padding) tokens (mean pooling) and L2-normalised into one 384-dimensional vector. In DocMind the transformer runs on ONNX Runtime, and my code does the pooling and normalisation the same way sentence-transformers does.

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
- Key points: a write lock; the store's RLock; the background worker and its queue lock; lock ordering; the single-process limitation.
- Model answer: A `threading.Lock` serialises process and delete, and the vector store and registry use their own locks. FastAPI runs sync routes in a thread pool. Background processing adds one worker thread that takes the same write lock, plus a queue lock; everywhere the order is write lock, then queue lock, to avoid deadlock. ONNX Runtime calls are serialised so only one batch is in memory at a time. This only works within one process; multiple Uvicorn workers would each have their own index copy, and I haven't tested concurrent load.

**F5. What makes your tests meaningful rather than superficial?**
- Testing: testing philosophy.
- Key points: behavioural assertions; edge cases; plus the limits.
- Model answer: They assert behaviour: chunks never exceed the size and are lossless without overlap, an identical text scores 1.0, re-processing doesn't call the embedder, hallucinated citations are flagged, validation returns 422. But 100 passing tests missed the numeric-line bug, and most tests use fake models, so they verify logic, not retrieval or answer quality.

**F6. Which important parts are untested?**
- Testing: self-awareness.
- Key points: list them honestly.
- Model answer: Since the audit I added tests for the Anthropic client (real SDK, mocked HTTP), encrypted PDFs, oversized uploads, registry/index consistency, runtime settings and the UI's safe rendering. Later I added tests for grounding and the retry, the relevance floor, background processing and restart recovery, the SSRF guard, ONNX/sentence-transformers equivalence, and the public mode (`tests/test_public.py`: session isolation between two clients, rate limits and quotas, the Origin check, admin-token handling). A live provider (OpenRouter, including `openrouter/free`) has been spot-checked by hand, not under automated tests. The public mode was also checked in one scripted live run with two cookie jars, but not on the real Render deployment. Still untested: the Anthropic provider live, the QA evaluation script, the CLI, an automated browser end-to-end suite, and the Docker build.

**F7. How do you handle errors in document processing?**
- Testing: fault isolation.
- Key points: per-document try/except; status `failed` + message; index cleanup.
- Model answer: `_process_one` catches ingestion errors, a missing raw file, and unexpected exceptions separately. The document is marked `failed` with a readable message (the unexpected case is logged with a traceback), its vectors are removed, and the rest of the batch continues.

**F8. What would you refactor first?**
- Testing: judgement.
- Key points: real items from the audit.
- Model answer: The audit's top items (the number-only-line removal, registry/index reconciliation, damaged-index handling and the `[2024]` citation false positive) are already fixed, the API key is hidden from `Settings.__repr__`, and the Anthropic client has mocked-transport tests. Next: run the QA evaluation with a real LLM, build and run the Docker image, and add claim-level citation checking.

## G. API/deployment

**G1. List your endpoints.**
- Testing: API knowledge.
- Key points: 16 routes under `/api`: 9 public, 7 admin.
- Model answer: All under `/api`. Public, no token, scoped to the visitor's session: `GET /health`; `POST /documents/upload`, `POST /documents/process` (optionally in the background), `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/chunks`, `DELETE /documents/{id}`; `POST /search`, `POST /ask`. Admin, behind `DOCMIND_API_TOKEN`: `GET` and `PATCH /admin/settings`, `DELETE /admin/settings/llm-api-key`, `POST /admin/settings/reset`, `POST /admin/settings/test-llm`, `POST /admin/evaluation/retrieval`, `GET /admin/diagnostics`.

**G2. Which status codes does your API return, and when?**
- Testing: HTTP semantics.
- Key points: 201/202/204/400/401/403/404/409/411/413/422/429/502/503/500.
- Model answer: 201 for uploads, 202 for background processing, 204 for delete, 400 when every uploaded file is rejected or there are more than 20, 401 for a missing or wrong admin token, 403 for a cross-site browser request, 404 for unknown documents and for other visitors' documents, 409 when a session's document quota is full, 429 with `Retry-After` for rate limits, 411/413 for a missing or too-large Content-Length on upload, 422 for validation errors, 503 when no LLM is configured, stored data couldn't be loaded, or the server is at its session capacity, 502 when the LLM call fails (without the provider's error body), and 500 for internal errors with a generic message.

**G3. How does the web UI talk to the backend?**
- Testing: the client/server split.
- Key points: same origin under `/api`; typed client; TanStack Query; cookie session, no visitor token; admin token in memory; error mapping; safe rendering.
- Model answer: Only through a typed client (`web/src/lib/api.ts`) calling `/api` on the same origin; Vite proxies it in development and FastAPI serves the built UI in production. TanStack Query caches server state. Visitors send no token: requests use `credentials: "same-origin"`, and the server's HttpOnly session cookie goes along automatically, so JavaScript never sees it. The administrator signs in on the Settings page; that token is kept in memory for the page only, sent only to `/api/admin/*`, and never stored in the build or browser storage. A 429 shows how long to wait, from `Retry-After`. Errors map to friendly messages, and 5xx details are never shown because they can contain server paths. Upload uses XHR for real progress; processing then runs in the background and the UI polls the document list every 1.5 s only while something is queued or processing. Answers are rendered from a tiny Markdown subset as React text, so injected links or images can't load.

**G4. How are uploaded files validated?**
- Testing: input security.
- Key points: extension; magic bytes; size; sanitising; hash storage; the spooling caveat.
- Model answer: The filename is sanitised; the file must end in `.pdf`, contain `%PDF-` in its first kilobyte, and be under `MAX_UPLOAD_MB`. It's stored under its document ID (a hash of owner and content). A caveat: Starlette receives the full upload to a temp file before my check, so the limit doesn't stop large uploads reaching the server.

**G5. How do you handle secrets?**
- Testing: security basics.
- Key points: env or write-only setting; .gitignore/.dockerignore; not logged; hidden from repr; key bound to its endpoint; SSRF guard.
- Model answer: API keys come from environment variables or `.env`, which are excluded from git and the Docker build context, or from the Settings page, where the key is write-only and stored in the data directory. They're never logged and are hidden from `Settings.__repr__`. If someone changes the provider or base URL from the UI, the environment key is withheld until a new key is entered, so an admin-token holder can't redirect it to their own host. Visitors can't reach the settings at all. In production a UI-set base URL must also be `https` and resolve to public IPs only.

**G6. How is the app containerised? Does it work?**
- Testing: honesty about deployment.
- Key points: what the files do; that it's unverified.
- Model answer: There's a `python:3.11-slim` Dockerfile with no PyTorch: it installs the runtime requirements, bakes in only the four ONNX model and tokenizer files (about 90 MB), sets `HF_HUB_OFFLINE=1`, runs as a non-root user in production mode and starts one Uvicorn process. It is a two-stage build: Node builds the React app, and the Python image serves it together with the API, so docker-compose runs one container with `./data` mounted. I haven't been able to build or run it yet, so I don't know its size and I'd call it "Docker configuration, untested" rather than a working deployment.

**G7. Is this production-ready? What's missing?**
- Testing: maturity.
- Key points: no accounts; in-process rate limits; job queue; scalable storage; evaluation; OCR; monitoring; unverified Docker build.
- Model answer: No. Visitors are anonymous cookie sessions rather than user accounts, and the rate limiter lives in process memory, so it resets on restart and only works for a single instance. Background processing is one thread in one process, not a durable job queue; it's a single process with a JSON registry; there's no OCR, no real-world evaluation, no monitoring, and the Docker image has never been built. It's a well-structured prototype that can be demoed on one small instance.

## H. Later changes

**H1. Why do you run the embedding model with ONNX Runtime instead of PyTorch, and how do you know the vectors are the same?**
- Testing: deployment trade-offs; whether you verified a risky change.
- Key points: PyTorch was only needed for inference; memory and load time on small instances; the official ONNX export; re-implemented tokenisation, pooling and normalisation; measured equivalence; unchanged retrieval metrics; what wasn't measured.
- Model answer: DocMind only does inference, and PyTorch plus sentence-transformers was most of the memory and image size. On my Windows machine, with the same 300-chunk workload, the PyTorch path took 15.3 s to load and had a 632 MB working set after embedding (705 MB peak); the ONNX path loads in 3.0 s (0.4 s from a warm cache) and uses 232 MB (346 MB peak). That's what makes a 512 MB instance realistic. `app/embeddings.py` downloads the model's official `onnx/model.onnx` plus its tokenizer and pooling config with `huggingface_hub`, tokenises with the `tokenizers` library truncated to the model's `max_seq_length` (256), runs the graph with an ONNX Runtime CPU session, applies mean or CLS pooling as the pooling config says, and L2-normalises. To verify it, I compared it with `SentenceTransformer.encode` on 13 texts, including the sample PDFs, a long text that gets truncated and non-Latin text: cosine 1.000000, maximum absolute difference 1.3e-7. A test repeats that check when sentence-transformers is installed, and the retrieval metrics on the demo set were identical. Two smaller details: texts are sorted by length into batches to cut padding, and ONNX Runtime's CPU memory arena is disabled so memory is released after big batches. I haven't measured it on Linux or in a container.

**H2. What happens when the LLM's reply doesn't cite any source?**
- Testing: handling unreliable model output.
- Key points: server-side classification; one retry with a reminder; a fixed message instead of the reply; raw reply only as unverified; abstentions not retried; what it doesn't check.
- Model answer: `qa.assess_answer` classifies every reply: `grounded` if it cites at least one source that was actually provided, `not_found` if it starts with the exact abstention sentence, otherwise `ungrounded`. Citing only non-existent source numbers counts as ungrounded. An ungrounded reply triggers exactly one retry, with a reminder of the citation rules appended to the user prompt. If that is still ungrounded, the API returns a fixed message ("I could not produce an answer that is supported by citations…") as the answer, and the model's text separately in `unverified_answer`; the UI only shows it in a collapsed "Show unverified reply" section, as plain text, with a "Could not be verified" badge. Abstentions aren't retried. I added this because `openrouter/free` once routed to a content-safety classifier that replied "User Safety: safe"; that reply would now never be shown as an answer. The limit: "grounded" means "cites a real source", not "the source supports the claim".

**H3. What is the relevance floor, and why can't it replace the model's abstention?**
- Testing: thresholds on similarity scores; using data to choose one.
- Key points: 0.15 cosine; Q&A only; drops noise and duplicates; skips the LLM when nothing is left; the evidence; on-topic unanswerable questions score high.
- Model answer: Before building the prompt, passages with cosine below `MIN_RELEVANCE` (0.15 by default) and exact duplicate texts are dropped; if nothing remains, DocMind abstains without calling the LLM. Search results aren't filtered. I picked 0.15 from the demo set: all 24 labelled-relevant passages in the top 5 scored at least 0.245, while 31 of 76 irrelevant top-5 passages were below 0.15, and clearly off-topic questions had top scores of 0.08–0.18. But unanswerable questions on the documents' topic scored 0.45–0.77, as high as real answers, so similarity can't tell "related" from "answers the question". The floor saves LLM calls on obvious misses; the real abstention still has to come from the model. And all of this comes from a small dataset I wrote myself.

**H4. How does background processing work, and what happens if the server restarts mid-way?**
- Testing: concurrency, durability, and why it was needed.
- Key points: 202 + polling; one daemon worker; same write lock; persisted statuses; resume on restart; shutdown; safe delete; why.
- Model answer: With `"background": true`, `POST /api/documents/process` marks the documents `queued` and returns 202. A single daemon worker thread in the API process takes them one at a time, sets `processing`, and runs the same `process` code under the same write lock as synchronous processing, ending in `processed` or `failed`. The web UI always uses this and polls `GET /api/documents` every 1.5 s, but only while something is pending; the CLI, tests and scripts keep the synchronous default. The statuses are stored in the registry, so on startup any document still `queued` or `processing` is re-queued. On shutdown the worker stops after its current document, within uvicorn's 30 s graceful timeout. Deleting a queued document is safe: the worker checks the record under the queue lock, and every path takes the write lock before the queue lock, so a deleted document can't come back. The reason was hosting: a large PDF on a slow free-tier CPU can take minutes, and proxies cut long requests. It's still one thread in one process, not a durable distributed queue.

**H5. Users can change the LLM base URL from the Settings page. Isn't that an SSRF risk?**
- Testing: security thinking about user-controlled URLs.
- Key points: who can do it; https only; resolve and require public IPs; metadata endpoints; check-time only (DNS rebinding); operator env trusted; development exception; key withholding.
- Model answer: It was, so in production `runtime_settings.check_public_endpoint` validates any base URL saved through the API: it must be `https`, and its host must resolve only to public (`is_global`) addresses. That blocks loopback, private ranges and link-local addresses such as the `169.254.169.254` cloud metadata endpoint, which someone with the admin token could otherwise make the server call. Visitors can't reach this setting at all. The check happens when the setting is saved, so DNS rebinding afterwards isn't covered. The operator's own `LLM_BASE_URL` from the environment is trusted, and development mode allows local endpoints like Ollama. Separately, changing the endpoint from the UI withholds the environment's API key until a new key is entered, so the key can't be sent to an attacker's server.

**H6. DocMind is public without sign-in. How do you keep one visitor's documents away from another's?**
- Testing: session design; identity without accounts.
- Key points: server-generated 256-bit ID; HttpOnly, SameSite=Strict, Path=/api cookie; created lazily on first upload; only a hash stored; owner key on every document; unknown cookie = no session; the admin token is separate.
- Model answer: On a visitor's first upload the server creates a session: `secrets.token_urlsafe(32)`, sent in an HttpOnly, SameSite=Strict cookie scoped to `/api`, `Secure` in production. Reads and searches never create one. The server stores only a truncated SHA-256 of the ID, the owner key, in `sessions.json`, so a leaked data directory doesn't give anyone a usable cookie. Every document records the owner key of the session that uploaded it. Clients can't pick an identity: an unknown, malformed or expired cookie is just "no session", and a new random ID is issued on the next upload. The old shared `DOCMIND_API_TOKEN` now only protects the admin endpoints; it has nothing to do with visitors. The honest limit: this is possession-based, not authentication. Whoever has the cookie has that session's documents, and clearing cookies loses them.

**H7. How do you make sure a query can't leak another visitor's data?**
- Testing: authorisation at the data layer; failure modes.
- Key points: owner passed on every public route; sentinel owner `-` instead of "no filter"; 404 not 403; FAISS results filtered to the visitor's doc IDs; no LLM call without documents; owner-scoped document IDs; tests with two clients.
- Model answer: Every public route passes the session's owner key into the service, and the service filters by it. A request without a session gets the sentinel owner `-`, which matches nothing, so there's no code path where a missing session turns into an unscoped query. Another visitor's document ID behaves exactly like a missing one (404) for get, chunks, delete, process, and search or ask with `doc_ids`, so IDs can't be probed. Unfiltered search and ask only search the visitor's processed documents; FAISS has one shared index, so the results are filtered to that visitor's document IDs, and a visitor with no documents gets no search and no LLM call. Document IDs include the owner key, so two visitors uploading the same PDF get two separate documents rather than one shared record. Owner-less documents from the CLI are never visible to visitors. `tests/test_public.py` checks this with two separate clients, and a live run with two cookie jars confirmed it. The weak point is the shared index: isolation depends on that filter being applied everywhere, which is why the routes never call the store directly.

**H8. How is abuse limited, and why did you choose an in-process limiter?**
- Testing: rate-limiting design and its limits.
- Key points: sliding window; per IP and per session; separate budgets for requests, questions, uploads, new sessions; global question cap for the LLM quota; quotas for documents, jobs, sessions; 429 + Retry-After; in-process trade-off; TRUSTED_PROXY_COUNT.
- Model answer: `app/ratelimit.py` is a sliding-window counter keyed by IP and by session, so dropping the cookie or sharing it doesn't escape the limits. There are separate budgets: 120 API requests a minute, 20 questions and 20 uploaded files an hour, 20 new sessions per IP an hour (to stop cookie-dropping), plus a server-wide cap of 200 questions an hour that protects the shared OpenRouter quota and is only spent when the visitor actually has documents to search. Quotas cap documents (20, then 409) and queued jobs (5, then 429) per session and active sessions overall (1000, then 503). Rejections are 429 with `Retry-After`, which the UI turns into "try again in N minutes". I kept it in process memory because DocMind runs as exactly one process on one instance; Redis would be another service to run on a free tier. The costs: counters reset on restart, several instances would each count separately, and everyone behind one NAT shares the IP limits. Behind a proxy the client IP comes from `X-Forwarded-For`, counting `TRUSTED_PROXY_COUNT` entries from the right, because entries further left are client-supplied. On Render I expect 1, but I haven't verified it there yet; `/api/admin/diagnostics` shows the IP the limiter sees so it can be checked.

**H9. With cookie-based sessions, what about CSRF, and what are the remaining gaps?**
- Testing: browser security model; honesty.
- Key points: SameSite=Strict; Origin check on unsafe methods; Sec-Fetch-Site; non-browser clients unaffected; no cross-origin UI; known gaps.
- Model answer: Two layers. The cookie is SameSite=Strict, so browsers don't send it on cross-site requests, and every POST, PUT, PATCH or DELETE checks `Origin`: it must match the `Host` or be an explicitly allowed CORS origin, otherwise 403. A request marked `Sec-Fetch-Site: cross-site` without an `Origin` is also rejected. Non-browser clients send no `Origin` and aren't affected, which is fine because they can't ride on a victim's cookie. The remaining gaps: no accounts, so a stolen cookie means access to that session's documents; the limiter is single-instance and resets on restart; shared NATs share limits; the SSRF guard still doesn't cover DNS rebinding; and on Render's free tier the disk is ephemeral, so every restart wipes all documents and sessions. I describe it as a reasonable model for a public demo, not as enterprise security.
