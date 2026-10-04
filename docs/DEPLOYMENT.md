# Deployment

DocMind runs as **one process** that serves the API (`/api`) and the built web UI (`/`) on one port. This page covers configuration, cloud hosting, storage, TLS, health checks and security. For the container itself see [DOCKER.md](DOCKER.md).

## 1. Environment variables

Set these on the host or platform (never commit them; `.env` is git- and docker-ignored):

| Variable | Why |
|---|---|
| `DOCMIND_API_TOKEN` | **Required in production** (`APP_ENV=production` refuses to start without it, or if it is shorter than 24 characters). Without it, anyone who can reach the server can read and delete all documents. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `LLM_API_KEY`, `LLM_MODEL`, `LLM_PROVIDER`, `LLM_BASE_URL` | Question answering. For OpenRouter: `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, and either a concrete model ID (most predictable) or the free router `openrouter/free` ([LLM_INTEGRATION.md](LLM_INTEGRATION.md)). |
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

## 4. Cloud hosting (single instance)

Any platform that runs a Dockerfile works: Render, Railway, Fly.io, Hugging Face Spaces (Docker), a VM. The recipe:

1. Deploy from the repository's `Dockerfile` (it builds the UI too; no separate frontend service).
2. Set the secrets from §1 in the platform's secret/environment settings.
3. Attach a **persistent volume at `/app/data`** (§5). The volume must be writable by UID 1000. If it is root-owned, `/api/health` returns 503 with "DATA_DIR … is not writable"; fix the volume's ownership or the platform's run-as-user setting.
4. Health check path: `/api/health`. Allow a start period of about 90 s (model load).
5. Exactly **one** instance; disable autoscaling (§6).
6. Memory: a **512 MB** instance is realistic. On the development machine (Windows) the API process had a working set of about 232 MB after embedding 300 chunks, with a peak of about 346 MB; Linux numbers have not been measured. Very large PDFs raise the peak, so leave headroom or use a larger instance if you process them.
7. Request timeouts: the web UI processes documents in the background (the request returns HTTP 202 immediately and the UI polls for status), so a short platform or proxy timeout does not cut off processing of a large PDF. Synchronous processing (`"background": false`, the API default) still happens inside one request and can take minutes on a small CPU.

**Free hosting.** DocMind is designed for one small always-on container with a persistent volume at `/app/data`. Platforms such as Render, Hugging Face Spaces, Koyeb, Fly.io, Railway or Google Cloud Run can run the Dockerfile; check the platform's current free tier for memory, disk and sleep rules. Free tiers commonly have ephemeral disks and sleep when idle (cold starts); in that case uploaded documents and the index are lost on restart (§5).

Platform notes (verify against the platform's current documentation):

- **Render** (Docker web service): Render sets `PORT`, which the image honours. Set the health check path to `/api/health` and add the secrets as environment variables.
- **Hugging Face Spaces** (Docker SDK): Spaces route traffic to port 7860 unless the Space's README metadata sets `app_port`. Either add the Space variable `PORT=7860`, or set `app_port: 8000`. Spaces run containers as UID 1000, which matches the image's user. Add the secrets as Space secrets.
- **Any VM** (including always-free cloud VMs): `docker compose up --build -d` with a `.env` file, behind Caddy or nginx for HTTPS (§7). This is the most reliable free option for persistence, because the disk is yours.

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
- On SIGTERM, uvicorn stops accepting connections and waits up to 30 s for in-flight requests. The background processing worker stops after the document it is working on. Every write is already on disk when its request returns, so nothing needs flushing.
- Documents still `queued` or `processing` when the process stopped are re-queued automatically on the next start (the statuses are stored in the registry).

## 9. Recovery

If `/api/health` returns 503 with an index or registry error, follow the message. Usually: stop the app, delete `DATA_DIR/index/`, start it again, and use *Process pending documents* in the UI. The registry automatically marks affected documents for re-processing ([TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

## 10. Security checklist

- [ ] `DOCMIND_API_TOKEN` set (enforced by `APP_ENV=production`); shared only with intended users
- [ ] Secrets set in the platform's secret store; `.env` never committed
- [ ] HTTPS (platform or reverse proxy)
- [ ] `DATA_DIR` on a persistent, access-restricted volume, backed up
- [ ] One instance only, ≥ 512 MB RAM (more for very large PDFs)
- [ ] If the LLM base URL is changed from the Settings page in production, it must be `https` and resolve to public IP addresses (enforced)
- [ ] Request size and rate limits at the proxy/platform; LLM provider spending limit
- [ ] `CORS_ALLOW_ORIGINS` empty unless the UI is hosted on another origin
- [ ] `API_DOCS` left off in production unless needed

More in [SECURITY.md](SECURITY.md).
