# Security

DocMind is a public demo: anyone who can reach it can upload PDFs and ask questions without signing in. Each visitor works in an anonymous, server-issued session and sees only their own documents. One administrator token (`DOCMIND_API_TOKEN`) protects the server settings. There are no user accounts. This page lists what is protected, how, and what is not. It is a reasonable model for a single-instance demo, not enterprise-grade security.

## Public and admin surfaces

| Surface | Routes | Access |
|---|---|---|
| Public | `GET /api/health`, `POST /api/documents/upload`, `POST /api/documents/process`, `GET /api/documents`, `GET /api/documents/{id}`, `GET /api/documents/{id}/chunks`, `DELETE /api/documents/{id}`, `POST /api/search`, `POST /api/ask` | No token. Scoped to the visitor's session; rate limited (except health). |
| Admin | `GET`/`PATCH /api/admin/settings`, `DELETE /api/admin/settings/llm-api-key`, `POST /api/admin/settings/reset`, `POST /api/admin/settings/test-llm`, `POST /api/admin/evaluation/retrieval`, `GET /api/admin/diagnostics` | `DOCMIND_API_TOKEN` as `X-API-Key: <token>` or `Authorization: Bearer <token>`. |

- `DOCMIND_API_TOKEN` (environment only) is now **only** the administrator credential. It plays no part in visitor identity.
- The comparison uses `secrets.compare_digest` (constant time). Failed attempts are throttled: after 10 failures from one IP in 15 minutes, further attempts get `429`. Only failures are counted, so a correct token is never throttled.
- Without a token, admin routes are open; this is allowed only in development (the API logs a warning). `APP_ENV=production` refuses to start without a token of at least 24 characters.
- `/api/health` is public and not rate limited so probes can reach it. It returns the version, model names, `llm_configured`, `session_ttl_hours` and limits; it reveals no global document or chunk counts and nothing about other visitors.
- `GET /api/admin/diagnostics` returns operational counters (active sessions, documents, documents without owner, documents by status, indexed chunks, rate-limiter keys) and the client IP as the rate limiter sees it. It returns no secrets, cookies or document content.
- **The web UI never contains the token.** Visitors never need it. On the Settings page the administrator can sign in; the token is kept in memory for that page only (never in `localStorage` or `sessionStorage`), sent only to `/api/admin/*`, and reloading signs out. The UI also removes the `docmind.token` key that older versions stored.

## Anonymous sessions

- A session is created lazily, on a visitor's **first upload**. Listing, searching and asking never create one.
- The server generates the ID with `secrets.token_urlsafe(32)` (256 random bits) and sends it in the cookie `SESSION_COOKIE_NAME` (default `docmind_session`): `HttpOnly`, `SameSite=Strict`, `Path=/api`, `Max-Age = SESSION_TTL_HOURS x 3600`, and `Secure` when the request is HTTPS or when `APP_ENV=production` on a non-loopback host (so `docker compose` on `http://127.0.0.1` still works). The expiry slides with activity.
- The server stores only `sha256(id)[:32]` (the *owner key*) in `DATA_DIR/sessions.json` (atomic writes; last-seen times are flushed lazily, at most every 5 minutes, and on shutdown). A leaked copy of that file or of the document registry does not reveal a usable cookie.
- Unknown, malformed or expired cookies mean "no session". Clients cannot choose an identity; a new random ID is issued on the next upload.
- No secret is kept in browser storage, and JavaScript cannot read the session cookie.

## Document isolation

- Every document records the owner key of the session that uploaded it (`DocumentRecord.owner`, never returned by the API).
- Visitor document IDs are `sha256(owner + NUL + content)[:16]`, so the same PDF uploaded by two visitors becomes two separate documents. Duplicate detection works only within one session.
- Every public route passes the session's owner to the service. A request without a session uses the sentinel owner `-`, which matches no document; no visitor request runs an unscoped query.
- Another visitor's document behaves exactly like a missing one (`404`) for get, chunks, delete, process, and search/ask with `doc_ids`. Unfiltered search and ask search only the visitor's processed documents (FAISS results are filtered to their document IDs); a visitor with no processed documents gets no search and no LLM call.
- Documents with no owner (added with `python main.py ingest`, or uploaded before this version) are never visible to visitors.

## Data lifecycle

- A maintenance thread runs every 60 seconds. It deletes sessions idle for longer than `SESSION_TTL_HOURS` (default 24) together with all their documents (vectors, registry entries, stored PDFs), and deletes documents whose session no longer exists.
- At startup, stored PDFs without a registry entry are removed.
- On a host with an ephemeral disk (Render Free) everything, including `sessions.json`, is lost on restart, redeploy or spin-down; old cookies then simply mean "no session". The UI tells visitors: "Private to this browser · deleted after 24 h of inactivity or when the server restarts".

## Rate limiting and quotas

An in-process sliding-window limiter (`app/ratelimit.py`) counts each public request against the client IP **and** the session, so neither dropping the cookie nor sharing it across machines escapes the limits. Exceeding a limit gives `429` with `Retry-After` and a user-facing message. `0` disables a limit.

| Variable | Default | Applies to |
|---|---|---|
| `PUBLIC_RATE_LIMIT` / `PUBLIC_RATE_WINDOW_SECONDS` | 120 / 60 s | every public API request except `/api/health` |
| `PUBLIC_QA_RATE_LIMIT` / `PUBLIC_QA_RATE_WINDOW_SECONDS` | 20 / 3600 s | questions (`/api/ask`) |
| `PUBLIC_QA_GLOBAL_LIMIT` | 200 per QA window | questions from all visitors together; counted only when the visitor has processed documents. Protects the server's LLM (OpenRouter) quota. |
| `PUBLIC_UPLOAD_RATE_LIMIT` / `PUBLIC_UPLOAD_RATE_WINDOW_SECONDS` | 20 files / 3600 s | uploads |
| `PUBLIC_NEW_SESSIONS_PER_IP` | 20 per hour | new sessions per IP (stops cookie-dropping) |
| `PUBLIC_MAX_SESSIONS` | 1000 | active sessions; then `503` "DocMind is at capacity right now" |
| `PUBLIC_MAX_DOCUMENTS` | 20 | documents per session; then `409` |
| `PUBLIC_MAX_ACTIVE_JOBS` | 5 | queued or processing documents per session; then `429`. A visitor's synchronous `POST /api/documents/process` (without `background`) may process at most this many documents per request (else `429` "Process at most N documents at once."), because a synchronous request holds the processing lock. `/api/health` reports `max_files_per_upload = min(20, PUBLIC_MAX_ACTIVE_JOBS)`. |

`MAX_UPLOAD_MB`, `MAX_REQUEST_MB` and `MAX_PAGES` still apply (see Upload limits below).

**Client IP.** `TRUSTED_PROXY_COUNT` (default `0`) decides it. `0` uses the TCP peer. With `n > 0` the client IP is the n-th `X-Forwarded-For` entry from the right; entries further left are client-supplied and ignored, so forging the header does not help. Setting it higher than the real number of proxies lets clients spoof their IP. On Render `TRUSTED_PROXY_COUNT=1` is the expected value but has **not been verified** there; check that `client_ip` in `GET /api/admin/diagnostics` is your own public IP.

**Limits of this limiter.** Counters live in process memory: they reset on restart, and several instances would each count separately, so it is not suitable as the only limiter for a multi-instance deployment (use a shared store such as Redis, or the platform's rate limiting). Users behind one NAT or corporate proxy share the per-IP limits.

## CSRF

- The session cookie is `SameSite=Strict`, so browsers do not send it on cross-site requests.
- In addition, every `POST`/`PUT`/`PATCH`/`DELETE` (public and admin) checks `Origin`: a browser `Origin` must match the `Host` header or be listed in `CORS_ALLOW_ORIGINS`, otherwise `403 Cross-site request blocked`. Requests with `Sec-Fetch-Site: cross-site` and no `Origin` are also rejected. Non-browser clients send no `Origin` and are unaffected.

## CORS

Off by default. The bundled UI is served from the same origin, so it needs no CORS. `CORS_ALLOW_ORIGINS` (environment only) enables it for explicitly listed origins, for GET/POST/PATCH/DELETE, without credentials. Wildcards and malformed origins are rejected at startup. Because the session cookie is same-site only, a UI hosted on another origin is not supported for visitor sessions.

## Upload limits

| Check | Where | Result |
|---|---|---|
| Whole request size (`MAX_REQUEST_MB`) from `Content-Length`, **before reading the body** | `UploadSizeLimitMiddleware` | 413 |
| Missing `Content-Length` on upload | same | 411 |
| ≤ 20 files per request | upload route | 400 |
| Per-file size (`MAX_UPLOAD_MB`), `.pdf` extension, `%PDF-` magic bytes | `ingestion.validate_pdf_upload` | file rejected |
| Page count (`MAX_PAGES`), encrypted PDFs, unparseable PDFs | `ingestion.extract_pages` | document marked failed |

Files are stored as `<document-id>.pdf`; user-supplied names are sanitised and used for display only, so path traversal via filenames is impossible. Document IDs in URLs are looked up in the registry before any path is built. PDFs are parsed, never executed. The PDF parser (MuPDF, C code) runs in-process without a sandbox.

## Prompt injection and untrusted document text

Document text reaches the LLM. Mitigations are described in [PROMPTING.md](PROMPTING.md#prompt-injection-hardening): an untrusted-source rule in the system prompt, removal of `<sources>` delimiters and `[Source n]` headers from document text and from filenames in source headers, and a plain-text answer instruction. In a live test with four free models, an injected instruction on a PDF page was not followed and its link was not emitted. **Mitigated, not solved**: a malicious document can still influence an answer's content; one model reported the planted claim, with a citation, as something the source says. DocMind cannot tell true document content from planted false content.

## Markdown / HTML escaping in the UI

- All document text, filenames and LLM answers are rendered by React as text; React escapes them.
- Answers use a deliberately tiny Markdown subset (`web/src/lib/markdown.ts`): headings, lists, bold/italic, code, citations. **Links, images and raw HTML are never produced**; they stay literal text. A test renders hostile input (`<img onerror>`, `<script>`, Markdown images and `javascript:` links) and asserts that no `img`, `script`, `a` or `iframe` element appears.
- `dangerouslySetInnerHTML` is not used anywhere.

## Security headers

| Header | Applied to |
|---|---|
| `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; …` | the UI's `index.html` |
| `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin`, `Permissions-Policy` (camera, microphone, geolocation, payment off), `Strict-Transport-Security: max-age=31536000` (ignored by browsers over plain HTTP) | every response |

`'unsafe-inline'` for styles is needed because the animation library sets style attributes; scripts are restricted to the app's own origin.

## Secret handling

- `LLM_API_KEY` and `DOCMIND_API_TOKEN` come from the environment and are excluded from git (`.gitignore`) and the Docker build context (`.dockerignore`). They are hidden from `Settings.__repr__`.
- An LLM key saved from the Settings page is stored in `<DATA_DIR>/settings.json` (git- and docker-ignored, inside the persistent data volume). It is **write-only**: no endpoint ever returns it, and responses only say `configured` and `source`.
- Settings that define security boundaries (`DOCMIND_API_TOKEN`, `CORS_ALLOW_ORIGINS`, `APP_ENV`) cannot be changed through the API.
- **The environment's LLM key is bound to the environment's endpoint.** Changing the provider or base URL from the Settings page withholds that key until a key for the new endpoint is entered, so an admin-token holder cannot point the server at their own host and capture the key.
- **LLM base URLs set from the UI cannot reach internal addresses (SSRF guard).** In `APP_ENV=production`, a base URL saved through the API or Settings page must be `https` and its host must resolve only to public (`is_global`) IP addresses (`runtime_settings.check_public_endpoint`). This blocks loopback, private and link-local addresses, including cloud metadata endpoints such as `169.254.169.254`; otherwise anyone with the admin token could make the server send requests to internal services. DNS is checked when the setting is saved; a DNS rebinding afterwards is not covered. The operator's own `LLM_BASE_URL` environment value is trusted, and development mode allows local endpoints such as Ollama.
- Visitors cannot reach any settings endpoint, so the LLM key stays server-side and visitors cannot change the model or endpoint.
- `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key` and `*.log` are git- and docker-ignored. The web bundle can only contain `VITE_*` variables, and the only one used (`VITE_API_BASE_URL`) is a public URL.

## Production profile

`APP_ENV=production` (the Docker image's default) refuses to start without a `DOCMIND_API_TOKEN` of at least 24 characters, applies the SSRF guard above, marks the session cookie `Secure` (except on loopback), and turns off `/api/docs` and `/api/openapi.json` unless `API_DOCS=true`. The only diagnostics endpoint is `/api/admin/diagnostics`, behind the admin token. The `Server` header is not sent.

## Logging policy

Logs contain document IDs, counts, sizes and timings. They **never** contain query text, document text, prompts, answers, session IDs, tokens or keys. LLM provider error bodies are logged truncated (300 characters) for debugging and are never returned to clients. Setting changes log field **names**, never values.

## Known gaps

- **No accounts.** A visitor's identity is the session cookie. Whoever holds it (for example after it is stolen from the browser or used on a shared computer) can read, search and delete that session's documents until the session expires. Clearing cookies loses access to one's own documents.
- **In-process rate limiter.** Counters reset on restart and are per process; it is not suitable as the only limiter for multiple instances. Visitors behind one NAT share the per-IP limits.
- **`TRUSTED_PROXY_COUNT` on Render is unverified** (see above). If it is wrong, either all visitors share the proxy's IP limits or clients can spoof their IP.
- **DNS rebinding** after an LLM base URL is saved is not covered by the SSRF guard (unchanged).
- **Single instance only.** Sessions, the processing queue and the limiter live in one process and one data directory.
- Not implemented: TLS (use a reverse proxy or the platform's HTTPS) · malware scanning · sandboxing of the PDF parser · audit logging. See [DEPLOYMENT.md](DEPLOYMENT.md) for how to compensate at the infrastructure level.
