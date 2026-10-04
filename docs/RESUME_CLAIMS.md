# DocMind: Resume Claim Audit

Rule of thumb: a line on your resume is a promise you can defend for ten minutes of follow-up questions. Every item below is judged against what the code does today (commit `9b15cf0`) and what has actually been measured.

## 1. Claims you can safely make now

| Claim (suggested wording) | Why it's safe |
|---|---|
| "Built an end-to-end retrieval-augmented generation (RAG) application for PDF question answering in Python, implemented without orchestration frameworks (no LangChain)." | The whole pipeline exists in `app/` and is covered by tests. |
| "Implemented PDF ingestion with PyMuPDF (page-level extraction, content-hash deduplication, detection of empty or image-only pages)." | `ingestion.py` plus 18 tests. |
| "Designed deterministic, sentence-aware chunking with configurable size/overlap and page-level metadata for exact citations." | `chunking.py` plus 14 tests. |
| "Implemented semantic search using sentence-transformer embeddings (all-MiniLM-L6-v2) and a FAISS inner-product index with persisted metadata." | `embeddings.py`, `vector_store.py`, `retrieval.py`. |
| "Added citation verification that flags LLM citations to non-existent sources." | `qa.py`, tested. Say *verification of citation numbers*, not *fact-checking*. |
| "Built a FastAPI backend and a React + TypeScript frontend (Tailwind, Radix, Motion, React Three Fiber) with interactive source citations, real upload progress and a runtime settings panel." | `app/api.py`, `web/`; both run locally and were exercised in a browser (upload, search, citations with a scripted LLM, settings, mobile layout, reduced motion, keyboard focus). |
| "Wrote a retrieval evaluation framework computing Hit@K, Precision@K, Recall@K and MRR against labelled queries." | `evaluate.py` runs and is reproducible. Claim the *framework*, not the numbers. |
| "Wrote a pytest suite (unit + API integration tests, with mocked models)." | 160 tests pass. Mentioning the count is fine but not impressive; describing what they test is better. |
| "Designed a provider-agnostic LLM interface (Anthropic SDK and OpenAI-compatible HTTP)." | The abstraction exists. Don't add "tested with multiple providers" (see §3). |

## 2. Claims that require real-world evaluation first

| Claim | What you'd need first |
|---|---|
| "Accurate" / "high-quality retrieval" | An independently labelled evaluation on real documents, with a BM25 baseline. |
| "Reduces hallucinations" (with or without a number) | A QA evaluation with faithfulness judgements, comparing against a no-RAG or no-citation-check baseline. The `--qa` evaluation has never been run. |
| "Grounded answers with citations" as a *quality* claim | At least one real-LLM evaluation run showing that the model cites and abstains correctly. Currently only tested with a fake LLM. |
| "Document classifier with X% accuracy" | A real labelled test set that the classifier never trained on. |
| "Fast" / "low latency" / "handles large PDFs" | Latency and throughput were never measured, and large or complex PDFs were never tested. |
| "Works with OpenAI / Groq / Ollama / Claude" | Actually calling each provider end to end. Currently: Anthropic untested, OpenAI-compatible tested only against a mock. |
| "Dockerized" / "containerized deployment" | `docker compose up --build` succeeding and the full flow working inside containers. Not done. |

## 3. Claims that would be misleading

| Claim | Why it's misleading |
|---|---|
| "Production-ready" / "production-grade" / "scalable" | Only a single shared API token (no per-user accounts) and no rate limiting; live LLM only spot-checked and Docker never built; processing runs synchronously; single process; JSON registry; no monitoring. |
| "Deployed" | It has never been deployed anywhere. |
| "Fine-tuned a transformer" / "trained a deep learning model" | Nothing trains transformer weights. The only training is scikit-learn logistic regression on frozen embeddings, on synthetic data. |
| "Built with PyTorch" / "PyTorch experience" (from this project) | DocMind never imports torch; it's an indirect dependency of sentence-transformers. |
| "Hybrid search", "re-ranking", "OCR", "multi-lingual", "conversation memory", "agentic" | None of these are implemented. |
| "Hallucination-free" / "eliminates hallucination" | Only citation *numbers* are verified; claims aren't checked against sources. |
| "Supports any LLM" | The client always sends `max_tokens` and `temperature`, which some newer models reject, and no provider has been tested live. |
| "Robust text preprocessing that preserves meaning" | The rules are heuristics: the number-only-line bug (F1) is fixed, but hyphenated compounds are still merged at line breaks, and there is no handling of table structure. Say "conservative" rather than "robust". |

## 4. Metrics that should NOT be on the resume

| Metric | Reason |
|---|---|
| Hit@5 = 1.00, Hit@3 = 0.95, Hit@1 = 0.70, MRR = 0.838, Recall@5 = 1.00 | From 20 queries over 3 fictional PDFs (11 chunks), written by the same person as the queries, with no baseline. With 11 chunks, even random ordering often hits within the top 5. |
| Classifier "81% accuracy" / "0.81 macro-F1" | Cross-validation on 48 synthetic, hand-written sentences. The same model mislabelled 1 of the 3 sample documents. |
| "100 tests" framed as a quality metric | It's a count, not coverage or correctness. The original 100 missed real bugs. |
| Any latency, throughput, cost, or "X% improvement" number | Never measured. Don't estimate one. |

If an interviewer asks about metrics, describe the framework and explain why the demo numbers aren't evidence. That answer is stronger than quoting them.

## 5. Technologies to list only if you can explain them

| Technology | What you must be able to explain before listing it |
|---|---|
| **FAISS** | `IndexFlatIP` vs IVF/HNSW; why inner product = cosine on unit vectors; `IndexIDMap2`; how metadata is mapped; save/load and the manifest check. |
| **sentence-transformers / Transformers** | Tokenisation (uncased WordPiece, 256 limit), self-attention at a high level, mean pooling, normalisation, why contrastive training makes cosine meaningful. You used a pretrained model; say so. |
| **Hugging Face** | Only as "used pretrained models from the Hugging Face Hub via sentence-transformers". Don't imply use of `transformers` training APIs. |
| **RAG / LLMs** | Context construction, prompt rules, abstention, citation checking and their limits, why not send the whole PDF, RAG vs fine-tuning. |
| **scikit-learn** | Logistic regression, stratified k-fold CV, why CV on synthetic data isn't a performance claim. |
| **FastAPI / Pydantic** | Dependency injection, lifespan, sync vs async routes, response models, 422 validation, status codes. |
| **React / TypeScript** | Component structure, server state with TanStack Query, why untrusted text is never rendered as HTML, how the token is handled without being in the bundle. |
| **Three.js / React Three Fiber** | What the hero scene represents, why it is lazy-loaded and paused off-screen, the fallback for reduced motion and no WebGL. Don't claim 3D or graphics expertise from one scene. |
| **Docker** | Only after you've built and run it. Until then, at most "wrote Dockerfile/compose config". |
| **PyTorch** | Leave it off for this project. |
| **NumPy / Pandas** | Where they're actually used: vector normalisation, mean pooling and dot products; metric tables and CSV cleaning. |

## Suggested resume bullet (safe today)

> **DocMind: PDF semantic search and RAG Q&A** (Python, sentence-transformers, FAISS, FastAPI, React/TypeScript)
> - Built an end-to-end RAG pipeline without orchestration frameworks: PyMuPDF page-level extraction, sentence-aware chunking with page-level citations, MiniLM embeddings, and FAISS vector search.
> - Implemented grounded answer generation behind a provider-agnostic LLM interface, with verification that flags citations to non-existent sources.
> - Wrote a retrieval evaluation framework (Hit@K, Precision@K, Recall@K, MRR) and a pytest suite covering ingestion, chunking, retrieval, QA logic and the API.

Before adding anything stronger, do the items in §2.
