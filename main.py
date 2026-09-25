"""DocMind command-line entry point.

    python main.py api                         # run the FastAPI backend
    python main.py ui                          # run the Streamlit frontend
    python main.py ingest file1.pdf file2.pdf  # upload + index PDFs without the UI
    python main.py train-classifier data/classifier/sample_training.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.config import PROJECT_ROOT, get_settings
from app.utils import setup_logging

logger = logging.getLogger("docmind")


def run_api(host: str, port: int, reload: bool) -> None:
    import uvicorn

    uvicorn.run("app.api:app", host=host, port=port, reload=reload)


def run_ui(port: int) -> None:
    script = PROJECT_ROOT / "frontend" / "streamlit_app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(script), "--server.port", str(port)]
    raise SystemExit(subprocess.call(cmd, env=os.environ.copy()))


def run_ingest(paths: list[Path]) -> int:
    from app.ingestion import IngestionError
    from app.service import DocMindService

    service = DocMindService(get_settings())
    doc_ids = []
    for path in paths:
        try:
            record, duplicate = service.upload(path.name, path.read_bytes())
        except (OSError, IngestionError) as exc:
            logger.error("Skipping %s: %s", path, exc)
            continue
        doc_ids.append(record.doc_id)
        logger.info("%s %s -> %s", "Duplicate" if duplicate else "Uploaded", path.name, record.doc_id)
    for record, skipped in service.process(doc_ids):
        state = "already indexed" if skipped else record.status
        print(f"{record.filename:40s} {state:16s} chunks={record.chunk_count} {record.error or ''}")
    return 0 if doc_ids else 1


def run_train_classifier(csv_path: Path) -> int:
    from app.classifier import load_training_data, train_classifier
    from app.embeddings import Embedder

    settings = get_settings()
    df = load_training_data(csv_path)
    embedder = Embedder(settings.embedding_model, settings.embedding_batch_size)
    report = train_classifier(embedder, df, settings.classifier_model_path)
    report_path = settings.classifier_model_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Trained on {report['n_examples']} examples: {report['class_counts']}")
    if "cv_accuracy" in report:
        print(
            f"{report['cv_folds']}-fold cross-validated accuracy={report['cv_accuracy']:.3f} "
            f"macro-F1={report['cv_macro_f1']:.3f}  (measured on {csv_path.name} only)"
        )
    print(f"Model saved to {settings.classifier_model_path}; report saved to {report_path}")
    print("Restart the API so it picks up the new classifier.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DocMind: PDF semantic search and grounded Q&A")
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("api", help="Run the FastAPI backend")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true", help="Auto-reload on code changes (development)")

    ui = sub.add_parser("ui", help="Run the Streamlit frontend")
    ui.add_argument("--port", type=int, default=8501)

    ingest = sub.add_parser("ingest", help="Upload and index PDF files from disk")
    ingest.add_argument("paths", nargs="+", type=Path)

    train = sub.add_parser("train-classifier", help="Train the supervised document classifier")
    train.add_argument("csv", type=Path, help="CSV with 'text' and 'label' columns")

    args = parser.parse_args()
    setup_logging(get_settings().log_level)

    if args.command == "api":
        run_api(args.host, args.port, args.reload)
        return 0
    if args.command == "ui":
        run_ui(args.port)
        return 0
    if args.command == "ingest":
        return run_ingest(args.paths)
    return run_train_classifier(args.csv)


if __name__ == "__main__":
    sys.exit(main())
