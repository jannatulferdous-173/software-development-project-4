"""
condition_model.py
-------------------
Pure-Python TF-IDF + Logistic Regression inference for mental-health
condition pattern detection (Anxiety / Bipolar / Depression / Normal /
Personality disorder / Stress).

No numpy, pandas, or scikit-learn imports here on purpose — this file only
uses json, re, and math from the standard library so it never touches a
compiled .pyd/DLL. That means it will run even when Windows Smart App
Control (or any similar Application Control policy) blocks numpy's
_multiarray_umath.dll.

The actual model (vocabulary, IDF weights, logistic regression
coefficients) was trained separately with scikit-learn and exported to
condition_model_weights.json. This file just re-implements the same math
by hand:
  1. tokenize + count words              (TF)
  2. multiply by each word's IDF weight  (TF-IDF)
  3. L2-normalize the resulting vector
  4. dot product with each class's coefficients + intercept -> logits
  5. softmax over logits -> probabilities

IMPORTANT: This gives a *pattern match*, not a diagnosis. Every label is
phrased as "this pattern is worth discussing with a professional", never
"you have X". If confidence is below CONFIDENCE_THRESHOLD, we say nothing
rather than force a guess.
"""

import json
import re
import math
import os

CONFIDENCE_THRESHOLD = 0.50

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "condition_model_weights.json")

_TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")

# Non-diagnostic, supportive framing per label. Never states a diagnosis.
_FRAMING = {
    "Anxiety": "Some patterns here are often associated with anxiety — "
               "worry, restlessness, or a racing mind. This isn't a diagnosis, "
               "but it may be worth discussing with a counselor or doctor.",
    "Bipolar": "There are patterns here sometimes associated with big mood "
               "swings. This isn't a diagnosis, but a conversation with a "
               "mental health professional could help make sense of it.",
    "Depression": "Some of what you wrote reflects patterns often linked to "
                  "low mood or depression. This isn't a diagnosis, but "
                  "talking to a professional could be a helpful next step.",
    "Normal": "Nothing here points to a specific concerning pattern — "
              "your entry reads as fairly steady.",
    "Personality disorder": "There are some patterns here that professionals "
                             "sometimes look into further. This isn't a "
                             "diagnosis — a conversation with a mental health "
                             "professional would be the right way to explore it.",
    "Stress": "This reads like it carries some stress patterns. This isn't a "
              "diagnosis, but it may help to talk through what's weighing on "
              "you with someone you trust or a professional.",
}

_weights_cache = None


def _load_weights():
    global _weights_cache
    if _weights_cache is None:
        with open(_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            _weights_cache = json.load(f)
    return _weights_cache


def _tokenize(text):
    return _TOKEN_RE.findall(text.lower())


def _tfidf_vector(text, vocab, idf):
    """Returns a sparse dict {feature_index: tfidf_value}, L2-normalized."""
    tokens = _tokenize(text)
    if not tokens:
        return {}

    counts = {}
    for tok in tokens:
        idx = vocab.get(tok)
        if idx is not None:
            counts[idx] = counts.get(idx, 0) + 1

    if not counts:
        return {}

    tfidf = {idx: count * idf[idx] for idx, count in counts.items()}

    norm = math.sqrt(sum(v * v for v in tfidf.values()))
    if norm > 0:
        tfidf = {idx: v / norm for idx, v in tfidf.items()}

    return tfidf


def _softmax(logits):
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps)
    return [x / s for x in exps]


def predict_condition(text):
    """
    Returns None if there's no clear pattern (confidence below threshold)
    or the text is empty. Otherwise returns:
    {
        "label": "Depression",
        "confidence": 0.83,
        "message": "<non-diagnostic framing text>",
        "scores": {"Anxiety": 0.02, "Bipolar": 0.01, ...}
    }
    """
    if not text or not text.strip():
        return None

    weights = _load_weights()
    vocab = weights["vocab"]
    idf = weights["idf"]
    coef = weights["coef"]          # list[n_classes][n_features]
    intercept = weights["intercept"]  # list[n_classes]
    classes = weights["classes"]

    tfidf = _tfidf_vector(text, vocab, idf)
    if not tfidf:
        return None

    logits = []
    for class_idx in range(len(classes)):
        class_coef = coef[class_idx]
        score = intercept[class_idx]
        for feat_idx, val in tfidf.items():
            score += class_coef[feat_idx] * val
        logits.append(score)

    probs = _softmax(logits)
    scores = {classes[i]: round(probs[i], 4) for i in range(len(classes))}

    best_idx = max(range(len(classes)), key=lambda i: probs[i])
    best_label = classes[best_idx]
    best_conf = probs[best_idx]

    if best_conf < CONFIDENCE_THRESHOLD:
        return None

    return {
        "label": best_label,
        "confidence": round(best_conf, 4),
        "message": _FRAMING.get(best_label, ""),
        "scores": scores,
    }


if __name__ == "__main__":
    # quick manual smoke test
    samples = [
        "I can't stop worrying about everything, my heart races all night",
        "I feel numb and empty, nothing brings me joy anymore",
        "Had a normal day at work, cooked dinner, watched a show",
        "One minute I feel on top of the world, then crash into despair",
    ]
    for s in samples:
        print(s[:50], "->", predict_condition(s))
