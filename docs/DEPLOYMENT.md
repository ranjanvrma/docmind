# Deployment

DocMind runs as **one process** that serves the API (`/api`) and the built web UI (`/`) on one port. This page covers configuration, cloud hosting, storage, TLS, health checks and security. For the container itself see [DOCKER.md](DOCKER.md).

## 1. Environment variables

Set these on the host or platform (never commit them; `.env` is git- and docker-ignored):

| Variable | Why |
|---|---|
| `DOCMIND_API_TOKEN` | **Required in production** (`APP_ENV=production` refuses to start without it). Without it, anyone who can reach the server can read and delete all documents. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `LLM_API_KEY`, `LLM_MODEL`, `LLM_PROVIDER`, `LLM_BASE_URL` | Question answering. For OpenRouter: `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, and a **concrete** model ID (not a router like `openrouter/free`). |
| `DATA_DIR` | Must point at **persistent** storage (see §5). `/app/data` in the image. |
| `APP_ENV` | `production` in the Docker image; `development` otherwise. |
| `PORT` | Set by most platforms; the app listens on it. |

Everything else has working defaults ([CONFIGURATION.md](CONFIGURATION.md)). No URL in the app or the UI points at `localhost`: the built UI calls `/api` on its own origin.

## 2. Local deployment (no Docker)

```bash
cd web && npm ci && npm run build && cd ..
python main.py api                       # serves UI + API on 127.0.0.1:8000
```

`HOST=0.0.0.0` (or `--host 0.0.0.0`) only together with `DOCMIND_API_TOKEN` and, ideally, a reverse proxy.

## 3. Docker / Docker Compose

```bash
cp .env.example .env    # set DOCMIND_API_TOKEN (+ LLM_* values)
docker compose up --build -d
```

The compose file publishes port 8000 on `127.0.0.1` only and mounts `./data`. Details: [DOCKER.md](DOCKER.md).

## 4. Cloud hosting (single-instance demo)

Any platform that runs a Dockerfile works: Render, Railway, Fly.io, Hugging Face Spaces (Docker), a VM. The recipe:

1. Deploy from the repository's `Dockerfile` (it builds the UI too; no separate frontend service).
2. Set the secrets from §1 in the platform's secret/environment settings.
3. Attach a **persistent volume at `/app/data`** (§5). The volume must be writable by UID 1000. If it is root-owned, `/api/health` returns 503 with "DATA_DIR … is not writable"; fix the volume's ownership or the platform's run-as-user setting.
4. Health check path: `/api/health`. Allow a start period of about 90 s (model load).
5. Exactly **one** instance; disable autoscaling (§6).
6. Give the service roughly **1 GB of RAM or more**. The API process used about 600 MB resident on the development machine (PyTorch + the embedding model); 512 MB instances are likely to run out of memory.
7. Raise the platform's request timeout if it is short: processing a large PDF happens inside one request and can take minutes on a small CPU.

**Separately hosted UI (optional).** The default and recommended setup serves the UI from the API (same origin, no CORS). If you host `web/dist` elsewhere, build it with `VITE_API_BASE_URL=https://<api-host>` and set `CORS_ALLOW_ORIGINS=https://<ui-host>` on the API. The CSP for that page is then the static host's responsibility.

## 5. Persistent storage: what must survive a restart

Do not assume the container filesystem is persistent. On most platforms it is reset on every deploy and restart.

| Data | Location | If lost |
|---|---|---|
| Uploaded PDFs | `DATA_DIR/raw/` | Documents are gone; they cannot be re-processed |
| Document registry (metadata, status, classification) | `DATA_DIR/processed/documents.json` | The app forgets every document |
| FAISS index + chunk metadata | `DATA_DIR/index/` | Search and Q&A return nothing; with the PDFs still present, *Process pending documents* rebuilds it |
| Settings saved from the UI (may include an LLM key) | `DATA_DIR/settings.json` | Falls back to environment values |
| Trained classifier (optional) | `DATA_DIR/classifier/` | Falls back to zero-shot |

All of these live under one directory, so **one volume at `DATA_DIR` is enough**. Writes are atomic (temp file + rename) and the index is saved before the registry commits, so a crash cannot leave them inconsistent; startup reconciles the two if needed.

**Without a persistent volume** (for example a free tier with an ephemeral disk) the app still runs, but every restart, redeploy or idle spin-down starts with an empty library. That is acceptable only for a throwaway demo; say so to anyone you share it with. Object storage (S3, GCS) is **not** a drop-in replacement: FAISS and the registry need a POSIX filesystem with atomic renames, so a FUSE-mounted bucket is not recommended.

Back up the whole `DATA_DIR`, ideally while the app is stopped. Restrict access to it: it contains your documents and possibly a key.

## 6. Single-instance limitation

The FAISS index and the write locks live in process memory. Run **exactly one** process and one replica. Multiple workers or replicas would each hold their own copy of the index and overwrite each other's files. Scaling out would require a shared vector database and a job queue, which DocMind does not have.

## 7. Reverse proxy and HTTPS

Cloud platforms terminate TLS for you. On your own server, do not expose the app directly; put a reverse proxy in front, for example Caddy:

```
docmind.example.com {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 110MB          # a little above MAX_REQUEST_MB
    }
}
```

With nginx, set `client_max_body_size` similarly and long enough `proxy_read_timeout` values.

**Rate limiting:** DocMind has none. Every `/api/ask` call costs LLM credits, so limit requests at the proxy or platform and set a spending cap in your LLM provider's console.

## 8. Health checks, startup and shutdown

- `GET /api/health` (public) returns `200` when the app is ready (model loaded, index usable) and `503` with an explanation when stored data could not be loaded or `DATA_DIR` is not writable. It reveals no secrets.
- A configuration error (for example `APP_ENV=production` without a token, or an invalid `CORS_ALLOW_ORIGINS` entry) stops startup with a one-line `Configuration error: …` message.
- On SIGTERM, uvicorn stops accepting connections and waits up to 30 s for in-flight requests. Every write is already on disk when its request returns, so nothing needs flushing.

## 9. Recovery

If `/api/health` returns 503 with an index or registry error, follow the message. Usually: stop the app, delete `DATA_DIR/index/`, start it again, and use *Process pending documents* in the UI. The registry automatically marks affected documents for re-processing ([TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

## 10. Security checklist

- [ ] `DOCMIND_API_TOKEN` set (enforced by `APP_ENV=production`); shared only with intended users
- [ ] Secrets set in the platform's secret store; `.env` never committed
- [ ] HTTPS (platform or reverse proxy)
- [ ] `DATA_DIR` on a persistent, access-restricted volume, backed up
- [ ] One instance only, ≥ 1 GB RAM
- [ ] Request size and rate limits at the proxy/platform; LLM provider spending limit
- [ ] `CORS_ALLOW_ORIGINS` empty unless the UI is hosted on another origin
- [ ] `API_DOCS` left off in production unless needed

More in [SECURITY.md](SECURITY.md).
