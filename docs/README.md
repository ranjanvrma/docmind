# DocMind documentation

DocMind is a retrieval-augmented generation (RAG) application for PDFs: upload documents, search them by meaning, and ask questions that are answered only from retrieved passages, with page-level citations. This folder documents how it works, how to run it, and its limits.

## Start here

| If you want to… | Read |
|---|---|
| Run it on your machine in 10 minutes | [GETTING_STARTED.md](GETTING_STARTED.md) |
| Understand the whole system on one page | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Configure it (environment and the Settings page) | [CONFIGURATION.md](CONFIGURATION.md) |
| Call the HTTP API | [API.md](API.md) |
| Deploy it | [DEPLOYMENT.md](DEPLOYMENT.md), [DOCKER.md](DOCKER.md) |
| Fix a problem | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

## How the AI pipeline works

1. [RAG_PIPELINE.md](RAG_PIPELINE.md): the end-to-end flow and why retrieval is separate from generation
2. [EMBEDDINGS.md](EMBEDDINGS.md): turning text into vectors, run with ONNX Runtime (no PyTorch)
3. [VECTOR_SEARCH.md](VECTOR_SEARCH.md): FAISS, IDs, persistence, consistency
4. [RETRIEVAL.md](RETRIEVAL.md): top-k, filters, similarity scores, the relevance floor
5. [PROMPTING.md](PROMPTING.md): context construction, the grounding prompt, prompt-injection hardening
6. [LLM_INTEGRATION.md](LLM_INTEGRATION.md): providers, configuration, retries, errors
7. [CITATIONS.md](CITATIONS.md): how sources are numbered, cited and verified; grounding and unverified replies
8. [EVALUATION.md](EVALUATION.md): how quality is measured, and what the numbers do and do not mean

## Product and engineering

- [FRONTEND.md](FRONTEND.md): React app structure, data flow, 3D scene, accessibility
- [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md): tokens, glass, motion, typography
- [SECURITY.md](SECURITY.md): public and admin endpoints, anonymous sessions, document isolation, rate limits, CSRF, prompt injection, secrets
- [CONTRIBUTING.md](CONTRIBUTING.md): setup for development, tests, conventions

## Study and audit material

These were written while auditing the project for interview preparation. They describe the code at specific points in time; each has a note where later work changed things.

- [STUDY_ORDER.md](STUDY_ORDER.md), [INTERVIEW_PREP.md](INTERVIEW_PREP.md), [RESUME_CLAIMS.md](RESUME_CLAIMS.md)
- [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md) (audit), [VALIDATION_REPORT.md](VALIDATION_REPORT.md) (real-world validation run)
- [`../PROJECT_GUIDE.md`](../PROJECT_GUIDE.md): an in-depth explanation of every component

## Honesty notes

- Retrieval quality has only been measured on a **small demo dataset** written by the author ([EVALUATION.md](EVALUATION.md)).
- Question answering was built and tested with a **scripted stand-in LLM**, then spot-checked end to end against a **live provider** (OpenRouter: one pinned model, and `openrouter/free`, which routed 8 questions to 4 different free models). The Anthropic provider has not been run live, and the QA evaluation script has not been run. See [LLM_INTEGRATION.md](LLM_INTEGRATION.md#verification-status).
- Memory and load-time figures for the ONNX embedding runtime were measured on the Windows development machine only ([EMBEDDINGS.md](EMBEDDINGS.md#memory-and-load-time)).
- The Docker image has **not yet been built** in a real Docker environment, so its size and container startup time are unmeasured.
- There is no automated browser end-to-end test suite. The public-mode isolation and rate limits were checked in one scripted live run (production mode, two separate cookie jars), not on the real Render deployment; `TRUSTED_PROXY_COUNT=1` on Render is unverified.
- Visitor isolation rests on an anonymous session cookie, not accounts, and the rate limiter is in-process (single instance only). See [SECURITY.md](SECURITY.md#known-gaps).
