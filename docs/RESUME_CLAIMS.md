# DocMind: Resume Claim Audit

Rule of thumb: a line on your resume is a promise you can defend for ten minutes of follow-up questions. Every item below is judged against what the code does today and what has actually been measured. (First written at commit `9b15cf0`; updated after the switch to ONNX Runtime, grounding classification, the relevance floor, background processing, the live `openrouter/free` test, and the public mode with anonymous sessions and rate limits.)

## 1. Claims you can safely make now

| Claim (suggested wording) | Why it's safe |
|---|---|
| "Built an end-to-end retrieval-augmented generation (RAG) application for PDF question answering in Python, implemented without orchestration frameworks (no LangChain)." | The whole pipeline exists in `app/` and is covered by tests. |
| "Implemented PDF ingestion with PyMuPDF (page-level extraction, content-hash deduplication, detection of empty or image-only pages)." | `ingestion.py` plus `tests/test_ingestion.py`. |
| "Designed deterministic, sentence-aware chunking with configurable size/overlap and page-level metadata for exact citations." | `chunking.py` plus `tests/test_chunking.py`. |
| "Implemented semantic search using sentence-transformer embeddings (all-MiniLM-L6-v2) and a FAISS inner-product index with persisted metadata." | `embeddings.py`, `vector_store.py`, `retrieval.py`. |
| "Ran a transformer embedding model with ONNX Runtime, reproducing the sentence-transformers pipeline (tokenisation, mean pooling, normalisation) and verifying identical vectors (cosine 1.000000)." | `embeddings.py`; checked on 13 texts and in `tests/test_embeddings.py`; retrieval metrics unchanged. |
| "Reduced memory ~2.7× (632 MB → 232 MB working set) and model load time from 15 s to 3 s by replacing PyTorch with ONNX Runtime (measured on the development machine)." | Measured on one Windows machine with the same 300-chunk workload. Always say where it was measured; Linux and container numbers were not measured. |
| "Added citation verification that flags LLM citations to non-existent sources, and server-side grounding checks: an uncited reply is retried once, then withheld and shown only as unverified output." | `qa.py`, tested. Say *verification of citation numbers*, not *fact-checking*. |
| "Moved PDF processing to a background worker with persisted queue status and automatic resume after restart." | `service.py`, `tests/test_background.py`. One thread in one process, not a distributed job queue. |
| "Added an SSRF guard for user-configurable LLM endpoints (https only, public IP addresses only)." | `runtime_settings.check_public_endpoint`, tested. Be ready to explain the DNS-rebinding gap. |
| "Built a FastAPI backend and a React + TypeScript frontend (Tailwind, Radix, Motion, React Three Fiber) with interactive source citations, real upload progress and a runtime settings panel." | `app/api.py`, `web/`; both run locally and were exercised in a browser (upload, search, citations with a scripted LLM, settings, mobile layout, reduced motion, keyboard focus). |
| "Wrote a retrieval evaluation framework computing Hit@K, Precision@K, Recall@K and MRR against labelled queries." | `evaluate.py` runs and is reproducible. Claim the *framework*, not the numbers. |
| "Added an anonymous public mode: server-issued HttpOnly session cookies, per-session document isolation, and per-IP/per-session rate limits and quotas, with admin endpoints behind a separate token." | `app/sessions.py`, `app/ratelimit.py`, `app/api.py`, `tests/test_public.py` (32 tests), plus one scripted live run with two cookie jars. Say *anonymous sessions*, not *user accounts* or *authentication*; be ready to explain why the limiter is in-process and only fits a single instance. |
| "Wrote a pytest suite (unit + API integration tests, with mocked models) and Vitest component tests." | 252 backend and 48 frontend (300 total) tests pass. Mentioning the count is fine but not impressive; describing what they test is better. |
| "Designed a provider-agnostic LLM interface (Anthropic SDK and OpenAI-compatible HTTP)." | The abstraction exists. The OpenAI-compatible path was run live against OpenRouter (one pinned model, and `openrouter/free` routing to 4 models); the Anthropic path never was. Don't say "tested with multiple providers" (see §3). |

## 2. Claims that require real-world evaluation first

| Claim | What you'd need first |
|---|---|
| "Accurate" / "high-quality retrieval" | An independently labelled evaluation on real documents, with a BM25 baseline. |
| "Reduces hallucinations" (with or without a number) | A QA evaluation with faithfulness judgements, comparing against a no-RAG or no-citation-check baseline. The `--qa` evaluation has never been run. |
| "Grounded answers with citations" as a *quality* claim | A real-LLM evaluation run showing that the model cites and abstains correctly. So far: a fake LLM in tests, plus hand spot-checks (in the `openrouter/free` test, 4 of 4 factual answers grounded and correct, 4 of 4 unanswerable questions abstained). That is 8 questions, not an evaluation. |
| "Document classifier with X% accuracy" | A real labelled test set that the classifier never trained on. |
| "Fast" / "low latency" / "handles large PDFs" | Query latency and throughput were never measured, and large or complex PDFs were never tested. (Model load time and memory were measured; see §1.) |
| "Works with OpenAI / Groq / Ollama / Claude" | Actually calling each provider end to end. Currently: Anthropic never run live; the OpenAI-compatible client run live only against OpenRouter. |
| "Runs on a 512 MB free tier" | Deploying it there and processing real documents. The ~232 MB / ~346 MB peak figures come from the Windows development machine, not a container. |
| "Dockerized" / "containerized deployment" | `docker compose up --build` succeeding and the full flow working inside containers. Not done. |

## 3. Claims that would be misleading

| Claim | Why it's misleading |
|---|---|
| "Production-ready" / "production-grade" / "scalable" / "secure multi-tenant" | Anonymous cookie sessions, not accounts; an in-process rate limiter that resets on restart and fits only one instance; `TRUSTED_PROXY_COUNT` unverified on the real host; live LLM only spot-checked and Docker never built; background processing is one thread in one process; JSON registry; no monitoring; no automated browser end-to-end tests. |
| "Deployed" | It has never been deployed anywhere. |
| "Fine-tuned a transformer" / "trained a deep learning model" | Nothing trains transformer weights. The only training is scikit-learn logistic regression on frozen embeddings, on synthetic data (optional, `requirements-train.txt`). |
| "Built with PyTorch" / "PyTorch experience" (from this project) | DocMind does not use PyTorch at all any more; the runtime is ONNX Runtime. PyTorch was only ever an indirect dependency, and it was removed. |
| "Prevents prompt injection" | Injection is mitigated, not solved. In the live test one model repeated a planted false claim, with a citation, as document content. |
| "Hybrid search", "re-ranking", "OCR", "multi-lingual", "conversation memory", "agentic" | None of these are implemented. |
| "Hallucination-free" / "eliminates hallucination" | Only citation *numbers* are verified; claims aren't checked against sources. |
| "Supports any LLM" | The client always sends `max_tokens` and `temperature`, which some newer models reject, and only OpenRouter has been tested live. |
| "Robust text preprocessing that preserves meaning" | The rules are heuristics: the number-only-line bug (F1) is fixed, but hyphenated compounds are still merged at line breaks, and there is no handling of table structure. Say "conservative" rather than "robust". |

## 4. Metrics that should NOT be on the resume

| Metric | Reason |
|---|---|
| Hit@5 = 1.00, Hit@3 = 0.95, Hit@1 = 0.70, MRR = 0.838, Recall@5 = 1.00 (800/150), or Hit@1 = 0.85, MRR = 0.917 (600/150, the current default) | From 20 queries over 3 fictional PDFs (11 chunks at 800/150), written by the same person as the queries, with no baseline. With so few chunks, even random ordering often hits within the top 5. The chunk-size sweep's differences are 2–3 queries. |
| Relevance-floor statistics (e.g. "all relevant passages scored ≥ 0.245") | Same small, author-written dataset. |
| Classifier "81% accuracy" / "0.81 macro-F1" | Cross-validation on 48 synthetic, hand-written sentences. The same model mislabelled 1 of the 3 sample documents. |
| "100 tests" framed as a quality metric | It's a count, not coverage or correctness. The original 100 missed real bugs. |
| Any query latency, throughput, cost, or "X% improvement" number | Never measured. Don't estimate one. The one exception is the measured memory/load-time comparison in §1, which must name the machine it was measured on. |

If an interviewer asks about metrics, describe the framework and explain why the demo numbers aren't evidence. That answer is stronger than quoting them.

## 5. Technologies to list only if you can explain them

| Technology | What you must be able to explain before listing it |
|---|---|
| **FAISS** | `IndexFlatIP` vs IVF/HNSW; why inner product = cosine on unit vectors; `IndexIDMap2`; how metadata is mapped; save/load and the manifest check. |
| **sentence-transformers / Transformers** | Tokenisation (uncased WordPiece, 256 limit), self-attention at a high level, mean pooling, normalisation, why contrastive training makes cosine meaningful. You used a pretrained model; say so. sentence-transformers is no longer a runtime dependency; it is only used optionally in a test to check equivalence. |
| **ONNX Runtime** | What an ONNX export is, `InferenceSession` inputs/outputs, why the pooling and normalisation had to be re-implemented, how equivalence was verified, why the CPU memory arena is disabled. You ran an existing export; you did not convert the model yourself. |
| **Hugging Face** | Only as "used pretrained models from the Hugging Face Hub" (downloaded with `huggingface_hub`, tokenised with `tokenizers`). Don't imply use of `transformers` training APIs. |
| **RAG / LLMs** | Context construction, prompt rules, abstention, citation checking and their limits, why not send the whole PDF, RAG vs fine-tuning. |
| **scikit-learn** | Logistic regression, stratified k-fold CV, why CV on synthetic data isn't a performance claim. |
| **FastAPI / Pydantic** | Dependency injection, lifespan, sync vs async routes, response models, 422 validation, status codes. |
| **React / TypeScript** | Component structure, server state with TanStack Query, why untrusted text is never rendered as HTML, why visitors need no token (HttpOnly session cookie) and why the admin token is kept only in memory and never in the bundle. |
| **Three.js / React Three Fiber** | What the hero scene represents, why it is lazy-loaded and paused off-screen, the fallback for reduced motion and no WebGL. Don't claim 3D or graphics expertise from one scene. |
| **Docker** | Only after you've built and run it. Until then, at most "wrote Dockerfile/compose config". |
| **PyTorch** | Leave it off for this project. You can mention that you *removed* it and why. |
| **NumPy / Pandas** | Where they're actually used: vector normalisation, mean pooling and dot products; metric tables (pandas is imported only while an evaluation runs). |

## Suggested resume bullet (safe today)

> **DocMind: PDF semantic search and RAG Q&A** (Python, ONNX Runtime, FAISS, FastAPI, React/TypeScript)
> - Built an end-to-end RAG pipeline without orchestration frameworks: PyMuPDF page-level extraction, sentence-aware chunking with page-level citations, MiniLM embeddings on ONNX Runtime, and FAISS vector search.
> - Replaced PyTorch with ONNX Runtime for embeddings with identical vectors, reducing memory ~2.7× and model load time ~5× (measured on the development machine).
> - Implemented grounded answer generation behind a provider-agnostic LLM interface, with citation verification, a server-side grounding check with one retry, and abstention when no passage is relevant.
> - Wrote a retrieval evaluation framework (Hit@K, Precision@K, Recall@K, MRR) and test suites (pytest, Vitest) covering ingestion, chunking, retrieval, QA logic, background processing, the API and UI components.

Before adding anything stronger, do the items in §2.
