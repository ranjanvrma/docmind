import pandas as pd
import pytest

from app.classifier import DocumentClassifier, load_training_data, train_classifier
from app.embeddings import Embedder
from tests.conftest import HashingEncoder

LABELS = ["Policy", "Assignment"]
TRAIN = pd.DataFrame(
    {
        "text": [
            "employees must comply with this policy and its rules",
            "this policy applies to all staff and contractors",
            "violations of the policy lead to disciplinary action",
            "policy scope compliance obligations for employees",
            "question one worth ten marks submit homework by friday",
            "assignment due date answer all questions show working",
            "homework problem set marks deadline submission portal",
            "assignment question marks exam submit answers",
        ],
        "label": ["Policy"] * 4 + ["Assignment"] * 4,
    }
)


def test_zero_shot_scores_every_label(fake_embedder):
    classifier = DocumentClassifier(fake_embedder, ["Policy", "Other", "My Custom Label"])
    result = classifier.classify_text("some document text")
    assert classifier.mode == "zero-shot" and result.method == "zero-shot"
    assert set(result.scores) == {"Policy", "Other", "My Custom Label"}
    assert result.label == max(result.scores, key=result.scores.get)


def test_supervised_training_saves_model_and_reports_cv(fake_embedder, tmp_path):
    path = tmp_path / "clf.joblib"
    report = train_classifier(fake_embedder, TRAIN, path)

    assert path.exists()
    assert report["n_examples"] == 8 and report["cv_folds"] == 4
    assert 0.0 <= report["cv_accuracy"] <= 1.0

    classifier = DocumentClassifier(fake_embedder, LABELS, path)
    assert classifier.mode == "supervised"
    result = classifier.classify_text("please submit the homework assignment answers for marks")
    assert result.label == "Assignment"
    assert sum(result.scores.values()) == pytest.approx(1.0, abs=1e-3)


def test_model_trained_with_other_embedding_model_is_ignored(fake_embedder, tmp_path):
    path = tmp_path / "clf.joblib"
    train_classifier(fake_embedder, TRAIN, path)
    other = Embedder("a-different-model", model=HashingEncoder())
    assert DocumentClassifier(other, LABELS, path).mode == "zero-shot"


def test_load_training_data_validates_columns_and_cleans(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("content,category\nx,y\n")
    with pytest.raises(ValueError, match="text"):
        load_training_data(bad)

    good = tmp_path / "good.csv"
    good.write_text("text,label\n hello ,A\nhello,A\n,B\nworld,B\n")
    df = load_training_data(good)
    assert df["text"].tolist() == ["hello", "world"]  # stripped, deduplicated, blank dropped


def test_training_requires_two_labels(tmp_path):
    single = tmp_path / "single.csv"
    single.write_text("text,label\na,X\nb,X\n")
    with pytest.raises(ValueError, match="two distinct labels"):
        load_training_data(single)
