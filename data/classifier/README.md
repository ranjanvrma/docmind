# Classifier training data

`sample_training.csv` is a **synthetic sample dataset**: 48 short texts (8 per category)
written by hand for this project to demonstrate the supervised classification pipeline.
It is not drawn from real documents, it is far too small to train a reliable classifier,
and any cross-validation score computed on it says very little about real-world accuracy.

## Building a real dataset

1. Collect real PDFs for each category (aim for 50+ per category, from varied sources).
2. Extract text with DocMind's pipeline (`app.ingestion.extract_pages` +
   `app.preprocessing.preprocess_pages`) and keep the first ~2,000 characters of each.
3. Label each document; have a second person label a subset to check agreement.
4. Save as a CSV with columns `text,label`.
5. Hold out a test set the classifier never sees, *then* train on the rest with
   `python main.py train-classifier your_data.csv`.

`classifier.joblib` and its report (created by training) are git-ignored.
Restart the API after training so it loads the new model.
