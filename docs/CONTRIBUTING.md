# Contributing

## Setup

Follow [GETTING_STARTED.md](GETTING_STARTED.md): a Python virtual environment with `requirements-dev.txt`, plus `npm install` in `web/`.

## Before you open a pull request

```bash
pytest                      # backend: 181 tests
cd web
npm run typecheck
npm test                    # frontend: 34 tests
npm run build
```

All of them should pass. If you change retrieval or chunking, also run `python evaluation/evaluate.py` and report the before/after numbers, with the dataset caveat ([EVALUATION.md](EVALUATION.md)).

## Conventions

**Backend**
- Keep business logic in `app/` modules and `DocMindService`; API routes only validate, call the service and map errors.
- New configuration goes in `app/config.py` (and `.env.example`); if it should be editable at runtime, add it to `runtime_settings.EDITABLE`. Security boundaries stay environment-only.
- Never log document text, queries, prompts, answers or secrets.
- Persistent writes go through `utils.atomic_write_*`. Storage problems raise a `StorageError` subclass with recovery instructions.
- Tests: use the `HashingEncoder`/`FakeLLM` fixtures in `tests/conftest.py` so tests stay fast and offline; only `tests/test_embeddings.py` loads the real model.

**Frontend**
- API calls and parsing live in `lib/`; components stay presentational where possible.
- Use the design tokens and existing primitives; don't add colours, shadows or component libraries ad hoc.
- Render untrusted text as React text only. Never use `dangerouslySetInnerHTML`; extend `lib/markdown.ts` if you need more formatting, and never add links or images there.
- Animations use the tokens in `components/animations/motion.ts` and must degrade under reduced motion.
- Don't show numbers the backend doesn't provide (no fake progress or confidence).

**Docs and claims**
- Update the relevant page in `docs/` with behaviour changes.
- Don't claim accuracy, scale or guarantees that haven't been measured.

## Commit messages

Imperative and specific, e.g. "Validate base URL scheme in runtime settings".
