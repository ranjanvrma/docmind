"""Evaluate retrieval (and optionally answer) quality against a labelled dataset.

    python evaluation/evaluate.py                       # retrieval metrics only
    python evaluation/evaluate.py --k 1 3 5 10          # choose cut-offs
    python evaluation/evaluate.py --qa                  # also evaluate answers (calls the LLM)

The documents listed in the dataset are indexed into a *temporary* data
directory using the same pipeline and settings as the app (EMBEDDING_MODEL,
CHUNK_SIZE, CHUNK_OVERLAP from .env), so your real index is never touched.

Relevance is labelled at page level: a retrieved chunk counts as relevant if
it comes from a (document, page) pair listed in the query's ``relevant`` list.
Page labels survive changes to chunk size/overlap; chunk IDs do not. If a
query also has ``relevant_chunk_ids``, those are used instead.

Metrics (for each cut-off K, averaged over queries):
  Hit@K        1 if at least one relevant chunk is in the top K, else 0
  Precision@K  (# relevant chunks in top K) / K
  Recall@K     (# distinct relevant pages found in top K) / (# relevant pages)
  MRR          1 / rank of the first relevant chunk (0 if none in top max(K))
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import string
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pandas is imported only while an evaluation runs
    import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.qa import is_abstention  # noqa: E402
from app.utils import setup_logging  # noqa: E402

DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "sample_eval.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

# ----------------------------------------------------------------------------
# Retrieval metrics (pure functions, unit-tested in tests/test_evaluation.py)
# ----------------------------------------------------------------------------


def precision_at_k(relevance: list[bool], k: int) -> float:
    return sum(relevance[:k]) / k


def recall_at_k(retrieved_keys: list, relevant_keys: set, k: int) -> float:
    if not relevant_keys:
        return 0.0
    return len(set(retrieved_keys[:k]) & relevant_keys) / len(relevant_keys)


def hit_at_k(relevance: list[bool], k: int) -> float:
    return 1.0 if any(relevance[:k]) else 0.0


def reciprocal_rank(relevance: list[bool]) -> float:
    for rank, is_relevant in enumerate(relevance, start=1):
        if is_relevant:
            return 1.0 / rank
    return 0.0


# ----------------------------------------------------------------------------
# Answer metrics
# ----------------------------------------------------------------------------

_CITATION = re.compile(r"\[[^\]]*\]")
_ARTICLES = re.compile(r"\b(a|an|the)\b")


def normalize_answer(text: str) -> list[str]:
    """SQuAD-style normalisation: drop citations, punctuation, articles; lowercase."""
    text = _CITATION.sub(" ", text.lower())
    text = "".join(ch for ch in text if ch not in string.punctuation)
    return _ARTICLES.sub(" ", text).split()


def token_f1(prediction: str, reference: str) -> float:
    """Token-overlap F1. Crude: rewards shared words, blind to paraphrase and correctness."""
    pred, ref = normalize_answer(prediction), normalize_answer(reference)
    if not pred or not ref:
        return float(pred == ref)
    common = sum((Counter(pred) & Counter(ref)).values())
    if common == 0:
        return 0.0
    precision, recall = common / len(pred), common / len(ref)
    return 2 * precision * recall / (precision + recall)


# ----------------------------------------------------------------------------


def _relevant_keys(item: dict) -> set[tuple[str, int]]:
    return {(r["document"], int(r["page"])) for r in item.get("relevant", [])}


class EvaluationError(RuntimeError):
    pass


def build_eval_service(dataset: dict, workdir: Path, settings=None, embedder=None):
    """Index the dataset's PDFs into a throwaway data dir using ``settings`` (default: .env)."""
    from app.service import DocMindService

    settings = dataclasses.replace(settings or get_settings(), data_dir=workdir)
    service = DocMindService(settings, embedder=embedder)
    docs_dir = PROJECT_ROOT / dataset["documents_dir"]
    pdfs = sorted(docs_dir.glob("*.pdf"))
    if not pdfs and docs_dir.name == "sample_docs":
        from evaluation.make_sample_docs import main as make_sample_docs

        make_sample_docs()
        pdfs = sorted(docs_dir.glob("*.pdf"))
    if not pdfs:
        raise EvaluationError(f"No PDFs found in {docs_dir}")
    for pdf in pdfs:
        service.upload(pdf.name, pdf.read_bytes())
    failures = [r for r, _ in service.process() if r.status != "processed"]
    if failures:
        raise EvaluationError(f"Failed to index: {[f.filename for f in failures]}")
    return service


def run_retrieval_evaluation(settings, ks=(1, 3, 5), dataset_path: Path = DEFAULT_DATASET, embedder=None) -> dict:
    """Run the retrieval evaluation with the given settings and return a JSON-friendly report.

    Used by the API's evaluation lab so the UI can measure the effect of
    chunking/retrieval settings. Works in a temporary directory; the real index
    is never touched.
    """
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    ks = sorted(set(ks))
    with tempfile.TemporaryDirectory(prefix="docmind-eval-") as tmp:
        service = build_eval_service(dataset, Path(tmp), settings, embedder)
        per_query, summary = evaluate_retrieval(service, dataset["retrieval"], ks)
        top = max(ks)
        return {
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset": dataset["name"],
            "dataset_description": dataset["description"],
            "n_queries": int(len(per_query)),
            "n_documents": len(service.list_documents()),
            "indexed_chunks": service.store.size,
            "settings": {
                "embedding_model": settings.embedding_model,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
            },
            "metrics": [
                {"k": int(row.k), "hit_rate": round(float(row.hit_rate), 4), "precision": round(float(row.precision), 4), "recall": round(float(row.recall), 4)}
                for row in summary.itertuples()
            ],
            "mrr": round(float(per_query["mrr"].mean()), 4),
            "misses": [
                {"id": r["id"], "query": r["query"], "top1": r["top1"]}
                for r in per_query[per_query[f"hit@{top}"] == 0].to_dict(orient="records")
            ],
        }


def evaluate_retrieval(service, items: list[dict], ks: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    import pandas as pd

    max_k = max(ks)
    rows = []
    for item in items:
        results = service.search(item["query"], top_k=max_k)
        if item.get("relevant_chunk_ids"):
            relevant = set(item["relevant_chunk_ids"])
            keys = [r.chunk.chunk_id for r in results]
        else:
            relevant = _relevant_keys(item)
            keys = [(r.chunk.doc_name, r.chunk.page_number) for r in results]
        relevance = [key in relevant for key in keys]

        row = {
            "id": item["id"],
            "query": item["query"],
            "n_relevant": len(relevant),
            "mrr": reciprocal_rank(relevance),
            "top1": f"{keys[0][0]} p{keys[0][1]}" if keys and isinstance(keys[0], tuple) else (keys[0] if keys else ""),
            "top1_score": round(results[0].score, 4) if results else None,
        }
        for k in ks:
            row[f"hit@{k}"] = hit_at_k(relevance, k)
            row[f"precision@{k}"] = precision_at_k(relevance, k)
            row[f"recall@{k}"] = recall_at_k(keys, relevant, k)
        rows.append(row)

    per_query = pd.DataFrame(rows)
    summary = pd.DataFrame(
        [
            {
                "k": k,
                "hit_rate": per_query[f"hit@{k}"].mean(),
                "precision": per_query[f"precision@{k}"].mean(),
                "recall": per_query[f"recall@{k}"].mean(),
            }
            for k in ks
        ]
    )
    return per_query, summary


def evaluate_qa(service, items: list[dict], top_k: int) -> tuple[pd.DataFrame, dict]:
    import pandas as pd

    rows = []
    for item in items:
        result = service.ask(item["question"], top_k=top_k)
        relevant = _relevant_keys(item)
        source_keys = [(s.chunk.doc_name, s.chunk.page_number) for s in result.sources]
        cited_keys = [source_keys[n - 1] for n in sorted(result.cited_numbers)]
        abstained = is_abstention(result.answer)
        rows.append(
            {
                "id": item["id"],
                "answerable": item["answerable"],
                "abstained": abstained,
                "token_f1": token_f1(result.answer, item["reference_answer"]) if item["answerable"] else None,
                "context_has_relevant_page": any(k in relevant for k in source_keys) if relevant else None,
                "citation_precision": (
                    sum(k in relevant for k in cited_keys) / len(cited_keys) if item["answerable"] and cited_keys else None
                ),
                "invalid_citations": len(result.invalid_citations),
                "answer": result.answer,
            }
        )
    df = pd.DataFrame(rows)
    answerable, unanswerable = df[df["answerable"]], df[~df["answerable"]]
    summary = {
        "n_answerable": int(len(answerable)),
        "n_unanswerable": int(len(unanswerable)),
        "mean_token_f1_answerable": _mean(answerable["token_f1"]),
        "false_abstention_rate": _mean(answerable["abstained"]),
        "correct_abstention_rate_unanswerable": _mean(unanswerable["abstained"]),
        "context_recall_answerable": _mean(answerable["context_has_relevant_page"]),
        "mean_citation_precision": _mean(answerable["citation_precision"]),
        "total_invalid_citations": int(df["invalid_citations"].sum()),
    }
    return df, summary


def _mean(series: pd.Series) -> float | None:
    series = series.dropna().astype(float)
    return round(float(series.mean()), 4) if len(series) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--qa", action="store_true", help="Also evaluate generated answers (requires LLM_API_KEY)")
    parser.add_argument("--qa-top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    settings = get_settings()
    setup_logging("WARNING")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    ks = sorted(set(args.k))
    args.output.mkdir(parents=True, exist_ok=True)

    print(f"Dataset: {dataset['name']}  ({len(dataset['retrieval'])} retrieval queries)")
    print(f"NOTE: {dataset['description']}\n")

    with tempfile.TemporaryDirectory(prefix="docmind-eval-") as tmp:
        try:
            service = build_eval_service(dataset, Path(tmp))
        except EvaluationError as exc:
            print(f"Evaluation failed: {exc}")
            return 1
        print(f"Indexed {len(service.list_documents())} documents -> {service.store.size} chunks\n")

        per_query, summary = evaluate_retrieval(service, dataset["retrieval"], ks)
        report = {
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset": dataset["name"],
            "embedding_model": settings.embedding_model,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "indexed_chunks": service.store.size,
            "n_queries": int(len(per_query)),
            "retrieval": summary.round(4).to_dict(orient="records"),
            "mrr": round(float(per_query["mrr"].mean()), 4),
        }
        per_query.to_csv(args.output / "retrieval_per_query.csv", index=False)

        print("Retrieval results (measured on this run):")
        print(summary.round(3).to_string(index=False))
        print(f"MRR@{max(ks)}: {report['mrr']:.3f}\n")
        misses = per_query[per_query[f"hit@{max(ks)}"] == 0]
        if len(misses):
            print(f"Queries with no relevant chunk in top {max(ks)}:")
            print(misses[["id", "query", "top1"]].to_string(index=False), "\n")

        if args.qa:
            if not settings.llm_configured:
                print("Skipping QA evaluation: LLM_API_KEY is not set.")
            else:
                qa_df, qa_summary = evaluate_qa(service, dataset["qa"], args.qa_top_k)
                qa_df.to_csv(args.output / "qa_per_question.csv", index=False)
                report["qa"] = {"llm_model": settings.llm_model, **qa_summary}
                print("QA results (measured on this run):")
                for key, value in qa_summary.items():
                    print(f"  {key}: {value}")

    (args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved results to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
