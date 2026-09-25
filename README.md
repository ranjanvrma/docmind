# DocMind

**Semantic search, grounded question answering and document classification over your own PDFs.**

DocMind is a local document intelligence app. You upload PDFs; it extracts and cleans the text, splits it into chunks, embeds them with a sentence-transformer model and indexes them in FAISS. You can then search the documents by meaning, ask questions that an LLM answers *only from the retrieved passages* (with page-level citations), and see an automatic category for each document.

The retrieval-augmented generation (RAG) pipeline is implemented directly in Python (PyMuPDF → chunking → sentence-transformers → FAISS → prompt → LLM) rather than hidden behind a framework, so each step can be read, tested and explained.

> Status: a working portfolio / learning project. It runs locally and is tested, but it is **not production-ready** (see [Limitations](#limitations)).

---

## Table of contents

1. [Problem statement](#problem-statement)
2. [Overview](#overview)
3. [Features](#features)
4. [Architecture](#architecture)
5. [Technology stack](#technology-stack)
6. [Project structure](#project-structure)
7. [Installation](#installation)
8. [Environment variables](#environment-variables)
9. [Running locally](#running-locally)
10. [Using the application](#using-the-application)
11. [API endpoints](#api-endpoints)
12. [Evaluation methodology](#evaluation-methodology)
13. [Sample results](#sample-results)
14. [Limitations](#limitations)
15. [Future improvements](#future-improvements)
16. [Screenshots](#screenshots)
17. [Author](#author)

---

## Problem statement

Useful information is often locked inside long PDFs: reports, policies, papers, lecture notes. Keyword search (Ctrl+F) fails when the reader's wording differs from the document's ("get my money back" vs "refund"). Asking a general-purpose chatbot is worse: it has never seen your documents and may confidently invent an answer.

DocMind addresses both problems. It finds passages by *meaning*, and when it generates an answer it is constrained to the retrieved passages and must show which document and page each claim came from, so the user can check it.

## Overview

Four related but different techniques are used. It helps to keep them separate:

| Concept | What it does in DocMind | Needs an LLM? |
|---|---|---|
| **Semantic search** | Turns the query and every chunk into embedding vectors and ranks chunks by cosine similarity, so matches are found by meaning rather than exact words. This is the "Semantic search" tab and `POST /search`. | No |
| **Retrieval** | The general step of selecting the top-k most relevant chunks for a query. Semantic search *is* a retrieval method; in RAG, retrieval is the first stage whose output becomes the LLM's context. | No |
| **RAG** (retrieval-augmented generation) | Retrieval + generation: the top-k chunks are placed in a prompt, and an LLM writes an answer using only that context, citing numbered sources. The "Ask a question" tab and `POST /ask`. | Yes |
| **Document classification** | Assigns a whole document to a category (Research Paper, Report, Assignment, Notes, Policy, Other) from its mean embedding, using a trained logistic regression or a zero-shot similarity fallback. | No |

## Features

- **PDF ingestion**: multi-file upload, page-by-page extraction with PyMuPDF, content-hash document IDs (duplicate uploads are detected even under a different filename), detection of empty or image-only pages, clear errors for malformed, encrypted or non-PDF files.
- **Conservative preprocessing**: Unicode/ligature normalisation, rejoining of words hyphenated across lines, merging of layout-wrapped lines into paragraphs, removal of page-number lines and repeated headers/footers. Punctuation, numbers and case are preserved.
- **Deterministic, sentence-aware chunking** with configurable size and overlap. Chunks never cross a page boundary, so every citation points to one exact page.
- **Embeddings** with any sentence-transformers model (default `all-MiniLM-L6-v2`), L2-normalised so inner product = cosine similarity. The model is loaded once per process, and processed documents are never re-embedded.
- **FAISS vector store** (`IndexFlatIP` + `IndexIDMap2`) with JSON metadata, atomic saves, and a manifest that detects index/metadata drift or a changed embedding model on load.
- **Semantic search** with configurable top-k and optional per-document filtering.
- **RAG question answering** with a grounding-focused system prompt, a bounded context budget, a fixed abstention sentence, and **citation verification**: sources shown are exactly the chunks sent to the LLM, and citations to source numbers that were never provided are flagged, not displayed as real.
- **Provider-agnostic LLM layer**: Anthropic (official SDK) or any OpenAI-compatible endpoint (OpenAI, Groq, OpenRouter, local Ollama), selected by environment variables.
- **Document classification**: zero-shot by default; supervised logistic regression on embeddings once you train it (`python main.py train-classifier`), with cross-validated metrics reported at training time.
- **FastAPI backend** with Pydantic request/response models and proper status codes (400/404/422/502/503).
- **Streamlit frontend** that talks to the API over HTTP.
- **Evaluation framework**: Hit@K, Precision@K, Recall@K and MRR for retrieval, plus token-F1, abstention and citation checks for QA.
- **100 unit/integration tests**, Docker image and docker-compose setup.

## Architecture

```
                       ┌──────────────────────────────┐
  Browser ──────────▶  │ Streamlit UI (frontend/)     │   no ML code; HTTP calls only
                       └──────────────┬───────────────┘
                                      │ JSON over HTTP (requests)
                       ┌──────────────▼───────────────┐
                       │ FastAPI (app/api.py)         │   validation, status codes
                       └──────────────┬───────────────┘
                                      │ Python calls
                       ┌──────────────▼───────────────┐
                       │ DocMindService (service.py)  │   orchestrates the pipeline
                       └──┬──────────┬──────────┬─────┘
       ingestion pipeline │          │ query    │ QA
                          ▼          ▼          ▼
  PDF bytes ─▶ ingestion ─▶ preprocessing ─▶ chunking ─▶ embeddings ─▶ FAISS vector store
               (PyMuPDF)     (clean text)    (chunks +     (sentence-     (index + metadata
                                             metadata)      transformers)  on disk)
                                                                  │
                          classifier ◀── mean chunk embedding ────┘
                          (LogReg / zero-shot)

  question ─▶ embed query ─▶ FAISS top-k ─▶ build numbered context ─▶ LLM ─▶ answer
                                                  (prompts.py)       (llm.py)   + verified citations (qa.py)
```

**Upload + process:** `POST /documents/upload` validates the file (extension, `%PDF` magic bytes, size), hashes it to get a document ID, and stores it as `data/raw/<doc_id>.pdf` (never under the user's filename). `POST /documents/process` extracts pages, cleans them, chunks them, embeds all chunks in batches, adds them to FAISS, classifies the document from the mean of its chunk embeddings, then saves the index and the document registry.

**Search:** the query is embedded with the same model, FAISS returns the top-k chunks by inner product (= cosine similarity), and the chunk metadata supplies document name and page.

**Ask:** the same retrieval runs; the top-k chunks are formatted as `[Source n] (document, page)` blocks within a character budget, sent to the LLM with a strict grounding prompt, and the `[n]` citations in the reply are parsed and checked against the sources actually provided.

## Technology stack

| Technology | Used for | Why |
|---|---|---|
| Python 3.11 | Everything | Standard for ML work. |
| PyMuPDF | PDF text extraction | Fast, robust to messy PDFs, gives per-page text and reading-order sorting. |
| sentence-transformers | Embeddings | Pretrained models tuned for semantic similarity; one-line batch encoding. |
| FAISS (`faiss-cpu`) | Vector search | Efficient exact (and optionally approximate) nearest-neighbour search; runs locally with no server. |
| NumPy | Vector maths | Normalisation, mean pooling, similarity matrices. |
| Pandas | Evaluation and training data | Per-query metric tables, CSV loading/cleaning for the classifier. |
| scikit-learn | Classification | Logistic regression, stratified k-fold cross-validation, metrics. |
| Anthropic SDK / httpx | LLM calls | Official SDK for Anthropic; plain HTTP for any OpenAI-compatible API. |
| FastAPI + Pydantic + Uvicorn | Backend API | Typed request/response validation, automatic OpenAPI docs at `/docs`. |
| Streamlit | Frontend | A functional UI in one Python file. |
| pytest | Tests | Fixtures, parametrisation, FastAPI `TestClient`. |
| Docker / docker-compose | Packaging | Reproducible environment; compose runs the API and UI as two services. |

Not used, on purpose: **LangChain / LlamaIndex** (the pipeline is short enough to write directly, and writing it is the point), and **a database** (a JSON registry and a FAISS file are enough for a single-user local app).

## Project structure

```
docmind/
├── app/
│   ├── config.py          # Settings from environment variables (.env)
│   ├── models.py          # Domain dataclasses + Pydantic API schemas
│   ├── ingestion.py       # Upload validation, PyMuPDF page extraction
│   ├── preprocessing.py   # Text cleaning, header/footer removal
│   ├── chunking.py        # Sentence-aware chunking with overlap
│   ├── embeddings.py      # sentence-transformers wrapper (cached, normalised)
│   ├── vector_store.py    # FAISS index + metadata persistence
│   ├── retrieval.py       # query -> embedding -> top-k chunks
│   ├── prompts.py         # System prompt, context construction
│   ├── llm.py             # LLM provider abstraction (Anthropic / OpenAI-compatible)
│   ├── qa.py              # RAG answer generation + citation verification
│   ├── classifier.py      # Zero-shot and supervised document classification
│   ├── registry.py        # JSON registry of documents and processing status
│   ├── service.py         # DocMindService: orchestrates the whole pipeline
│   ├── api.py             # FastAPI routes
│   └── utils.py           # Logging, hashing, safe filenames, atomic writes
├── frontend/streamlit_app.py
├── data/
│   ├── raw/               # uploaded PDFs, stored as <doc_id>.pdf   (git-ignored)
│   ├── processed/         # documents.json registry                  (git-ignored)
│   ├── index/             # index.faiss, metadata.json, manifest.json (git-ignored)
│   └── classifier/        # sample_training.csv (synthetic) + trained model
├── evaluation/
│   ├── datasets/sample_eval.json   # SAMPLE labelled queries + QA items
│   ├── make_sample_docs.py         # generates the 3 fictional sample PDFs
│   ├── sample_docs/                # generated PDFs
│   └── evaluate.py                 # retrieval + QA metrics
├── tests/                 # 100 pytest tests
├── notebooks/pipeline_walkthrough.ipynb
├── main.py                # CLI: api | ui | ingest | train-classifier
├── Dockerfile, docker-compose.yml, .dockerignore
├── requirements.txt, pytest.ini, .env.example, .gitignore
├── README.md
└── PROJECT_GUIDE.md       # in-depth explanation for interview preparation
```

## Installation

Requirements: Python 3.11 or newer, about 1.5 GB of disk space (PyTorch CPU and the models).

```bash
git clone <your-repo-url> docmind
cd docmind
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

# Optional but recommended: install the CPU-only PyTorch build first (much smaller download)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
```

The embedding model (~90 MB) downloads automatically the first time the API starts.

## Environment variables

All configuration lives in `.env` (git-ignored). See `.env.example` for the full list.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic`, or `openai` for any OpenAI-compatible API |
| `LLM_API_KEY` | *(empty)* | **Required only for Q&A.** Without it, search and classification still work and `/ask` returns 503. |
| `LLM_MODEL` | `claude-opus-5` | Model name for the chosen provider |
| `LLM_BASE_URL` | *(empty)* | For OpenAI-compatible providers other than OpenAI, e.g. `https://api.groq.com/openai/v1` or `http://localhost:11434/v1` (Ollama) |
| `LLM_MAX_TOKENS` | `4096` | Maximum response length |
| `MAX_CONTEXT_CHARS` | `6000` | Maximum retrieved text sent to the LLM per question |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Any sentence-transformers model. Changing it requires re-indexing. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `150` | Characters per chunk / characters of overlap |
| `TOP_K` | `5` | Default number of chunks retrieved (1–20) |
| `MAX_UPLOAD_MB` | `25` | Upload size limit |
| `CLASSIFIER_LABELS` | `Research Paper,Report,Assignment,Notes,Policy,Other` | Comma-separated categories |
| `DOCMIND_API_URL` | `http://127.0.0.1:8000` | Where the Streamlit UI finds the API |

## Running locally

Start the API and the UI in two terminals (virtual environment activated):

```bash
python main.py api          # FastAPI on http://127.0.0.1:8000  (interactive docs: /docs)
python main.py ui           # Streamlit on http://localhost:8501
```

Equivalent direct commands: `uvicorn app.api:app --reload` and `streamlit run frontend/streamlit_app.py`.

Other commands:

```bash
python main.py ingest path/to/a.pdf path/to/b.pdf    # index PDFs without the UI
python main.py train-classifier data/classifier/sample_training.csv
python evaluation/evaluate.py                        # retrieval evaluation
python evaluation/evaluate.py --qa                   # + answer evaluation (needs LLM_API_KEY)
pytest                                               # run the test suite
```

### Docker

```bash
cp .env.example .env         # compose reads it; fill in LLM_API_KEY if you want Q&A
docker compose up --build    # API on :8000, UI on :8501, data persisted in ./data
```

Or just the API: `docker build -t docmind . && docker run -p 8000:8000 --env-file .env -v "$(pwd)/data:/app/data" docmind`.

The image is CPU-only and bakes in the default embedding model.

## Using the application

1. Open http://localhost:8501. The sidebar shows whether the API is reachable and whether an LLM is configured.
2. **Upload & process**: choose one or more PDFs and click *Upload & process*. Each file is reported as uploaded, duplicate or rejected (with the reason), then indexed. Warnings appear for pages with no extractable text.
3. **Semantic search**: type a query. Each result shows document, page and cosine score; expand it to read the passage.
4. **Ask a question**: the answer appears with numbered citations. Below it, *Sources* lists exactly the passages the LLM received, with the cited ones first. Warnings appear if the model cited a source number that does not exist or did not ground its answer.
5. **Documents & classification**: a table of all documents with status, page and chunk counts, and predicted category. Select a document to see its per-category scores, warnings, or to delete it.
6. Sidebar: set **top-k** and optionally restrict search/Q&A to selected documents.

## API endpoints

Interactive documentation is available at http://127.0.0.1:8000/docs.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | | status, model names, whether an LLM is configured, document/chunk counts |
| POST | `/documents/upload` | multipart `files` (1–20 PDFs) | per-file `uploaded` / `duplicate` / `rejected`; 201, or 400 if every file is rejected |
| POST | `/documents/process` | `{"doc_ids": [...]?, "force": false}` | per-document status and chunk count; 404 for unknown IDs |
| GET | `/documents` | | all documents with status, pages, empty pages, chunks, classification |
| GET | `/documents/{doc_id}` | | one document; 404 if unknown |
| DELETE | `/documents/{doc_id}` | | 204; removes vectors, registry entry and stored file |
| POST | `/search` | `{"query": "...", "top_k": 5, "doc_ids": [...]?}` | ranked chunks with score, document, page, text; 422 on blank query or top_k outside 1–20 |
| POST | `/ask` | `{"question": "...", "top_k": 5, "doc_ids": [...]?}` | answer, sources (with `cited` flags), `invalid_citations`, `answered_from_documents`; 503 if no LLM is configured, 502 if the LLM call fails |

Example:

```bash
curl -F "files=@report.pdf" http://127.0.0.1:8000/documents/upload
curl -X POST http://127.0.0.1:8000/documents/process -H "Content-Type: application/json" -d "{}"
curl -X POST http://127.0.0.1:8000/search -H "Content-Type: application/json" -d '{"query": "main risks", "top_k": 3}'
```

## Evaluation methodology

A system that produces fluent answers is not necessarily a good one, so DocMind ships with an evaluation script (`evaluation/evaluate.py`) and a labelled dataset format.

**Dataset** (`evaluation/datasets/sample_eval.json`): each retrieval item has a query and the `(document, page)` pairs that contain the answer. QA items add a reference answer, and some are deliberately unanswerable. Relevance is labelled at page level because page labels stay valid when chunk size or overlap changes; chunk IDs would not. (Items may also give `relevant_chunk_ids` for chunk-level labels.)

**Procedure:** the script indexes the dataset's PDFs into a temporary directory using the same pipeline and `.env` settings as the app, runs every query, and writes per-query CSVs and a `summary.json` to `evaluation/results/`.

**Retrieval metrics** (averaged over queries, where "relevant" means the chunk comes from a labelled page):

- **Hit@K**: 1 if any relevant chunk is in the top K.
- **Precision@K**: relevant chunks in top K ÷ K.
- **Recall@K**: distinct relevant pages found in top K ÷ number of relevant pages.
- **MRR**: mean of 1 / rank of the first relevant chunk.

**QA metrics** (`--qa`, requires an LLM):

- **Token F1** against the reference answer (SQuAD-style). A crude lexical measure: it rewards shared words and cannot judge paraphrases or factual correctness.
- **Correct-abstention rate** on unanswerable questions and **false-abstention rate** on answerable ones.
- **Context recall**: whether a relevant page reached the prompt at all. This separates retrieval failures from generation failures.
- **Citation precision**: the fraction of cited sources that come from a relevant page.
- **Invalid citations**: citations to source numbers that were never provided.

## Sample results

> **Read this first.** The numbers below were **measured** by running `python evaluation/evaluate.py` on this repository's **sample/demo dataset**: 20 queries over 3 short fictional PDFs (9 pages, 11 chunks) that were written by the project author along with the queries. That makes them optimistic and statistically meaningless as a measure of real-world quality. They are included to show what the evaluation produces and to serve as a regression baseline, **not** as a performance claim.

Configuration: `all-MiniLM-L6-v2`, `CHUNK_SIZE=800`, `CHUNK_OVERLAP=150`.

| K | Hit rate | Precision@K | Recall@K |
|---|---|---|---|
| 1 | 0.70 | 0.70 | 0.675 |
| 3 | 0.95 | 0.35 | 0.95 |
| 5 | 1.00 | 0.24 | 1.00 |

MRR@5 = 0.838.

**How to read this:** Precision@K falls as K grows because most queries have only one relevant page among 11 chunks. With K=5, at least four results *must* be irrelevant, so low precision here is expected and not a defect.

**Qualitative observations** (from reading `retrieval_per_query.csv`, not measured):

- All 6 rank-1 misses still found the right page at rank 2–4. Most are vocabulary mismatches the small model does not bridge well: "need to be *online*" vs the document's "must be *reachable*", "*memorising* the training set" vs "*overfits*".
- Introductory chunks that repeat the document's title and topic (e.g. page 1 of the policy) tend to rank high for generic queries about that document.
- Classification of the three sample PDFs: **zero-shot** labelled all three correctly, but "Policy" beat "Report" for the policy document by only 0.001 in cosine similarity, which is not a robust margin. The **supervised** model trained on the 48 synthetic examples mislabelled the ML lecture notes as "Research Paper", probably because the ML *topic* resembled the research-paper training texts more than the *form* resembled notes.
- Supervised classifier, 5-fold cross-validation on the 48 synthetic training texts: accuracy 0.81, macro-F1 0.81. This is measured, but on tiny, hand-written, clean data, so it says little about real documents.
- **QA has not been evaluated** in this repository. Running `--qa` requires an API key and produces `qa_per_question.csv`; no QA numbers are claimed here.

To evaluate properly, build a dataset from real documents with queries written by someone who did not write the documents, ideally 100+ queries, and compare configurations (chunk size, model, top-k) on it.

## Limitations

- **No OCR.** Scanned or image-only PDFs yield no text; they are flagged and marked failed.
- **Layout.** Tables, multi-column layouts, footnotes and equations are extracted as plain text in approximate reading order; table structure is lost.
- **Page-bounded chunks.** A passage that continues across a page break is split into two chunks.
- **Embedding model.** `all-MiniLM-L6-v2` is small and English-focused, and it truncates inputs at 256 word-pieces. Multilingual or domain-specific documents need another model.
- **Pure dense retrieval.** There is no keyword/BM25 component, so exact identifiers (codes, names, numbers) may be retrieved worse than by keyword search. There is no re-ranker.
- **Grounding is instructed, not guaranteed.** The prompt and citation checks reduce hallucination but cannot prove each sentence is supported. A cited source might not actually support the claim next to it.
- **No conversation memory.** Each question is answered independently.
- **Classifier.** The zero-shot labels depend on hand-written category descriptions. The bundled training data is synthetic and tiny. There is no measured accuracy on real documents.
- **Single-user, local design.** No authentication, no multi-tenancy, JSON-file registry, in-process locks. Processing runs synchronously inside the request, so large PDFs block that request. Exact FAISS search scales linearly with the number of chunks.
- **Evaluation data** is a small demo set; see [Sample results](#sample-results).

## Future improvements

- Hybrid retrieval (BM25 + dense) and a cross-encoder re-ranker, compared on a real evaluation set.
- OCR fallback (e.g. Tesseract) for scanned pages.
- Background job queue for processing large documents, with progress reporting.
- Streaming LLM responses in the UI.
- Sentence-level citation checking (e.g. an NLI model testing whether each cited passage entails its sentence).
- A larger, independently labelled evaluation set, and LLM-as-judge answer grading validated against human labels.
- Authentication and per-user document collections if the app is ever shared.

## Screenshots

> Placeholders. Add your own screenshots to `docs/screenshots/` and update these paths.

| View | Screenshot |
|---|---|
| Upload & processing | `docs/screenshots/upload.png` |
| Semantic search results | `docs/screenshots/search.png` |
| Answer with citations | `docs/screenshots/ask.png` |
| Documents & classification | `docs/screenshots/documents.png` |

## Author

**Your Name**. B.Tech Artificial Intelligence & Machine Learning (3rd year)

- GitHub: `https://github.com/<your-username>`
- LinkedIn: `https://linkedin.com/in/<your-profile>`
- Email: `<your-email>`

See [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) for a detailed walkthrough of the design, algorithms and likely interview questions.
