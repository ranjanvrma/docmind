# Architecture

DocMind has three layers: a React single-page app, a FastAPI backend, and a pipeline of small Python modules orchestrated by one service class. One process serves both the API (under `/api`) and the built UI.

```
Browser ──▶ React SPA (web/)                       design system, 3D hero, citations UI
              │  fetch /api/*  (+ X-API-Key if a token is configured)
              ▼
           FastAPI (app/api.py)                    auth, size limits, validation, security headers,
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
3. SHA-256 of the bytes gives the document ID; a known ID is reported as a duplicate.
4. The file is stored as `data/raw/<doc_id>.pdf` (never under the user's name), and a registry record is created with status `uploaded`.

**Process** `POST /api/documents/process`
1. For each target document (`service._process_one`): remove old vectors, extract pages (`MAX_PAGES` enforced), remove page-number artifacts and repeated headers, chunk per page, embed in batches, add to FAISS, classify from the mean chunk vector.
2. `service._save_index_then_commit`: save the index, and only then mark documents `processed`. If saving fails, roll back the vectors and mark the documents `failed`.
3. **Synchronous or background.** By default this runs inside the request (CLI, tests, scripts). With `"background": true` (always used by the web UI) the API returns `202` immediately, documents become `queued`, and a single daemon worker thread in the API process processes them one at a time (`queued → processing → processed | failed`), under the same write lock as synchronous processing. The UI polls `GET /api/documents` every 1.5 s while anything is pending. This avoids proxy and request timeouts for large PDFs on slow CPUs. On shutdown the worker stops after the current document.

**Search** `POST /api/search`: embed the query with the same model, run exact inner-product search, map IDs back to chunk metadata (document, page, text).

**Ask** `POST /api/ask`: retrieve as in search, drop passages below `MIN_RELEVANCE` and exact duplicates; if nothing remains, return the "not found" sentence without calling the LLM. Otherwise build `[Source n] (document, page)` blocks within `MAX_CONTEXT_CHARS`, call the LLM with a grounding prompt, parse `[n]` citations, mark invalid numbers, and classify the reply as `grounded`, `not_found` or `ungrounded`. An ungrounded reply is retried once; if still ungrounded it is returned only as `unverified_answer` ([CITATIONS.md](CITATIONS.md)).

## Persistent state

| Path (under `DATA_DIR`) | Owner | Contents |
|---|---|---|
| `raw/<doc_id>.pdf` | `service.upload` | uploaded files, named by content hash |
| `processed/documents.json` | `registry.py` | one record per document: status, pages, chunks, classification, errors |
| `index/index.faiss`, `metadata.json`, `manifest.json` | `vector_store.py` | vectors, chunk metadata, consistency manifest |
| `settings.json` | `runtime_settings.py` | values saved from the Settings page (override `.env`) |
| `classifier/classifier.joblib` | `main.py train-classifier` | optional supervised classifier (needs `requirements-train.txt`; ignored with a warning if scikit-learn/joblib are not installed) |

At startup the service loads the settings overrides, loads the embedding model and the index (refusing a mismatched or damaged one with a clear error), reconciles the registry with the index so documents missing from the index return to `uploaded`, and re-queues documents left `queued` or `processing` by an interrupted run.

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
- **Same-origin UI.** FastAPI serves the built SPA, so there is no CORS to configure and the API token never needs to live in the build.
- **Single process.** The index, its locks and the background processing queue live in memory (queued statuses are persisted, so interrupted work resumes after a restart). This is a deliberate simplicity trade-off; see [DEPLOYMENT.md](DEPLOYMENT.md).
- **No PyTorch at runtime.** The embedding model runs on ONNX Runtime, which keeps memory low enough for small (512 MB) instances ([EMBEDDINGS.md](EMBEDDINGS.md#memory-and-load-time)).
