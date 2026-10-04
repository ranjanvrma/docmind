"""Lightweight document classification on top of sentence embeddings.

Two modes, chosen automatically:

1. **Supervised** (when a trained model exists at ``data/classifier/classifier.joblib``):
   a scikit-learn LogisticRegression trained on embeddings of labelled example
   texts. Train it with ``python main.py train-classifier <csv>``.

2. **Zero-shot** (fallback, no training data needed): embed a short natural
   language description of each category and pick the category whose
   description is most cosine-similar to the document embedding.

In both cases the document is represented by the mean of its chunk embeddings
(re-normalised). Those embeddings were already computed for the search index,
so classification costs almost nothing extra at processing time.

This is a demonstration of an NLP classification pipeline, not a validated
general-purpose document classifier. See the README for how to build a real
labelled dataset; no accuracy claims are made for the bundled sample data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.embeddings import Embedder, normalize_rows
from app.models import ClassificationResult

if TYPE_CHECKING:  # heavy libraries are imported only when a trained model is used
    import pandas as pd
    from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

# Descriptions used by the zero-shot mode. Categories without an entry fall back
# to "a document of type <label>", so custom CLASSIFIER_LABELS still work.
CATEGORY_DESCRIPTIONS = {
    "Research Paper": "An academic research paper with an abstract, related work, methodology, experiments, results and references.",
    "Report": "A formal report presenting findings, analysis, figures and recommendations for an organisation, such as an annual or technical report.",
    "Assignment": "A student homework assignment or exam with numbered questions, tasks, marks and submission instructions.",
    "Notes": "Informal lecture or study notes with short bullet points, definitions and key concepts to remember.",
    "Policy": "An official policy, terms and conditions, or regulation document with rules, obligations, scope and compliance requirements.",
    "Other": "A general document such as a letter, manual, brochure, article or form.",
}


def document_embedding(chunk_embeddings: np.ndarray) -> np.ndarray:
    """Mean-pool chunk embeddings into a single unit-length document vector, shape (1, dim)."""
    if len(chunk_embeddings) == 0:
        raise ValueError("Cannot build a document embedding from zero chunks")
    return normalize_rows(chunk_embeddings.mean(axis=0, keepdims=True))


class DocumentClassifier:
    def __init__(self, embedder: Embedder, labels: list[str], model_path: Path | None = None):
        self.embedder = embedder
        self.labels = labels
        self.model_path = model_path
        self._supervised: LogisticRegression | None = None
        self._label_vectors: np.ndarray | None = None
        if model_path is not None and model_path.exists():
            self._load(model_path)

    @property
    def mode(self) -> str:
        return "supervised" if self._supervised is not None else "zero-shot"

    def _load(self, path: Path) -> None:
        try:
            import joblib
        except ImportError:
            logger.warning(
                "A trained classifier exists at %s but scikit-learn/joblib are not installed "
                "(pip install -r requirements-train.txt); using zero-shot classification",
                path,
            )
            return

        # joblib uses pickle: only load model files you created yourself. The
        # API never writes this file; only `python main.py train-classifier` does.
        bundle = joblib.load(path)
        if bundle.get("embedding_model") != self.embedder.model_name:
            logger.warning(
                "Ignoring classifier at %s: trained with embedding model %s, current model is %s",
                path,
                bundle.get("embedding_model"),
                self.embedder.model_name,
            )
            return
        self._supervised = bundle["model"]
        logger.info("Loaded supervised classifier with classes %s", list(self._supervised.classes_))

    def _zero_shot_vectors(self) -> np.ndarray:
        if self._label_vectors is None:
            descriptions = [CATEGORY_DESCRIPTIONS.get(l, f"A document of type {l}.") for l in self.labels]
            self._label_vectors = self.embedder.embed(descriptions)
        return self._label_vectors

    def classify(self, doc_vector: np.ndarray) -> ClassificationResult:
        doc_vector = np.asarray(doc_vector, dtype=np.float32).reshape(1, -1)
        if self._supervised is not None:
            probabilities = self._supervised.predict_proba(doc_vector)[0]
            scores = {str(c): round(float(p), 4) for c, p in zip(self._supervised.classes_, probabilities)}
            return ClassificationResult(label=max(scores, key=scores.get), method="supervised", scores=scores)

        similarities = (self._zero_shot_vectors() @ doc_vector.T).ravel()
        scores = {label: round(float(s), 4) for label, s in zip(self.labels, similarities)}
        return ClassificationResult(label=max(scores, key=scores.get), method="zero-shot", scores=scores)

    def classify_text(self, text: str) -> ClassificationResult:
        return self.classify(self.embedder.embed([text]))


def load_training_data(csv_path: Path) -> pd.DataFrame:
    import pandas as pd

    df = pd.read_csv(csv_path)
    missing = {"text", "label"} - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} must have 'text' and 'label' columns (missing: {sorted(missing)})")
    df = df.dropna(subset=["text", "label"])
    df["text"] = df["text"].astype(str).str.strip()
    df["label"] = df["label"].astype(str).str.strip()
    df = df[df["text"] != ""].drop_duplicates(subset=["text"])
    if df["label"].nunique() < 2:
        raise ValueError("Training data needs at least two distinct labels")
    return df.reset_index(drop=True)


def train_classifier(embedder: Embedder, df: pd.DataFrame, output_path: Path) -> dict:
    """Train logistic regression on embeddings, report cross-validated metrics, save the model.

    The returned metrics are computed with stratified k-fold cross-validation
    on the provided data. With a small or synthetic dataset they say very
    little about real-world performance.
    """
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    X = embedder.embed(df["text"].tolist())
    y = df["label"].to_numpy()

    min_class_count = int(df["label"].value_counts().min())
    report: dict = {
        "n_examples": int(len(df)),
        "class_counts": {k: int(v) for k, v in df["label"].value_counts().sort_index().items()},
        "embedding_model": embedder.model_name,
    }

    # class_weight="balanced" compensates for unequal class sizes.
    make_model = lambda: LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")  # noqa: E731

    if min_class_count >= 2:
        n_splits = min(5, min_class_count)
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        predictions = cross_val_predict(make_model(), X, y, cv=cv)
        report.update(
            {
                "cv_folds": n_splits,
                "cv_accuracy": round(float(accuracy_score(y, predictions)), 4),
                "cv_macro_f1": round(float(f1_score(y, predictions, average="macro")), 4),
                "cv_per_class": classification_report(y, predictions, output_dict=True, zero_division=0),
            }
        )
    else:
        report["cv_note"] = "Skipped cross-validation: some class has fewer than 2 examples."

    model = make_model().fit(X, y)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "embedding_model": embedder.model_name}, output_path)
    logger.info("Saved classifier to %s", output_path)
    return report
