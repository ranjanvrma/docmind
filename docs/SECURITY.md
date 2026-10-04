# Security

DocMind is designed for a single trusted team or individual. It has a shared access token, not per-user accounts. This page lists what is protected, how, and what is not.

## API token authentication

- Set `DOCMIND_API_TOKEN` (environment only). Every `/api/*` endpoint except `/api/health` then requires `X-API-Key: <token>` or `Authorization: Bearer <token>`; anything else gets `401`.
- The comparison uses `secrets.compare_digest` (constant time).
- `/api/health` stays public so probes can reach it; it reveals only whether a token is required, never the token.
- **The web UI never contains the token.** When the server requires one, the UI asks the user and keeps it in `sessionStorage` (or `localStorage` if they tick "Remember on this device"). A scan of the production bundle found no secret-like strings, only the header name.
- Without a token, anyone who can reach the server has full access. The API logs a warning at startup.

## CORS

Off by default. The bundled UI is served from the same origin, so it needs no CORS. `CORS_ALLOW_ORIGINS` (environment only) enables it for explicitly listed origins, for GET/POST/PATCH/DELETE, without credentials. Wildcards and malformed origins are rejected at startup.

## Upload limits

| Check | Where | Result |
|---|---|---|
| Whole request size (`MAX_REQUEST_MB`) from `Content-Length`, **before reading the body** | `UploadSizeLimitMiddleware` | 413 |
| Missing `Content-Length` on upload | same | 411 |
| ≤ 20 files per request | upload route | 400 |
| Per-file size (`MAX_UPLOAD_MB`), `.pdf` extension, `%PDF-` magic bytes | `ingestion.validate_pdf_upload` | file rejected |
| Page count (`MAX_PAGES`), encrypted PDFs, unparseable PDFs | `ingestion.extract_pages` | document marked failed |

Files are stored as `<sha256-prefix>.pdf`; user-supplied names are sanitised and used for display only, so path traversal via filenames is impossible. Document IDs in URLs are looked up in the registry before any path is built. PDFs are parsed, never executed. The PDF parser (MuPDF, C code) runs in-process without a sandbox.

## Prompt injection and untrusted document text

Document text reaches the LLM. Mitigations are described in [PROMPTING.md](PROMPTING.md#prompt-injection-hardening): an untrusted-source rule in the system prompt, removal of `<sources>` delimiters and `[Source n]` headers from document text, and a plain-text answer instruction. **Mitigated, not solved**: a malicious document can still try to influence an answer's content.

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
- **The environment's LLM key is bound to the environment's endpoint.** Changing the provider or base URL from the Settings page withholds that key until a key for the new endpoint is entered, so a token holder cannot point the server at their own host and capture the key.
- `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key` and `*.log` are git- and docker-ignored. The web bundle can only contain `VITE_*` variables, and the only one used (`VITE_API_BASE_URL`) is a public URL.

## Production profile

`APP_ENV=production` (the Docker image's default) refuses to start without `DOCMIND_API_TOKEN` and turns off `/api/docs` and `/api/openapi.json` unless `API_DOCS=true`. There are no debug endpoints. The `Server` header is not sent.

## Logging policy

Logs contain document IDs, counts, sizes and timings. They **never** contain query text, document text, prompts, answers, tokens or keys. LLM provider error bodies are logged truncated (300 characters) for debugging and are not returned to clients. Setting changes log field **names**, never values.

## Not implemented

Rate limiting · per-user accounts and permissions · TLS (use a reverse proxy) · malware scanning · sandboxing of the PDF parser · audit logging. See [DEPLOYMENT.md](DEPLOYMENT.md) for how to compensate at the infrastructure level.
