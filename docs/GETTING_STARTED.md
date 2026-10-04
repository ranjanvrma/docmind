# Getting started

## Requirements

- Python 3.11 or newer
- Node.js 22 or newer (only to build or develop the web UI)
- Disk space for the Python dependencies and the embedding model (its ONNX export is about 90 MB, downloaded on first start). No PyTorch is needed.

## 1. Backend

```bash
git clone <your-repo-url> docmind
cd docmind
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements-dev.txt      # runtime + training dependencies + pytest
# or, to only run the app:  pip install -r requirements.txt

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
python main.py api                # API on http://127.0.0.1:8000 (the embedding model loads first, a few seconds)
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

1. Open the UI and drop a PDF onto the upload panel. Try the samples in `evaluation/sample_docs/`. No sign-in is needed: your first upload creates an anonymous session (an HttpOnly cookie), and your documents are visible only in this browser.
2. Watch the pipeline (upload → extract → chunk → embed → index) and open the document when it's ready.
3. **Search**: ask in your own words, e.g. "Can I claim money for a desk?".
4. **Settings**: in development without `DOCMIND_API_TOKEN` the server settings are open; with a token set, use *Administrator sign-in* first. Add an LLM API key, click *Test connection*, then use **Ask**. Hover over the `[1]` citations to see the source passages.
5. **Settings → Evaluation lab**: run the retrieval evaluation, change the chunk size, save, re-index and run it again.

## 5. Tests

```bash
pytest                            # backend: 252 tests
cd web && npm test                # frontend: 48 tests
cd web && npm run typecheck       # TypeScript
```

## Command-line tools

```bash
python main.py ingest a.pdf b.pdf                         # index PDFs without the UI (owner-less: not shown to UI visitors)
python main.py train-classifier data/classifier/sample_training.csv   # needs requirements-train.txt
python evaluation/evaluate.py                              # retrieval evaluation
python evaluation/evaluate.py --qa                         # + answer evaluation (needs an LLM)
```
