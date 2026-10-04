# Architecture

DocMind has three layers: a React single-page app, a FastAPI backend, and a pipeline of small Python modules orchestrated by one service class. One process serves both the API (under `/api`) and the built UI. Visitors use the public endpoints anonymously; each is an HttpOnly-cookie session that sees only its own documents. Settings, evaluation and diagnostics live under `/api/admin/*` behind `DOCMIND_API_TOKEN`.

```
Browser ──▶ React SPA (web/)                       design system, 3D hero, citations UI
              │  fetch /api/*  (session cookie; X-API-Key only for /api/admin/*)
              ▼
           FastAPI (app/api.py)                    sessions, rate limits, Origin check, admin auth,
              │                                    size limits, validation, security headers,
              │                                    serves web/dist with a strict CSP
              ▼
           DocMindService (app/service.py)         the only orchestrator of the pipeline
              │
   ┌──────────┼───────────────────────────────┬───────────────────────────┐
   ▼          ▼                               ▼                           ▼
 ingestion → preprocessing → chunking → embeddings → FAISS vector store   runtime settings
 (PyMuPDF)   (clean text)    (page-     (MiniLM,     (index + metadata    (data/settings.json)
                             bounded)   ONNX         + manifest)
                                        Runtime,
                                        384-d unit)
                                             │
                          classifier ◀── mean chunk vector

 question → embed → FAISS top-k → relevance floor + de-dup → numbered, sanitised context → LLM
          → answer → citation check + grounding (one retry if ungrounded)
```

## Request lifecycles

**Upload** `POST /api/documents/upload`
1. `UploadSizeLimitMiddleware` rejects requests whose `Content-Length` exceeds `MAX_REQUEST_MB` (413) before the body is read.
2. Each file: filename sanitised, `.pdf` extension, `%PDF-` magic bytes, per-file size limit (`ingestion.validate_pdf_upload`).
3. Upload rate limits are checked and, on a visitor's first upload, a session is created (cookie set). SHA-256 of the owner key plus the bytes gives the document ID (so two visitors uploading the same PDF get separate documents); a known ID within the same session is reported as a duplicate. The per-session document quota gives `409`.
4. The file is stored as `data/raw/<doc_id>.pdf` (never under the user's name), and a registry record is created with status `uploaded`.

**Process** `POST /api/documents/process`
1. For each target document (`service._process_one`): remove old vectors, extract pages (`MAX_PAGES` enforced), remove page-number artifacts and repeated headers, chunk per page, embed in batches, add to FAISS, classify from the mean chunk vector.
2. `service._save_index_then_commit`: save the index, and only then mark documents `processed`. If saving fails, roll back the vectors and mark the documents `failed`.
3. **Synchronous or background.** By default this runs inside the request (CLI, tests, scripts). With `"background": true` (always used by the web UI) the API returns `202` immediately, documents become `queued`, and a single daemon worker thread in the API process processes them one at a time (`queued → processing → processed | failed`), under the same write lock as synchronous processing. The UI polls `GET /api/documents` every 1.5 s while anything is pending. This avoids proxy and request timeouts for large PDFs on slow CPUs. On shutdown the worker stops after the current document.

**Search** `POST /api/search`: embed the query with the same model, run exact inner-product search restricted to the visitor's own processed documents, map IDs back to chunk metadata (document, page, text). A visitor with no processed documents gets an empty result without a search; `doc_ids` naming another visitor's document gives `404`.

**Ask** `POST /api/ask`: check the per-visitor and server-wide question limits, retrieve as in search (no LLM call if the visitor has no processed documents), drop passages below `MIN_RELEVANCE` and exact duplicates; if nothing remains, return the "not found" sentence without calling the LLM. Otherwise build `[Source n] (document, page)` blocks within `MAX_CONTEXT_CHARS`, call the LLM with a grounding prompt, parse `[n]` citations, mark invalid numbers, and classify the reply as `grounded`, `not_found` or `ungrounded`. An ungrounded reply is retried once; if still ungrounded it is returned only as `unverified_answer` ([CITATIONS.md](CITATIONS.md)).

## Persistent state

| Path (under `DATA_DIR`) | Owner | Contents |
|---|---|---|
| `raw/<doc_id>.pdf` | `service.upload` | uploaded files, named by document ID (owner + content hash) |
| `processed/documents.json` | `registry.py` | one record per document: owner key, status, pages, chunks, classification, errors |
| `sessions.json` | `sessions.py` | hashed session IDs (owner keys) with created/last-seen times; never the cookie values |
| `index/index.faiss`, `metadata.json`, `manifest.json` | `vector_store.py` | vectors, chunk metadata, consistency manifest |
| `settings.json` | `runtime_settings.py` | values saved from the Settings page (override `.env`) |
| `classifier/classifier.joblib` | `main.py train-classifier` | optional supervised classifier (needs `requirements-train.txt`; ignored with a warning if scikit-learn/joblib are not installed) |

At startup the service loads the settings overrides, loads the embedding model and the index (refusing a mismatched or damaged one with a clear error), reconciles the registry with the index so documents missing from the index return to `uploaded`, re-queues documents left `queued` or `processing` by an interrupted run, and removes stored PDFs without a registry entry. A maintenance thread then runs every 60 s: it deletes expired sessions with all their documents, and documents whose session no longer exists.

## Module map

| Module | Responsibility |
|---|---|
| `app/config.py` | environment settings, validation |
| `app/runtime_settings.py` | editable settings, persistence, public (secret-free) view |
| `app/ingestion.py` | upload validation, PyMuPDF extraction, page limit |
| `app/preprocessing.py` | text cleaning, header/footer and page-number removal |
| `app/chunking.py` | sentence-aware, page-bounded chunks with overlap |
| `app/embeddings.py` | sentence-transformers model run with ONNX Runtime (no PyTorch), normalisation |
| `app/vector_store.py` | FAISS index, metadata, persistence and integrity |
| `app/retrieval.py` | query → top-k results |
| `app/prompts.py` | system prompt, context construction, source sanitising |
| `app/llm.py` | provider abstraction (Anthropic, OpenAI-compatible) |
| `app/qa.py` | RAG answer: relevance floor, de-duplication, citation validation, grounding, retry |
| `app/classifier.py` | zero-shot and supervised document classification |
| `app/registry.py` | document records |
| `app/service.py` | orchestration, consistency, settings application, background processing queue |
| `app/api.py` | HTTP layer, middleware, UI serving |
| `evaluation/evaluate.py` | retrieval/QA evaluation (CLI and the Settings page's lab) |
| `web/src/` | React UI, see [FRONTEND.md](FRONTEND.md) |

## Design decisions

- **One orchestrator.** The API, CLI, evaluation and tests all call `DocMindService`, so the pipeline exists once.
- **Chunks never cross pages.** Every citation points to exactly one page.
- **Normalised vectors + inner product.** The score shown in the UI *is* the cosine similarity.
- **Registry is committed after the index is saved, and reconciled at startup.** "Processed" always means "searchable".
- **Same-origin UI.** FastAPI serves the built SPA, so there is no CORS to configure, the `SameSite=Strict` session cookie just works, and the admin token never needs to live in the build.
- **Anonymous sessions, not accounts.** A server-generated, HttpOnly cookie identifies each visitor; documents carry the owner key and every public query is scoped to it. See [SECURITY.md](SECURITY.md).
- **Single process.** The index, its locks, the background processing queue, the session store and the rate-limit counters live in memory (queued statuses are persisted, so interrupted work resumes after a restart). This is a deliberate simplicity trade-off; see [DEPLOYMENT.md](DEPLOYMENT.md).
- **No PyTorch at runtime.** The embedding model runs on ONNX Runtime, which keeps memory low enough for small (512 MB) instances ([EMBEDDINGS.md](EMBEDDINGS.md#memory-and-load-time)).
