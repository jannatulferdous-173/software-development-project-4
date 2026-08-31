import json
import re
import math
import os

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "situations_model_weights.json")

_TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")

_weights_cache = None


def _load_weights():
    global _weights_cache
    if _weights_cache is None:
        with open(_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["stop_words"] = set(data["stop_words"])
        _weights_cache = data
    return _weights_cache


def _tokenize_with_ngrams(text, stop_words):
    tokens = _TOKEN_RE.findall(text.lower())
    filtered = [t for t in tokens if t not in stop_words]
    ngrams = list(filtered)
    for i in range(len(filtered) - 1):
        ngrams.append(filtered[i] + " " + filtered[i + 1])
    return ngrams


def _tfidf_vector(text, vocab, idf, stop_words):
    terms = _tokenize_with_ngrams(text, stop_words)
    if not terms:
        return {}
    counts = {}
    for term in terms:
        idx = vocab.get(term)
        if idx is not None:
            counts[idx] = counts.get(idx, 0) + 1
    if not counts:
        return {}
    tfidf = {idx: (1.0 + math.log(count)) * idf[idx] for idx, count in counts.items()}
    norm = math.sqrt(sum(v * v for v in tfidf.values()))
    if norm > 0:
        tfidf = {idx: v / norm for idx, v in tfidf.items()}
    return tfidf


def _sigmoid(x):
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        return z / (1.0 + z)


def ml_matches(text, already_matched_categories=None, threshold=0.55):
    if already_matched_categories is None:
        already_matched_categories = set()
    if not text or not text.strip():
        return []
    weights = _load_weights()
    vocab = weights["vocab"]
    idf = weights["idf"]
    classes = weights["classes"]
    per_class = weights["per_class"]
    stop_words = weights["stop_words"]
    tfidf = _tfidf_vector(text, vocab, idf, stop_words)
    if not tfidf:
        return []
    matches = []
    for i, category in enumerate(classes):
        if category in already_matched_categories or category == "general_other":
            continue
        coef = per_class[i]["coef"]
        intercept = per_class[i]["intercept"]
        score = intercept
        for idx, val in tfidf.items():
            score += coef[idx] * val
        prob = _sigmoid(score)
        if prob >= threshold:
            matches.append({"category": category, "confidence": round(prob, 2), "source": "ml"})
    return matches
