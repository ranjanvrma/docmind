# DocMind: Validation Report

> **Historical document.** Written on 2026-09-26, when the interface was a Streamlit app (`frontend/streamlit_app.py`) and the API had no `/api` prefix. The Streamlit UI was later replaced by a React frontend (`web/`, see [FRONTEND.md](FRONTEND.md)); API routes moved under `/api`; Docker became a single two-stage image. Findings about the pipeline, retrieval and evaluation still apply unless noted elsewhere.

**Date:** 2026-09-26 · **Code state:** commit `9b15cf0` plus uncommitted fixes F1/F3/F4/F5 · **Tester:** automated session on the developer's machine

This report records what was **actually run** and what was **blocked**. Nothing here was estimated or simulated. Anything marked *Not verified* has not been tested in any form.

## Summary

| Area | Result |
|---|---|
| Upload, process, search, delete via the live API with the real embedding model | **Verified** |
| Streamlit UI: connection, search, passage display, disabled Q&A without an LLM | **Verified** (UI file upload not verified; see below) |
| Security sanity checks via the live API | **Verified** (8 checks) |
| Real LLM question answering | **Blocked**: no LLM credentials configured |
| QA evaluation (`evaluate.py --qa`) | **Blocked**: skipped by the script for the same reason; no QA metrics exist |
| "Answer not found" behaviour with a real LLM | **Blocked** |
| Docker build and run | **Blocked**: Docker is not installed |
| Test suite | 124 passed |

---

## Environment

| Item | Finding |
|---|---|
| OS / CPU | Windows 11, Intel64 (12 logical CPUs), CPU only |
| Python | 3.11.9 (project virtual environment `.venv`) |
| Dependencies | `pip check`: no broken requirements. Key versions: numpy 2.4.6, pandas 3.0.6, pymupdf 1.28.2, sentence-transformers 6.1.0, torch 2.14.0+cpu, faiss-cpu 1.15.1, scikit-learn 1.9.1, anthropic 1.8.0, httpx 0.28.1, fastapi 0.141.1, uvicorn 0.54.0, streamlit 1.64.0 |
| Git | Branch `main`; one commit (`9b15cf0`); the audit fixes and docs are uncommitted |
| `.env` | **Not present** |
| LLM credentials | `LLM_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_AUTH_TOKEN`: none set in the shell, Windows user or machine environment. No local Ollama server is running. (Presence checked only; no values were read or printed.) |
| Effective LLM config | Defaults: provider `anthropic`, model `claude-opus-5`, `llm_configured: false` (from `/health`) |
| Docker | `docker` is not on PATH, Docker Desktop is not installed, and WSL has no Linux distribution installed |

---

## End-to-end validation (live API, real embedding model)

**Setup.** `python main.py api --port 8010` with `DATA_DIR` pointed at a temporary directory, so the project's `data/` was never touched. The three committed sample PDFs were read, not modified (verified unchanged against git afterwards). Requests were sent over HTTP with `requests`.

| Step | Result |
|---|---|
| **Health** | 200; embedding model `all-MiniLM-L6-v2`; `llm_configured: false` |
| **Upload** (3 PDFs, one request) | 201; all three `uploaded` |
| **Duplicate upload** (same bytes, different name) | Reported as `duplicate` with "Already uploaded as 'ml_lecture_notes.pdf'" |
| **Process** one document, then the rest | 200; `processed`, 5 + 3 + 3 = 11 chunks |
| **Re-process** an already processed document | Skipped (`skipped: true`), so no re-embedding |
| **Classification** (zero-shot) | Notes, Policy, Report, which matches the three documents. This is a demo; there is no accuracy claim. |
| **Search**, 4 factual queries with known pages | The correct document and page were ranked first in 4 of 4 (laptop stolen → policy p3, 0.486; desk claim → policy p2, 0.570; inverter outage → report p2, 0.420; precision formula → notes p3, 0.313) |
| **Search** with a document filter | All results came from the selected document |
| **Search**, a question not answered by any document ("parental leave policy") | Returned policy p1 with score **0.518**, higher than two of the correct answers above. See the observation below. |
| **Ask**, factual and not-in-documents | Both **503**: "Question answering needs an LLM. Set LLM_API_KEY…". This is the documented behaviour without a key. |
| **Delete** a processed document | 204; indexed chunks 11 → 8; the stored PDF was removed; its chunks no longer appear in search |
| **Server log** | 73 lines; **no** query text, document text or key-like strings; only IDs, counts and timings |

**Observation: similarity scores can't tell an answerable question from an unanswerable one.** The unanswerable question scored higher (0.518) than the correct top hits for two answerable ones (0.420, 0.313). Retrieval will always hand the LLM *something* plausible-looking, so the "not found" behaviour depends entirely on the LLM following the system prompt. That is exactly the part that could not be tested.

### Streamlit UI (live, against the same API)
Run with `DOCMIND_API_URL=http://127.0.0.1:8010`, then inspected in a browser.

| Check | Result |
|---|---|
| Sidebar connection status | "API connected (8 chunks indexed)"; embedding model shown; "No LLM configured" warning |
| Upload widget limit | Shows 25 MB, matching `MAX_UPLOAD_MB` |
| Search tab | The query "How much can I claim for a home office desk?" gave 5 results; #1 was policy page 2 at 0.570 |
| Source/passage display | The expander shows document, page, chunk ID and passage text |
| Ask tab without an LLM | Ask button **disabled**, with an explanation message |
| Upload & process through the UI | **Not verified.** The browser automation used cannot operate the native file picker. The same endpoints were verified directly (above). |
| Answer and citation display | **Not verified** (needs an LLM) |

**Cosmetic bug found (not fixed):** `show_passage` in `frontend/streamlit_app.py` renders chunk text with `st.markdown(f"> {hit['text']}")`, so the text is interpreted as Markdown. Observed: a chunk starting "4. Equipment and Expenses …" was rendered as a numbered list item. By the same mechanism, other Markdown or LaTeX characters in documents (`*`, `#`, `$…$`) may be rendered rather than shown literally; that was not tested. Display only, with no effect on retrieval or answers.

---

## Real LLM validation

| Item | Result |
|---|---|
| Provider | None configured (defaults would be `anthropic` / `claude-opus-5`, but there's no key) |
| Tests performed | Only the no-credential path: `/ask` returns 503 with setup instructions; the UI disables Ask |
| Real answers, grounding, citations, abstention | **Not verified.** Nothing was sent to any LLM. |
| LLM latency | **Not measured** |
| `evaluate.py --qa` | Ran; retrieval metrics were produced; QA printed "Skipping QA evaluation: LLM_API_KEY is not set."; no `qa_per_question.csv` was written. **No QA metrics exist.** |

**What `--qa` would measure** once a key is set (`evaluation/evaluate.py:evaluate_qa`), over 6 answerable and 3 unanswerable sample questions:
- token-F1 against a reference answer (lexical overlap only);
- false-abstention rate on the answerable questions;
- correct-abstention rate on the unanswerable ones;
- whether a relevant page reached the prompt;
- citation precision (cited sources from relevant pages);
- number of invalid citations.

Nine questions are far too few to establish reliability.

**To run it:** create `.env` from `.env.example`, set `LLM_API_KEY` (and optionally `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL`), then run `python evaluation/evaluate.py --qa`. Be aware that `AnthropicClient` has never been executed, so that first run is also its first test.

---

## Docker validation

| Step | Result |
|---|---|
| Build | **Not run**: Docker not installed |
| Startup | **Not run** |
| Health endpoint | **Not run** |
| API request | **Not run** |
| UI reachable | **Not run** |
| Shutdown | **Not run** |

The Docker configuration remains **unverified**. No changes were made to `Dockerfile` or `docker-compose.yml`.

---

## Security checks (live API, non-destructive)

| Check | Input | Result |
|---|---|---|
| Fake PDF | `fake.pdf` containing executable-style bytes | **400**: "does not look like a PDF (missing %PDF header)" |
| Path-traversal filename | real PDF uploaded as `../../../../evil_traversal.pdf` | 201; recorded display name `evil_traversal.pdf`; stored as `<doc_id>.pdf` inside `raw/`; **no file written** outside `raw/` (checked the project root, its parent, the data dir and its parent) |
| Traversal in a path parameter | `DELETE /documents/..%2F..%2Fapp%2Fapi` | **404**; the ID is looked up in the registry, never used as a path |
| Unsupported extension | `notes.txt` | **400**: "is not a .pdf file" |
| Oversized upload | 26 MB body with a `%PDF` header | **400**: "exceeds the 25 MB upload limit" (140 ms) |
| Too many files | 21 files in one request | **400**: "At most 20 files per request" |
| Input validation | blank query; `top_k=100` | **422**; **422** |
| Missing API key | `/ask` with no key | **503** with setup instructions; no crash; key never logged |
| Log hygiene | whole server log | no query/document text or key-like strings |

**Remaining gaps, confirmed by these runs:**
- The oversized and too-many-files requests were rejected only *after* the full request body had been received by the server. The limits protect processing, not bandwidth or temporary-disk use.
- No authentication or rate limiting.
- No page-count limit.
- Prompt injection from document text is untested (it needs an LLM).
- `Settings.__repr__` still includes the API key; nothing prints it.

---

## Performance observations

**Environment-specific, not benchmarks.** One machine (Windows 11, Intel CPU, 12 logical cores, no GPU), one small document (`remote_work_policy.pdf`: 3 pages, 5 chunks, 2,716 characters), median of 5 in-process runs after warm-up.

| Stage | Median |
|---|---|
| Embedding model load (from local cache, cold process) | ~11.3 s (this run; about 5 s in an earlier session on the same machine) |
| PDF extraction (PyMuPDF) | 19.0 ms |
| Preprocessing | 0.7 ms |
| Chunking | 0.1 ms |
| Embedding 5 chunks | 78.3 ms |
| FAISS add | 0.1 ms |
| Index save (3 files) | 5.7 ms |
| Retrieval (query embedding + search, 5 chunks indexed) | 10.7 ms |

Over HTTP (single requests, live API): processing one document took 143 ms, including extraction, embedding, classification, index save and registry write. Search requests took 17–29 ms. **LLM latency was not measured.**

These numbers only show that small documents process quickly on this machine once the model is loaded. They say nothing about large PDFs, many documents, concurrency, or other hardware. They are not in the README.

---

## Bugs found during validation

| Bug | Location | Severity | Status |
|---|---|---|---|
| Chunk text is rendered as Markdown in the UI, so text that looks like Markdown (e.g. a leading "4.") changes appearance | `frontend/streamlit_app.py`, `show_passage` | Low (cosmetic) | **Reported, not fixed** |

No application code was changed during validation.

---

## Remaining limitations

1. **The core RAG claim is untested end to end.** No real LLM has answered a question through DocMind, so grounding, citation format, abstention on unanswerable questions, and the Anthropic client itself are unverified.
2. **Docker is unverified.**
3. **The UI upload flow was not exercised through the browser** (only through the API it calls).
4. **Retrieval evidence is still the demo set**: 20 author-written queries over 3 fictional PDFs, plus 4 more ad-hoc queries here. There is still no evaluation on real documents.
5. **No test with real-world PDFs** (scanned, multi-column, tables, large page counts).
6. Known open issues from the audit: hyphenated compounds merged at line breaks; partial answers containing the abstention sentence flagged as not grounded; the stale sidebar after upload; the API key in `Settings.__repr__`; the security gaps listed above.

**Before claiming the project works end to end:**
1. Configure an LLM key and run the manual QA checks, including an unanswerable question.
2. Run `evaluate.py --qa`.
3. Build and run Docker, or stop mentioning it.
4. Test a few real PDFs.
