# Docker

> **Status: unverified.** Docker was not available on the machine where this was written, so the image has never been built and the container has never been run. The configuration follows standard patterns, and the npm lockfile was checked to contain the Linux native binaries the build needs, but expect to debug the first build.

## Image (`Dockerfile`)

A two-stage build produces one image that serves the API and the UI on port 8000.

**Stage 1, `web` (`node:22-slim`)**
- `npm ci` from `web/package-lock.json`, then `npm run build` (TypeScript check + Vite build) → `web/dist`.

**Stage 2, runtime (`python:3.11-slim`)**
- No PyTorch: the embedding model runs on ONNX Runtime ([EMBEDDINGS.md](EMBEDDINGS.md)).
- `pip install -r requirements.txt` (runtime only; scikit-learn/joblib are in `requirements-train.txt`, pytest in `requirements-dev.txt`, neither is installed in the image).
- Only the four files the encoder needs are downloaded **at build time** with `hf_hub_download` (`ARG EMBEDDING_MODEL`): `onnx/model.onnx`, `tokenizer.json`, `sentence_bert_config.json`, `1_Pooling/config.json` (about 90 MB). Then `HF_HUB_OFFLINE=1`, so containers never download at startup.
- Copies `app/`, `evaluation/` (used by the Settings page's Evaluation lab), `main.py`, the sample classifier data, and `web/dist` from stage 1.
- Runs as non-root user `docmind` (UID 1000).
- `HEALTHCHECK` on `/api/health` at `$PORT` (90 s start period).
- `ENV APP_ENV=production DATA_DIR=/app/data HOST=0.0.0.0 PORT=8000`: the container **refuses to start without a `DOCMIND_API_TOKEN` of at least 24 characters**, hides the API docs, and listens on `$PORT` (override it for platforms that assign one).
- `CMD ["python", "main.py", "api"]` (exec form, so SIGTERM reaches uvicorn for a graceful shutdown; the background processing worker stops after its current document). One process only ([DEPLOYMENT.md](DEPLOYMENT.md#6-single-instance-limitation)).

`.dockerignore` keeps `.env`, virtual environments, `node_modules`, user data, tests, docs and git history out of the build context, so no secrets or uploaded documents are baked into the image.

## Compose (`docker-compose.yml`)

One service, `docmind`:
- builds the image; reads `.env` if present (`required: false`, needs Compose v2.24+);
- `DATA_DIR=/app/data` with the bind mount `./data:/app/data`;
- publishes `127.0.0.1:8000:8000`;
- `restart: unless-stopped`; the image's health check.

## Commands

```bash
cp .env.example .env                       # set DOCMIND_API_TOKEN (required), optionally LLM_API_KEY
docker compose up --build -d
docker compose ps                          # wait for "healthy"
curl http://127.0.0.1:8000/api/health
# UI: http://127.0.0.1:8000
docker compose logs -f
docker compose down                        # data stays in ./data
```

A different embedding model:

```bash
docker compose build --build-arg EMBEDDING_MODEL=<name>
# then re-process documents (the index refuses vectors from a different model)
```

The model must be a sentence-transformers model that ships `onnx/model.onnx` and uses mean or CLS pooling.

## Things to check on the first build

- `npm ci` resolves the Linux native packages (Rolldown, Tailwind oxide, LightningCSS, TypeScript 7). The lockfile lists them.
- **Linux bind-mount permissions:** the container runs as UID 1000, so make `./data` writable by it: `sudo chown -R 1000 data`.
- The image size: not measured. Without PyTorch it should be far smaller than the previous PyTorch-based design; the baked model files are about 90 MB.
- Startup: the embedding model loaded in about 3 s on the development machine (0.4 s from a warm cache); container startup time has not been measured. The health check allows 90 s.
