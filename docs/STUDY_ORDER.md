# DocMind: Study Order

Work through the stages in order. Don't move on until you can do the "explain before moving on" items **out loud without looking**. Run code as you go: the notebook (`notebooks/pipeline_walkthrough.ipynb`, needs `pip install jupyter`) and `pytest tests/<file> -v` are the quickest ways to see each stage working. The detailed trace for every stage is in `docs/CODE_WALKTHROUGH.md`.

Rough time budget: 2–3 focused days for stages 1–8, 2 days for 9–13, 1 day for 14–16.

---

### Stage 1. Python architecture
- **Read:** `app/service.py` (all of it), `app/models.py`, `app/config.py`, `main.py`
- **Learn:** layered architecture (UI → API → service → modules); dataclasses vs Pydantic models; dependency injection by constructor (`DocMindService(settings, embedder=..., llm=...)`); `lru_cache` singletons; configuration from the environment.
- **Explain before moving on:** the lifecycle `uploaded → (queued → processing →) processed | failed`, and when the background worker is used; why the service is the only orchestrator; which entry points (API, CLI, evaluation, tests) call it; how tests swap in fakes.
- **Interview questions:** "Why a service layer?" "How is configuration injected?" (INTERVIEW_PREP F1, F2)

### Stage 2. PDF processing
- **Read:** `app/ingestion.py`, `app/utils.py` (`sanitize_filename`, `sha256_bytes`), `service.upload`, `tests/test_ingestion.py`
- **Learn:** PDF text layers vs scanned images; magic bytes; content hashing; PyMuPDF `get_text("text", sort=True)`; why OCR is needed for scans.
- **Explain before moving on:** each validation check and what it protects against; why the ID is a hash; what `empty_pages` and the warnings mean; what happens with an encrypted or corrupt file.
- **Interview questions:** "Walk me through an upload." "Why store files under a hash?" (D1, D2, G4)

### Stage 3. Preprocessing
- **Read:** `app/preprocessing.py`, `tests/test_preprocessing.py`
- **Learn:** Unicode NFKC, ligatures, de-hyphenation, line joining, header/footer detection; why not to stem or remove stop words for transformers.
- **Explain before moving on:** the order of operations in `clean_text`; the 60% repeated-line rule; **finding F1 (fixed)**: why the old rule deleted table numbers, and how `_remove_page_number_lines` now tells page numbers apart from data (edge position + equals the page number). Run `clean_text("Year\n2023\n1480")` and `clean_text("Body.\n12", page_number=12)` yourself.
- **Interview questions:** "Why so little preprocessing?" "What can go wrong with regex cleanup?" (B7, D8)

### Stage 4. Chunking
- **Read:** `app/chunking.py`, `tests/test_chunking.py`
- **Learn:** greedy sentence packing, whole-sentence overlap, the long-sentence fallback, determinism, per-page chunking; the chunk ID format `doc:p3:c0`.
- **Explain before moving on:** trace `chunk_text` by hand on a 5-sentence paragraph with size 100 and overlap 40; explain why the default is 600 characters and the cap 1200 (the 256-token model limit, and the chunk-size sweep in `docs/EVALUATION.md`); explain the page-boundary trade-off.
- **Interview questions:** "Why chunk?" "Size and overlap trade-off?" (B1, B2, B3, D3)

### Stage 5. Embeddings
- **Read:** `app/embeddings.py`, `tests/test_embeddings.py`, `tests/conftest.py` (`HashingEncoder`)
- **Learn:** what an embedding is; batch encoding (length-sorted batches); L2 normalisation; model caching (`load_encoder`); the `EncoderModel` protocol used for fakes; ONNX Runtime `InferenceSession`, the `tokenizers` library and `huggingface_hub` downloads.
- **Explain before moving on:** input and output shapes (`list[str]` → `(n, 384)` float32, unit rows); why normalise; why queries and documents must use the same model; why tests use a hashing encoder; how `OnnxSentenceEncoder` reproduces the sentence-transformers pipeline and how equivalence was verified; why PyTorch was removed (memory and load time, `docs/EMBEDDINGS.md`).
- **Interview questions:** "What is an embedding?" "Why 384?" "Why ONNX Runtime instead of PyTorch?" (A3, H1)

### Stage 6. Cosine similarity
- **Read:** `embeddings.normalize_rows`, notebook cells 5–6
- **Learn:** the dot product, norms, cos = a·b/(‖a‖‖b‖), and for unit vectors ‖a−b‖² = 2 − 2cos.
- **Explain before moving on:** why an inner-product index returns cosine here; why L2 gives the same ranking; why scores are relative (correct hits in this repo scored about 0.35–0.47, not ">0.5").
- **Interview questions:** "Cosine vs Euclidean?" "Is 0.4 a good score?" (B4)

### Stage 7. FAISS
- **Read:** `app/vector_store.py`, `tests/test_retrieval.py` (store tests), `utils.atomic_write_bytes`
- **Learn:** `IndexFlatIP`, `IndexIDMap2`, `add_with_ids`, `remove_ids`, `search` returning scores and IDs (−1 = padding), serialisation; IVF and HNSW at a concept level only.
- **Explain before moving on:** how metadata stays in sync (own IDs, never reused, lock, atomic writes, manifest check); what `load_or_create` refuses and why; **findings F3/F4 (fixed)**: why the registry is now updated only after the index save, what `_reconcile_registry_with_index` does at startup, and why a damaged index now gives a `VectorStoreError` (503 from the API) instead of a crash.
- **Interview questions:** "How do you keep index and metadata in sync?" "When would you switch index types?" (C1, C2, C6)

### Stage 8. Retrieval
- **Read:** `app/retrieval.py`, `service.search`, `api.search`, `SearchRequest` / `SearchHit` in `models.py`
- **Learn:** top-k retrieval; document filtering by over-fetching; clamping k; what is logged and what isn't.
- **Explain before moving on:** the full path of a query from HTTP to ranked hits; why the query text isn't logged.
- **Interview questions:** "What is top-k?" "Weaknesses of dense retrieval?" (A6, C4)

### Stage 9. Transformers (only what DocMind uses)
- **Read:** `docs/CODE_WALKTHROUGH.md` Part 4; the model card for `sentence-transformers/all-MiniLM-L6-v2`
- **Learn:** WordPiece tokenisation (uncased; 256 limit); token vs contextual embeddings; self-attention (query/key/value, softmax); encoder layers (6 here); mean pooling; contrastive training for sentence similarity.
- **Explain before moving on:** what happens inside `OnnxSentenceEncoder.encode("...")`, step by step; why plain BERT isn't ideal for similarity; that DocMind fine-tunes nothing and does not use PyTorch at all (it runs an existing ONNX export).
- **Interview questions:** "How does a transformer make a sentence embedding?" "What is attention?" (E1, E2, E3)

### Stage 10. RAG
- **Read:** `app/prompts.py`, `app/qa.py`, `service.ask`, `tests/test_qa.py`
- **Learn:** the relevance floor and de-duplication (`select_passages`); context construction with a budget; source numbering; the system-prompt rules; the abstention sentence; citation parsing and validation; `grounding` (`grounded` / `not_found` / `ungrounded`), the single retry with `RETRY_REMINDER`, `UNVERIFIED_ANSWER` and `unverified_answer`; `answered_from_documents == (grounding == "grounded")`.
- **Explain before moving on:** trace a question end to end; why the sources are exactly the included chunks; what is *not* verified (claim support); **finding F5 (fixed)**: why only one- or two-digit markers count as citations; **F6** (still open); what happens when nothing is retrieved or nothing passes the floor; why the floor (0.15) cannot replace abstention; what the user sees for an ungrounded reply.
- **Interview questions:** "What is RAG?" "How do you reduce hallucination?" "What if the answer isn't in the documents?" "What if the reply cites nothing?" (E4, E5, D4, D5, C3, H2, H3)

### Stage 11. LLMs
- **Read:** `app/llm.py`, `.env.example`
- **Learn:** the abstract base class + provider implementations; the factory function; error mapping to 502/503; the single transport retry for 429/5xx/network errors (`Retry-After`, capped at 5 s); router models and the "routed model" log line; text vs non-text content blocks; stop reasons (`refusal`, `max_tokens`); API keys from the environment; the SSRF guard on UI-set base URLs (`runtime_settings.check_public_endpoint`).
- **Explain before moving on:** how to add a new provider; why the LLM client is lazy; that the Anthropic path has never been run live and that `LLM_TEMPERATURE` only affects the OpenAI-compatible client; what the `openrouter/free` live test showed (`docs/LLM_INTEGRATION.md`).
- **Interview questions:** "How is the provider abstracted?" "How are LLM errors handled?" "Isn't a configurable base URL an SSRF risk?" (C7, G2, H5)

### Stage 12. Classification
- **Read:** `app/classifier.py`, `data/classifier/README.md`, `data/classifier/sample_training.csv`, `tests/test_classifier.py`
- **Learn:** mean-pooled document vectors; zero-shot by description similarity; logistic regression; stratified k-fold CV; joblib (pickle) safety; why scikit-learn/joblib are optional (`requirements-train.txt`) and what happens to a trained model file without them.
- **Explain before moving on:** both modes and when each is used; why CV on 48 synthetic texts isn't a performance claim; the train/inference representation mismatch; why the trained model was removed (it mislabelled the ML notes).
- **Interview questions:** "How does your classifier work?" "Zero-shot vs supervised?" (E7, E8)

### Stage 13. Evaluation
- **Read:** `evaluation/evaluate.py`, `evaluation/datasets/sample_eval.json`, `evaluation/make_sample_docs.py`, `tests/test_evaluation.py`; run `python evaluation/evaluate.py` and open `evaluation/results/retrieval_per_query.csv`
- **Learn:** Hit@K, Precision@K, Recall@K, MRR; page-level labels; the isolated temp index; token F1; baselines, held-out splits, confidence intervals.
- **Explain before moving on:** compute each metric by hand for one query from the CSV; why P@5 = 0.24 (at 800/150) is expected; what the chunk-size sweep showed and why it is a weak signal; every reason the demo numbers aren't evidence; what a real evaluation would look like (CODE_WALKTHROUGH Part 8).
- **Interview questions:** "How do you know retrieval works?" "Precision vs recall?" (D7, C5, C8, E6)

### Stage 14. FastAPI
- **Read:** `app/api.py`, `models.py` (API schemas), `app/sessions.py`, `app/ratelimit.py`, `tests/test_api.py`, `tests/test_public.py`, `docs/SECURITY.md`; start `python main.py api` and use `/api/docs`
- **Learn:** app factory; `lifespan`; `Depends`; Pydantic validation → 422; `response_model`; exception handlers; sync routes in a thread pool; multipart uploads (and Starlette's temp-file spooling); `202` background processing (`service.enqueue`, the worker thread, restart recovery, `tests/test_background.py`); public vs admin routers; anonymous sessions (HttpOnly, SameSite=Strict cookie, only the hash stored); owner-scoped queries; sliding-window rate limiting and `Retry-After`; `X-Forwarded-For` and `TRUSTED_PROXY_COUNT`; the Origin check as CSRF defence.
- **Explain before moving on:** every endpoint's method, body, status codes and service call (`docs/API.md`; CODE_WALKTHROUGH Part 9 predates some of them); why routes contain no business logic; the lock order `_write_lock` then `_queue_lock`; why another visitor's document returns `404` rather than `403`; what the rate limiter cannot do (several instances, restarts, shared NAT).
- **Interview questions:** "List your endpoints." "Status codes?" "Role of Pydantic?" "What if the server restarts during processing?" "How do you keep visitors' documents apart without accounts?" "How is abuse limited?" (G1, G2, B8, H4, and the public-mode questions in INTERVIEW_PREP)

### Stage 15. Web frontend (React)
- **Read:** `docs/FRONTEND.md`, then `web/src/lib/api.ts`, `lib/errors.ts`, `lib/markdown.ts`, `components/qa/AnswerContent.tsx`, `components/citations/CitationChip.tsx`, `components/upload/UploadZone.tsx`, `pages/SettingsPage.tsx`; run `cd web && npm run dev`
- **Learn:** React components and hooks; TanStack Query (including conditional polling); same-origin API calls and the Vite proxy; why untrusted text is rendered as React text; Motion basics and reduced motion; route code-splitting with React Router `lazy`; how the 3D scene is lazy-loaded with a fallback.
- **Explain before moving on:** each flow (upload with real progress, then background processing with live status; search; ask with citation chips and grounding badges; settings + evaluation lab behind administrator sign-in); why visitors send no token and the admin token lives only in memory, never in the bundle or browser storage; why 5xx error details are hidden; why the pipeline view doesn't show fake percentages; how an unverified reply is shown.
- **Interview questions:** "How does the web UI talk to the backend?" (G3)

### Stage 16. Docker
- **Read:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- **Learn:** multi-stage builds; base images; layer order (requirements before code); baking only the four ONNX model files in, then `HF_HUB_OFFLINE=1`; non-root users; bind mounts; `env_file`; healthchecks.
- **Explain before moving on:** what each line does; why one image serves both UI and API (same origin); why there is no PyTorch step; **what's unverified** (CODE_WALKTHROUGH Part 13). Ideally, install Docker and actually run `docker compose up --build` before claiming it works.
- **Interview questions:** "How is it containerised? Does it work?" "Is it production-ready?" (G6, G7)

---

### Final check before interviews
Re-read `docs/CODE_WALKTHROUGH.md` §0 (the audit findings) and `docs/RESUME_CLAIMS.md`. Practise the 30-second and 3-minute explanations in `docs/INTERVIEW_PREP.md` until you can give them without notes.
