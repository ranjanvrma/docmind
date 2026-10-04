# HTTP API

All routes are under `/api`. Interactive documentation (OpenAPI/Swagger) is at `/api/docs` in development; with `APP_ENV=production` it is off unless `API_DOCS=true`. Every error body has the form `{"detail": "..."}`.

**Two surfaces.**

- **Public** (`/api/health`, `/api/documents*`, `/api/search`, `/api/ask`): no token. Each visitor is an anonymous, server-issued session (an HttpOnly cookie, `docmind_session` by default, created on the visitor's first upload) and only ever sees their own documents. All public routes except `/api/health` are rate limited per IP and per session (`429` with `Retry-After`; see [SECURITY.md](SECURITY.md#rate-limiting-and-quotas)).
- **Admin** (`/api/admin/*`): settings, LLM connection test, evaluation, diagnostics. Requires `DOCMIND_API_TOKEN` as `X-API-Key: <token>` or `Authorization: Bearer <token>`; a missing or wrong token gives `401`, and more than 10 failed attempts per IP in 15 minutes give `429` (a correct token is never throttled). Without a token configured, admin routes are open, which is allowed only in development.

Browser `POST`/`PATCH`/`DELETE` requests whose `Origin` is neither this server nor a `CORS_ALLOW_ORIGINS` entry get `403 Cross-site request blocked`. If stored data could not be loaded at startup, every endpoint returns `503` with recovery instructions. The old paths `/api/settings*` and `/api/evaluation/retrieval` no longer exist (`404`); they moved under `/api/admin/`.

## Health

| | |
|---|---|
| `GET /api/health` | Public, not rate limited. `200` with `status`, `version`, `embedding_model`, `llm_provider`, `llm_model`, `llm_configured`, `session_ttl_hours`, `limits` (`max_upload_mb`, `max_request_mb`, `max_pages`, `max_files_per_upload`, `max_documents`, `default_top_k`, `max_top_k`). Contains no global document or chunk counts. |

## Documents

All document routes act only on the calling visitor's documents. Another visitor's document ID behaves exactly like an unknown one (`404`). A request without a session sees an empty list.

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /api/documents/upload` | multipart `files` (1–20 PDFs) | `201` `{items: [{filename, status: uploaded\|duplicate\|rejected, doc_id, detail}]}`; sets the session cookie on a visitor's first upload | `400` every file rejected or >20 files · `409` document quota (`PUBLIC_MAX_DOCUMENTS`) reached · `411` no Content-Length · `413` request too large · `422` no files · `429` upload or new-session rate limit · `503` session capacity (`PUBLIC_MAX_SESSIONS`) reached |
| `POST /api/documents/process` | `{"doc_ids": [...] \| null, "force": false, "background": false}` | `200` `{items: [{doc_id, filename, status, chunk_count, skipped, detail}], indexed_chunks}`; with `"background": true`, `202` immediately | `404` unknown or another visitor's ID · `429` too many queued/processing documents (`PUBLIC_MAX_ACTIVE_JOBS`), or more than `PUBLIC_MAX_ACTIVE_JOBS` documents in one synchronous (non-background) request · `500` index save failed (documents marked failed) |
| `GET /api/documents` | | `200` list of documents | |
| `GET /api/documents/{id}` | | `200` one document (status, pages, empty pages, chunks, warnings, error, classification) | `404` |
| `GET /api/documents/{id}/chunks` | | `200` `[{chunk_id, page_number, chunk_index, text}]` in page order | `404` |
| `DELETE /api/documents/{id}` | | `204`; removes vectors, record and stored file | `404` |

`doc_ids: null` processes every one of the visitor's documents not yet processed; `force: true` re-processes (re-indexes) them.

**Background processing.** `"background": false` (the default, used by the CLI, tests and scripts) processes inside the request. With `"background": true` the request returns `202` at once and the documents move `uploaded → queued → processing → processed | failed` on a single worker thread in the API process; poll `GET /api/documents` for their status. The web UI always uses background mode. Document `status` is one of `uploaded`, `queued`, `processing`, `processed`, `failed`. Documents left `queued` or `processing` by a restart are re-queued automatically. Deleting a queued document removes it from the queue.

## Search and Q&A

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /api/search` | `{"query": "...", "top_k": 1-20?, "doc_ids": [...]?}` | `200` `{query, top_k, results: [{rank, score, chunk_id, doc_id, doc_name, page_number, text}]}` | `404` a `doc_ids` entry that is not the visitor's · `422` blank query / bad top_k |
| `POST /api/ask` | `{"question": "...", "top_k"?, "doc_ids"?}` | `200` `{question, answer, answered_from_documents, grounding, sources: [... + source_number, cited], invalid_citations, unverified_answer, model}` | `404` · `422` · `429` question limit (per visitor or server-wide) · `502` LLM provider error · `503` no LLM configured |

Without `doc_ids`, search and Q&A cover only the visitor's own processed documents; a visitor with none gets no results and no LLM call is made. `score` is the cosine similarity between query and passage (−1…1), not a probability. Search results are not filtered by `MIN_RELEVANCE`; Q&A is. `grounding` is `grounded`, `not_found` or `ungrounded`; `answered_from_documents` is true only when it is `grounded`. `unverified_answer` is `null` unless the model's reply could not be grounded even after a retry. See [CITATIONS.md](CITATIONS.md) for `cited`, `invalid_citations`, `grounding` and `unverified_answer`. A `502` never contains the provider's error body (details go to the server log).

## Admin: settings

All admin routes require the administrator token (see above).

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `GET /api/admin/settings` | | `200` `{values, overridden, llm_api_key: {configured, source, withheld}, read_only}`. Never contains secrets. | |
| `PATCH /api/admin/settings` | any subset of the editable fields ([CONFIGURATION.md](CONFIGURATION.md)) | `200` new view; applied immediately and saved to `settings.json` | `422` invalid value, a field that is not editable, or (in production) an LLM base URL that is not `https` or resolves to a non-public address |
| `DELETE /api/admin/settings/llm-api-key` | | `200`; forgets a key saved from the UI (the environment key applies again) | |
| `POST /api/admin/settings/reset` | | `200`; deletes all saved overrides | |
| `POST /api/admin/settings/test-llm` | | `200` `{ok, message, latency_ms, model}` from one tiny real LLM request | |

## Admin: evaluation and diagnostics

| Method & path | Body | Success |
|---|---|---|
| `POST /api/admin/evaluation/retrieval` | `{"ks": [1, 3, 5]}` | `200` report: `metrics` (hit rate, precision, recall per k), `mrr`, `misses`, settings used, dataset description. Runs on a temporary index of the bundled demo dataset. |
| `GET /api/admin/diagnostics` | | `200` `{version, client_ip, forwarded_for_entries, trusted_proxy_count, active_sessions, documents, documents_without_owner, documents_by_status, indexed_chunks, rate_limiter_keys}`. `client_ip` is the address the rate limiter sees; use it to check `TRUSTED_PROXY_COUNT`. No secrets. |

## Examples

```bash
# Public: keep the session cookie between calls with a cookie jar
curl -c jar -b jar -F "files=@report.pdf" http://127.0.0.1:8000/api/documents/upload
curl -c jar -b jar -X POST http://127.0.0.1:8000/api/documents/process -H "Content-Type: application/json" -d "{}"
curl -c jar -b jar -X POST http://127.0.0.1:8000/api/search -H "Content-Type: application/json" -d '{"query": "main risks", "top_k": 3}'

# Admin
TOKEN=...   # DOCMIND_API_TOKEN
curl -H "X-API-Key: $TOKEN" -X PATCH http://127.0.0.1:8000/api/admin/settings -H "Content-Type: application/json" -d '{"chunk_size": 600}'
curl -H "X-API-Key: $TOKEN" http://127.0.0.1:8000/api/admin/diagnostics
```
