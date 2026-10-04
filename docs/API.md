# HTTP API

All routes are under `/api`. Interactive documentation (OpenAPI/Swagger) is at `/api/docs` in development; with `APP_ENV=production` it is off unless `API_DOCS=true`. Every error body has the form `{"detail": "..."}`.

**Authentication.** If `DOCMIND_API_TOKEN` is set, send `X-API-Key: <token>` (or `Authorization: Bearer <token>`) with every request except `GET /api/health`. A missing or wrong token gives `401`. If stored data could not be loaded at startup, every endpoint returns `503` with recovery instructions.

## Health

| | |
|---|---|
| `GET /api/health` | Public. `200` with `version`, `embedding_model`, `llm_provider`, `llm_model`, `llm_configured`, `auth_required`, `documents`, `indexed_chunks`, `limits` (`max_upload_mb`, `max_request_mb`, `max_pages`, `max_files_per_upload`, `default_top_k`, `max_top_k`). |

## Documents

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /api/documents/upload` | multipart `files` (1–20 PDFs) | `201` `{items: [{filename, status: uploaded\|duplicate\|rejected, doc_id, detail}]}` | `400` every file rejected or >20 files · `411` no Content-Length · `413` request too large · `422` no files |
| `POST /api/documents/process` | `{"doc_ids": [...] \| null, "force": false, "background": false}` | `200` `{items: [{doc_id, filename, status, chunk_count, skipped, detail}], indexed_chunks}`; with `"background": true`, `202` immediately | `404` unknown ID · `500` index save failed (documents marked failed) |
| `GET /api/documents` | | `200` list of documents | |
| `GET /api/documents/{id}` | | `200` one document (status, pages, empty pages, chunks, warnings, error, classification) | `404` |
| `GET /api/documents/{id}/chunks` | | `200` `[{chunk_id, page_number, chunk_index, text}]` in page order | `404` |
| `DELETE /api/documents/{id}` | | `204`; removes vectors, record and stored file | `404` |

`doc_ids: null` processes every document not yet processed; `force: true` re-processes (re-indexes) them.

**Background processing.** `"background": false` (the default, used by the CLI, tests and scripts) processes inside the request. With `"background": true` the request returns `202` at once and the documents move `uploaded → queued → processing → processed | failed` on a single worker thread in the API process; poll `GET /api/documents` for their status. The web UI always uses background mode. Document `status` is one of `uploaded`, `queued`, `processing`, `processed`, `failed`. Documents left `queued` or `processing` by a restart are re-queued automatically. Deleting a queued document removes it from the queue.

## Search and Q&A

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `POST /api/search` | `{"query": "...", "top_k": 1-20?, "doc_ids": [...]?}` | `200` `{query, top_k, results: [{rank, score, chunk_id, doc_id, doc_name, page_number, text}]}` | `422` blank query / bad top_k |
| `POST /api/ask` | `{"question": "...", "top_k"?, "doc_ids"?}` | `200` `{question, answer, answered_from_documents, grounding, sources: [... + source_number, cited], invalid_citations, unverified_answer, model}` | `422` · `502` LLM provider error · `503` no LLM configured |

`score` is the cosine similarity between query and passage (−1…1), not a probability. Search results are not filtered by `MIN_RELEVANCE`; Q&A is. `grounding` is `grounded`, `not_found` or `ungrounded`; `answered_from_documents` is true only when it is `grounded`. `unverified_answer` is `null` unless the model's reply could not be grounded even after a retry. See [CITATIONS.md](CITATIONS.md) for `cited`, `invalid_citations`, `grounding` and `unverified_answer`. A `502` never contains the provider's error body (details go to the server log).

## Settings

| Method & path | Body | Success | Errors |
|---|---|---|---|
| `GET /api/settings` | | `200` `{values, overridden, llm_api_key: {configured, source, withheld}, read_only}`. Never contains secrets. | |
| `PATCH /api/settings` | any subset of the editable fields ([CONFIGURATION.md](CONFIGURATION.md)) | `200` new view; applied immediately and saved to `settings.json` | `422` invalid value, a field that is not editable, or (in production) an LLM base URL that is not `https` or resolves to a non-public address |
| `DELETE /api/settings/llm-api-key` | | `200`; forgets a key saved from the UI (the environment key applies again) | |
| `POST /api/settings/reset` | | `200`; deletes all saved overrides | |
| `POST /api/settings/test-llm` | | `200` `{ok, message, latency_ms, model}` from one tiny real LLM request | |

## Evaluation

| Method & path | Body | Success |
|---|---|---|
| `POST /api/evaluation/retrieval` | `{"ks": [1, 3, 5]}` | `200` report: `metrics` (hit rate, precision, recall per k), `mrr`, `misses`, settings used, dataset description. Runs on a temporary index of the bundled demo dataset. |

## Examples

```bash
TOKEN=...   # only if DOCMIND_API_TOKEN is set
curl -H "X-API-Key: $TOKEN" -F "files=@report.pdf" http://127.0.0.1:8000/api/documents/upload
curl -H "X-API-Key: $TOKEN" -X POST http://127.0.0.1:8000/api/documents/process -H "Content-Type: application/json" -d "{}"
curl -H "X-API-Key: $TOKEN" -X POST http://127.0.0.1:8000/api/search -H "Content-Type: application/json" -d '{"query": "main risks", "top_k": 3}'
curl -H "X-API-Key: $TOKEN" -X PATCH http://127.0.0.1:8000/api/settings -H "Content-Type: application/json" -d '{"chunk_size": 600}'
```
