# DocMind

**Understand your documents, semantically.** Upload PDFs, search them by meaning, and ask questions that are answered only from the retrieved passages, with source-level citations you can inspect.

DocMind is a retrieval-augmented generation (RAG) application built from first principles: PyMuPDF → chunking → sentence-transformer embeddings → FAISS → prompt → LLM → citation validation, with no orchestration framework hiding the steps. A React interface (glass, motion, a small 3D scene) sits on a FastAPI backend that also serves it.

> **Status:** portfolio project with production-minded engineering: access token, request and page limits, crash recovery, prompt-injection mitigations, runtime settings, an evaluation lab, and 221 automated tests (187 backend, 34 frontend). Question answering has been checked end to end against a live LLM (OpenRouter) on a handful of questions. **Not yet exercised:** the Docker build. See [Limitations](#limitations).

---

## What it does

| | |
|---|---|
| **Upload & index** | Drag-and-drop PDFs with real upload progress. Page-by-page extraction, cleaning, sentence-aware chunking that never crosses pages, embeddings, a FAISS index. Duplicates are detected by content hash; scanned, encrypted and oversized files fail with clear reasons. |
| **Semantic search** | Find passages by meaning (Ctrl/⌘ K). Results show document, page and a *similarity* score, clearly not an "accuracy". |
| **Ask (RAG)** | Answers generated only from the top retrieved passages. Each `[n]` is an interactive chip showing the passage; invalid citation numbers are flagged; "not found" is a first-class answer. |
| **Settings & evaluation lab** | Change the LLM provider, model, key (write-only) and effort, and test the connection. Tune chunk size and overlap with a live diagram, re-index in one click, and measure retrieval Hit@K / MRR on a demo dataset to compare settings. Applied instantly, no restart. |
| **Document classification** | Zero-shot categories from embeddings (labels editable); optional supervised model. Demo feature; no measured accuracy. |

## Architecture

```
Browser ─▶ React SPA (web/) ──/api──▶ FastAPI (app/api.py) ─▶ DocMindService (app/service.py)
                                                                   │
  PDF → ingestion → preprocessing → chunking → embeddings → FAISS ─┤
  question → embed → top-k → numbered, sanitised context → LLM → answer → citation check
```

One process serves the API (`/api`) and the built UI (`/`). Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

**AI pipeline:** Python 3.11, PyMuPDF, sentence-transformers (`all-MiniLM-L6-v2`, used as-is), FAISS (`IndexFlatIP`), NumPy, pandas, scikit-learn, the Anthropic SDK / OpenAI-compatible HTTP.
**Backend:** FastAPI, Pydantic, Uvicorn.
**Frontend:** React 19 + TypeScript, Vite, Tailwind CSS v4, Radix primitives (shadcn-style components), Motion, React Three Fiber, TanStack Query, Lucide.
**Tooling:** pytest, Vitest + Testing Library, Docker (multi-stage, unverified).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
cp .env.example .env
cd web && npm install && npm run build && cd ..
python main.py api                                     # http://127.0.0.1:8000
```

For UI development with hot reload, run `python main.py api` and `cd web && npm run dev` (http://localhost:5173). Full guide: [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

Question answering needs an LLM key: paste it in **Settings → Model** (stored server-side, never shown again) or set `LLM_API_KEY` in `.env`.

## Tests

```bash
pytest                                  # 187 backend tests
cd web && npm test && npm run typecheck # 34 frontend tests + types
python evaluation/evaluate.py           # retrieval metrics on the demo dataset
```

## Documentation

| | |
|---|---|
| Run & operate | [Getting started](docs/GETTING_STARTED.md) · [Configuration](docs/CONFIGURATION.md) · [Deployment](docs/DEPLOYMENT.md) · [Docker](docs/DOCKER.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) |
| How it works | [Architecture](docs/ARCHITECTURE.md) · [RAG pipeline](docs/RAG_PIPELINE.md) · [Embeddings](docs/EMBEDDINGS.md) · [Vector search](docs/VECTOR_SEARCH.md) · [Retrieval](docs/RETRIEVAL.md) · [Prompting](docs/PROMPTING.md) · [LLM integration](docs/LLM_INTEGRATION.md) · [Citations](docs/CITATIONS.md) |
| Quality & safety | [Evaluation](docs/EVALUATION.md) · [Security](docs/SECURITY.md) |
| Interface | [Frontend](docs/FRONTEND.md) · [Design system](docs/DESIGN_SYSTEM.md) |
| Reference | [HTTP API](docs/API.md) · [Contributing](docs/CONTRIBUTING.md) · [Project guide](PROJECT_GUIDE.md) |

## Measured results (demo dataset only)

Retrieval on 20 hand-written questions over 3 short fictional PDFs, written by the same author. These numbers are useful for **comparing settings**, not as evidence of real-world quality ([docs/EVALUATION.md](docs/EVALUATION.md)).

| Chunk size / overlap | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| 800 / 150 (default) | 0.70 | 0.95 | 1.00 | 0.838 |
| 600 / 150 | 0.85 | 1.00 | 1.00 | 0.92 |

Answer quality has **not** been measured: the QA evaluation (`python evaluation/evaluate.py --qa`) has not been run. A manual live check with OpenRouter (`nvidia/nemotron-3-super-120b-a12b:free`) answered factual questions with correct page citations and abstained on unanswerable ones, but that is a spot check, not a metric.

## Limitations

- Live LLM: spot-checked with one OpenRouter model only; the Anthropic provider has not been run live. The Docker image has never been built.
- Storage is a local directory (`DATA_DIR`): cloud deployments need a persistent volume or every restart starts empty ([docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#5-persistent-storage-what-must-survive-a-restart)).
- No OCR (scanned PDFs fail clearly); tables and multi-column layouts become plain text; chunks never cross pages.
- Dense retrieval only (no BM25, no re-ranker); small English-focused embedding model.
- Grounding is instructed and citation *numbers* are verified; whether a cited passage supports its claim is not.
- Prompt injection from document text is mitigated, not solved.
- Single process and a shared access token: no per-user accounts and no rate limiting. Put it behind a reverse proxy with TLS.

## Screenshots

> Add your own to `docs/screenshots/`: home (hero + upload), search results, an answer with an open citation, and the Settings evaluation lab.

## Author

**Your Name**: B.Tech Artificial Intelligence & Machine Learning
GitHub · LinkedIn · Email
