"""
train_situations.py — trains the ML backup for situations.py
----------------------------------------------------------------
Run this whenever you add new rows to training_data.csv:

    pip install scikit-learn joblib --break-system-packages
    python train_situations.py

It reads training_data.csv (columns: text,labels — labels are
semicolon-separated for multi-label rows), trains a small multi-label
TF-IDF + Logistic Regression classifier, and saves it to
situations_model.joblib. situations.py loads that file automatically
the next time the Flask server starts — no code changes needed there.

CAVEAT: with under ~100 total examples spread across 12 categories,
this model WILL overfit and won't generalize far beyond phrasing
similar to what's in the CSV. It's meant as a backup layer behind the
keyword rules in situations.py, not a standalone accurate classifier.
The more real (anonymized) examples you add to the CSV over time —
ideally 30+ per category — the better this gets. Re-run this script
after every meaningful addition to the CSV.
"""

import csv
import os

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

CSV_PATH = os.path.join(os.path.dirname(__file__), "training_data.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "situations_model.joblib")


def load_training_rows():
    texts, label_sets = [], []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("text") or "").strip()
            labels_raw = (row.get("labels") or "").strip()
            if not text or not labels_raw:
                continue
            labels = [lbl.strip() for lbl in labels_raw.split(";") if lbl.strip()]
            texts.append(text)
            label_sets.append(labels)
    return texts, label_sets


def main():
    texts, label_sets = load_training_rows()
    if len(texts) < 10:
        print(f"Only found {len(texts)} usable rows in {CSV_PATH} — add more before training.")
        return

    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform(label_sets)

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        stop_words="english",
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(texts)

    classifier = OneVsRestClassifier(
        LogisticRegression(max_iter=1000, class_weight="balanced")
    )
    classifier.fit(X, Y)

    joblib.dump({"vectorizer": vectorizer, "classifier": classifier, "mlb": mlb}, MODEL_PATH)

    print(f"Trained on {len(texts)} examples across {len(mlb.classes_)} categories:")
    for category in mlb.classes_:
        count = sum(1 for labels in label_sets if category in labels)
        print(f"  {category}: {count} examples")
    print(f"\nSaved model to {MODEL_PATH}")
    print(
        "\nReminder: this is a small-dataset model meant as a backup behind "
        "the keyword rules in situations.py, not a standalone accurate "
        "classifier yet. Add more examples and re-run this script over time."
    )


if __name__ == "__main__":
    main()
