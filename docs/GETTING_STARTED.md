# Getting started

## Requirements

- Python 3.11 or newer
- Node.js 22 or newer (only to build or develop the web UI)
- About 1.5 GB of disk space (PyTorch, which sentence-transformers needs, plus the embedding model)

## 1. Backend

```bash
git clone <your-repo-url> docmind
cd docmind
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

# On machines without an NVIDIA GPU, install the small CPU-only PyTorch first:
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt      # runtime dependencies + pytest

cp .env.example .env                     # Windows: copy .env.example .env
```

Everything works without editing `.env`, except question answering, which needs an LLM. You can configure the LLM later from the **Settings** page or in `.env` ([CONFIGURATION.md](CONFIGURATION.md)).

## 2. Web UI

```bash
cd web
npm install
cd ..
```

## 3. Run

**Option A, development** (hot reload for UI changes). Use two terminals:

```bash
python main.py api                # API on http://127.0.0.1:8000 (the embedding model loads first, ~5-15 s)
```

```bash
cd web && npm run dev             # UI on http://localhost:5173 (proxies /api to port 8000)
```

**Option B, production-style** (one process):

```bash
cd web && npm run build && cd ..  # creates web/dist
python main.py api                # serves the UI and the API on http://127.0.0.1:8000
```

## 4. Try it

1. Open the UI and drop a PDF onto the upload panel. Try the samples in `evaluation/sample_docs/`.
2. Watch the pipeline (upload → extract → chunk → embed → index) and open the document when it's ready.
3. **Search**: ask in your own words, e.g. "Can I claim money for a desk?".
4. **Settings**: add an LLM API key, click *Test connection*, then use **Ask**. Hover over the `[1]` citations to see the source passages.
5. **Settings → Evaluation lab**: run the retrieval evaluation, change the chunk size, save, re-index and run it again.

## 5. Tests

```bash
pytest                            # backend: 181 tests
cd web && npm test                # frontend: 34 tests
cd web && npm run typecheck       # TypeScript
```

## Command-line tools

```bash
python main.py ingest a.pdf b.pdf                         # index PDFs without the UI
python main.py train-classifier data/classifier/sample_training.csv
python evaluation/evaluate.py                              # retrieval evaluation
python evaluation/evaluate.py --qa                         # + answer evaluation (needs an LLM)
```
