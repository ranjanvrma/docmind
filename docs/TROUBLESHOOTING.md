# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| UI says **"Unable to connect to DocMind"** | API not running, or still loading the embedding model (5–15 s) | Start `python main.py api`; wait for "DocMind API ready" in the log. In dev, check that `DOCMIND_API_URL` points at it. |
| Vite dev server: `/api/...` returns **502** | The proxy cannot reach the API | Same as above; the API must listen on the URL in `DOCMIND_API_URL` (default `http://127.0.0.1:8000`) |
| Every endpoint returns **503 "Search index unavailable: …"** | The index or registry files are missing, corrupt, or were built with another embedding model | Follow the message. Usually: stop the app, delete `DATA_DIR/index/`, start again, then *Process pending documents*; the registry marks affected documents for re-processing. If the message names `EMBEDDING_MODEL`, either restore the original model or rebuild the index. |
| UI keeps asking for an **access token** / API returns 401 | `DOCMIND_API_TOKEN` is set on the server | Enter that token in the dialog or in Settings → This browser |
| **Ask is disabled**, "AI question answering is currently unavailable" | No LLM key configured | Settings → Model → paste an API key → *Test connection*; or set `LLM_API_KEY` in `.env` and restart |
| *Test connection* fails: "rejected the API key" | Wrong or expired key | Replace the key |
| *Test connection* fails: "returned HTTP 400" | Wrong model name, or a parameter the model rejects (e.g. `temperature` or `max_tokens` on some OpenAI models, `effort` on models without it) | Check the model name; for Anthropic set Effort to *Default*; see the server log for the provider's message |
| Odd one-line answers such as "User Safety: safe", or answer quality that varies from question to question | A **router** model ID (e.g. `openrouter/free`, `openrouter/auto`) picks a different model per request, sometimes a content-safety classifier. The server log shows `LLM endpoint routed model=… to …` | Pin a concrete chat model ID, e.g. `nvidia/nemotron-3-super-120b-a12b:free` |
| Answer ends with "(Answer truncated…)" | `LLM_MAX_TOKENS` reached (reasoning tokens count too) | Raise *Max answer tokens* or lower *Effort* |
| Answer says it **could not find the answer** although it is in the PDF | The right passage was not retrieved | Search for the same question to see what was retrieved; raise *Passages per question*; try a smaller chunk size and re-index (compare in the Evaluation lab) |
| Document **failed**: "No text could be extracted" | Scanned or image-only PDF | OCR is not supported; use a PDF with a text layer |
| Document failed: "password-protected" | Encrypted PDF | Remove the password first |
| Document failed: "has N pages; the limit is …" | Over `MAX_PAGES` | Raise the limit in Settings → Upload limits |
| Upload rejected: "exceeds … MB" / HTTP 413 | Over `MAX_UPLOAD_MB` / `MAX_REQUEST_MB` | Raise the limits in Settings, or upload fewer files at once |
| Changed chunk size, results unchanged | Existing documents keep their old chunks | Use the *Re-index now* banner, or `POST /api/documents/process {"force": true}` |
| Settings changes are ignored after restart | `data/settings.json` is invalid (logged as "Ignoring …settings.json") | Fix or delete the file; *Reset to defaults* deletes it |
| 3D scene does not appear | Reduced motion on, no WebGL, or a viewport narrower than 768 px | Expected: a static illustration is shown instead. Switch Motion to *Full* in Settings to force animation. |
| First request is slow | Model loading at startup | Normal; the Docker image bakes the model in and runs offline |
| Docker: permission denied on `/app/data` | Bind-mount owner ≠ UID 1000 (Linux) | `sudo chown -R 1000 data` |

## Where to look

- **Server log** (stdout): processing results, retrieval timings, LLM errors (truncated), storage problems. It never contains document or query text.
- **`/api/health`**: whether the app is ready and an LLM is configured.
- **`/api/docs`**: interactive API documentation for trying requests directly.
