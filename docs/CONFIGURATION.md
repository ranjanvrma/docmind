# Configuration

DocMind has two configuration sources:

1. **Environment** (`.env` or real environment variables): read at startup by `app/config.py`. Invalid values stop the app with a clear message.
2. **Settings page** (administrator only, `PATCH /api/admin/settings`): values saved there are written to `<DATA_DIR>/settings.json`, **override the environment**, are validated with the same rules, and apply immediately without a restart. *Reset to defaults* deletes the file.

Values that are security boundaries or need a rebuild are **environment-only**: `DOCMIND_API_TOKEN`, `CORS_ALLOW_ORIGINS`, `APP_ENV`, `API_DOCS`, `TRUSTED_PROXY_COUNT`, all `PUBLIC_*` limits, `SESSION_TTL_HOURS`, `SESSION_COOKIE_NAME`, `EMBEDDING_MODEL`, `DATA_DIR`, `WEB_DIST_DIR`, `LOG_LEVEL`. A browser session can therefore never widen its own access, and visitors cannot reach the settings at all.

An `LLM_API_KEY` from the environment is only sent to the environment's provider and base URL. If the provider or base URL is changed on the Settings page, a key must be entered for the new endpoint as well; until then Q&A reports that no key is configured. This stops anyone holding the administrator token from redirecting the server's key to a host they control.

In `APP_ENV=production`, an `LLM_BASE_URL` saved from the Settings page must be `https` and resolve only to public IP addresses (no loopback, private or link-local hosts); see [SECURITY.md](SECURITY.md#secret-handling). The environment's own `LLM_BASE_URL` is not restricted, and development mode allows local endpoints such as Ollama.

## Reference

| Variable | Default | Editable in UI | Meaning |
|---|---|---|---|
| `LLM_PROVIDER` | `anthropic` | ✓ | `anthropic` (official SDK) or `openai` (any OpenAI-compatible `/chat/completions` API) |
| `LLM_API_KEY` | – | ✓ (write-only) | **Secret.** Needed only for Q&A. Never returned by the API. |
| `LLM_MODEL` | `claude-opus-5` | ✓ | Model name for the provider |
| `LLM_BASE_URL` | – | ✓ | OpenAI-compatible host, e.g. `https://api.groq.com/openai/v1`, `https://openrouter.ai/api/v1`, `http://localhost:11434/v1` (local hosts only from the environment or in development) |
| `LLM_EFFORT` | – | ✓ | Anthropic only: `low`/`medium`/`high`/`xhigh`/`max`. Empty = model default. |
| `LLM_MAX_TOKENS` | `8192` | ✓ | Response limit including reasoning tokens. Truncated answers are labelled. |
| `LLM_TEMPERATURE` | `0` | ✓ | OpenAI-compatible client only |
| `LLM_TIMEOUT_SECONDS` | `60` | ✓ | Per-request timeout |
| `MAX_CONTEXT_CHARS` | `6000` | ✓ | Retrieved text sent to the LLM per question |
| `TOP_K` | `5` | ✓ | Default passages per query (1–20) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `600` / `150` | ✓ | Characters per chunk / shared characters. `CHUNK_SIZE` is capped at 1200 (`MAX_CHUNK_SIZE`): the embedding model reads only about 256 tokens (~1000 characters). Re-index to apply to existing documents. |
| `MIN_RELEVANCE` | `0.15` | ✓ ("Relevance floor", slider 0–0.5) | Q&A only: passages with a lower cosine score are not sent to the LLM; if none remain, DocMind abstains without calling it. Must be ≥ 0 and < 1. Search results are not filtered. |
| `MIN_CHARS_PER_PAGE` | `20` | ✓ | Pages with less text count as empty |
| `MAX_UPLOAD_MB` | `25` | ✓ | Per-file upload limit |
| `MAX_REQUEST_MB` | `100` | ✓ | Whole upload request; checked before the body is read |
| `MAX_PAGES` | `500` | ✓ | Pages per document |
| `CLASSIFIER_LABELS` | `Research Paper,Report,Assignment,Notes,Policy,Other` | ✓ | Zero-shot categories |
| `DOCMIND_API_TOKEN` | – | ✗ | **Secret.** Administrator token for `/api/admin/*` (sent as `X-API-Key` or `Authorization: Bearer`). Public endpoints never need it. Without it the admin endpoints are open, which is allowed only in development; in production it is required and must be at least 24 characters. |
| `TRUSTED_PROXY_COUNT` | `0` | ✗ | Reverse proxies in front of the app. `0` = the TCP peer is the client IP; `n` = the n-th `X-Forwarded-For` entry from the right. Expected `1` on Render (unverified; check `client_ip` in `/api/admin/diagnostics`). Too high lets clients spoof their IP. |
| `PUBLIC_RATE_LIMIT` / `PUBLIC_RATE_WINDOW_SECONDS` | `120` / `60` | ✗ | Public API requests per IP and per session (not `/api/health`). `0` disables. |
| `PUBLIC_QA_RATE_LIMIT` / `PUBLIC_QA_RATE_WINDOW_SECONDS` | `20` / `3600` | ✗ | Questions per IP and per session |
| `PUBLIC_QA_GLOBAL_LIMIT` | `200` | ✗ | Questions per QA window across all visitors (counted only when the visitor has processed documents); protects the server's LLM quota |
| `PUBLIC_UPLOAD_RATE_LIMIT` / `PUBLIC_UPLOAD_RATE_WINDOW_SECONDS` | `20` / `3600` | ✗ | Uploaded files per IP and per session |
| `PUBLIC_NEW_SESSIONS_PER_IP` | `20` | ✗ | New sessions per IP per hour |
| `PUBLIC_MAX_SESSIONS` | `1000` | ✗ | Active sessions on the server; beyond it new visitors get `503` |
| `PUBLIC_MAX_DOCUMENTS` | `20` | ✗ | Documents per session; beyond it `409` |
| `PUBLIC_MAX_ACTIVE_JOBS` | `5` | ✗ | Queued or processing documents per session (beyond it `429`); also the most documents a visitor's synchronous (non-background) process request may handle, because such a request holds the processing lock. Caps `max_files_per_upload` in `/api/health` at `min(20, value)`. |
| `SESSION_TTL_HOURS` | `24` | ✗ | Idle sessions and all their documents are deleted after this; also the cookie's `Max-Age` |
| `SESSION_COOKIE_NAME` | `docmind_session` | ✗ | Letters, digits, `_` and `-` only |
| `CORS_ALLOW_ORIGINS` | – | ✗ | Comma-separated exact origins (`https://ui.example.com`; no `*`, no trailing slash) for a separately hosted frontend. Not needed for the bundled UI. Also the only cross-origin `Origin` values accepted on `POST`/`PATCH`/`DELETE`. Visitor sessions do not work from another origin. |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | ✗ | Must ship an ONNX export (`onnx/model.onnx`) and use mean or CLS pooling. Changing it requires re-processing everything |
| `EMBEDDING_BATCH_SIZE` | `32` | ✗ | |
| `DATA_DIR` | `./data` | ✗ | Uploads, index, registry, saved settings, sessions |
| `WEB_DIST_DIR` | `./web/dist` | ✗ | Built UI served at `/` if present |
| `LOG_LEVEL` | `INFO` | ✗ | |
| `APP_ENV` | `development` (`production` in the Docker image) | ✗ | `production` refuses to start without a `DOCMIND_API_TOKEN` of at least 24 characters, restricts LLM base URLs set from the UI to public `https` hosts, and hides the API docs by default |
| `API_DOCS` | unset: on in development, off in production | ✗ | Serve `/api/docs` and `/api/openapi.json`; `true`/`false` overrides |
| `HOST` / `PORT` | `127.0.0.1` / `8000` (`0.0.0.0` / `8000` in Docker) | ✗ | Bind address and port of `python main.py api`; cloud platforms usually set `PORT` |
| `VITE_API_BASE_URL` | – (same origin) | – | **Build-time**, web UI only: API origin when the UI is hosted elsewhere. Public; never a secret. |
| `DOCMIND_API_URL` | `http://127.0.0.1:8000` | – | Development only: target of the Vite proxy |

## Tuning advice

- **Chunk size.** Smaller chunks give sharper matches but less context per passage. Use the Settings page's *Evaluation lab* to compare: on the bundled demo set, 600/150 (the current default) measured Hit@1 0.85 and MRR 0.917 against 0.70 and 0.838 at 800/150 (the previous default). With 20 queries that is a hint, not proof ([EVALUATION.md](EVALUATION.md)). Existing indexes keep their old chunks until re-indexed.
- **Relevance floor.** Raising `MIN_RELEVANCE` makes Q&A abstain more often without calling the LLM. It filters only clearly off-topic passages: on the sample set, unanswerable but on-topic questions still scored 0.45–0.77, so it cannot replace the model's own abstention ([RAG_PIPELINE.md](RAG_PIPELINE.md#relevance-floor-and-duplicates)).
- **Top-k and context budget.** More passages raise the chance that the answer is in context, but cost more tokens and give the model more to ignore.
- **Effort.** For grounded Q&A, `low` or `medium` is usually sufficient and cheaper. Leave it empty for models that don't support it.
