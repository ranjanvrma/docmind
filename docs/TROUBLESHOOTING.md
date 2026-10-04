# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| UI says **"Unable to connect to DocMind"** | API not running, or still loading the embedding model (a few seconds; longer on the first start, when the model is downloaded) | Start `python main.py api`; wait for "DocMind API ready" in the log. In dev, check that `DOCMIND_API_URL` points at it. |
| Vite dev server: `/api/...` returns **502** | The proxy cannot reach the API | Same as above; the API must listen on the URL in `DOCMIND_API_URL` (default `http://127.0.0.1:8000`) |
| Every endpoint returns **503 "Search index unavailable: …"** | The index or registry files are missing, corrupt, or were built with another embedding model | Follow the message. Usually: stop the app, delete `DATA_DIR/index/`, start again, then *Process pending documents*; the registry marks affected documents for re-processing. If the message names `EMBEDDING_MODEL`, either restore the original model or rebuild the index. |
| UI keeps asking for an **access token** / API returns 401 | `DOCMIND_API_TOKEN` is set on the server | Enter that token in the dialog or in Settings → This browser |
| **Ask is disabled**, "AI question answering is currently unavailable" | No LLM key configured | Settings → Model → paste an API key → *Test connection*; or set `LLM_API_KEY` in `.env` and restart |
| *Test connection* fails: "rejected the API key" | Wrong or expired key | Replace the key |
| *Test connection* fails: "returned HTTP 400" | Wrong model name, or a parameter the model rejects (e.g. `temperature` or `max_tokens` on some OpenAI models, `effort` on models without it) | Check the model name; for Anthropic set Effort to *Default*; see the server log for the provider's message |
| Answer quality or style varies from question to question | A **router** model ID (e.g. `openrouter/free`, `openrouter/auto`) picks a different model per request. The server log shows `LLM endpoint routed model=… to …` | Expected with a router; `openrouter/free` is supported. For predictable answers, pin a concrete chat model ID, e.g. `nvidia/nemotron-3-super-120b-a12b:free` |
| Answer reads "I could not produce an answer that is supported by citations to your documents…", badge **"Could not be verified"** | The model's reply cited no provided source, and the one automatic retry did not either (for example a router picked a model that ignores the rules) | Ask again or rephrase; the model's raw reply is under *Show unverified reply*. If it happens often, pin a concrete model |
| Answer says it could not find the answer, and the server log says "No passage above the relevance floor" | Every retrieved passage scored below `MIN_RELEVANCE`, so the LLM was not called | Expected for off-topic questions. If the answer is in the documents, check what Search returns (it is not filtered) and lower *Relevance floor* in Settings |
| `/api/ask` returns 502 after a short delay | The provider failed twice (one automatic retry for 429/5xx/network errors), or returned a 4xx such as 400 | See the server log for the provider's status and message |
| Saving an LLM base URL fails: "must be an https:// URL" or "must point to a public host" | Production mode blocks UI-set base URLs that are not `https` or resolve to loopback, private or link-local addresses | Use a public `https` endpoint, or set `LLM_BASE_URL` in the environment (trusted) |
| Startup fails: "DOCMIND_API_TOKEN must be at least 24 characters in production" | Token too short | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| A document stays **Queued** or **Extracting, embedding and indexing…** for a long time | Background processing runs one document at a time on one worker; large PDFs on a slow CPU take minutes | Wait; the UI polls every 1.5 s. After a restart, interrupted documents are re-queued automatically |
| Answer ends with "(Answer truncated…)" | `LLM_MAX_TOKENS` reached (reasoning tokens count too) | Raise *Max answer tokens* or lower *Effort* |
| Answer says it **could not find the answer** although it is in the PDF | The right passage was not retrieved | Search for the same question to see what was retrieved; raise *Passages per question*; try a smaller chunk size and re-index (compare in the Evaluation lab) |
| Document **failed**: "No text could be extracted" | Scanned or image-only PDF | OCR is not supported; use a PDF with a text layer |
| Document failed: "password-protected" | Encrypted PDF | Remove the password first |
| Document failed: "has N pages; the limit is …" | Over `MAX_PAGES` | Raise the limit in Settings → Upload limits |
| Upload rejected: "exceeds … MB" / HTTP 413 | Over `MAX_UPLOAD_MB` / `MAX_REQUEST_MB` | Raise the limits in Settings, or upload fewer files at once |
| Changed chunk size, results unchanged | Existing documents keep their old chunks (this includes indexes built with the previous default of 800) | Use the *Re-index now* banner, or `POST /api/documents/process {"force": true}` |
| Saving chunk size fails above 1200 | `CHUNK_SIZE` is capped at 1200 characters; the embedding model reads only about 256 tokens | Use 1200 or less |
| Startup error: "Could not load 'onnx/model.onnx' for embedding model …" | No network access and the model is not in the Hugging Face cache, or `EMBEDDING_MODEL` names a model without an ONNX export | Allow network access on the first start, or use a model that ships `onnx/model.onnx` |
| Settings changes are ignored after restart | `data/settings.json` is invalid (logged as "Ignoring …settings.json") | Fix or delete the file; *Reset to defaults* deletes it |
| 3D scene does not appear | Reduced motion on, no WebGL, or a viewport narrower than 768 px | Expected: a static illustration is shown instead. Switch Motion to *Full* in Settings to force animation. |
| First request is slow | Model loading at startup, or a free-tier host waking from sleep (cold start) | Normal; the Docker image bakes the model in and runs offline. On hosts that sleep and have ephemeral disks, documents are also lost on restart ([DEPLOYMENT.md](DEPLOYMENT.md#5-persistent-storage-what-must-survive-a-restart)) |
| Docker: permission denied on `/app/data` | Bind-mount owner ≠ UID 1000 (Linux) | `sudo chown -R 1000 data` |

## Where to look

- **Server log** (stdout): processing results, retrieval timings, LLM errors (truncated), storage problems. It never contains document or query text.
- **`/api/health`**: whether the app is ready and an LLM is configured.
- **`/api/docs`**: interactive API documentation for trying requests directly.
