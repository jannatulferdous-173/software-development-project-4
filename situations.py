"""
situations.py — MindMirror's "situation" (life-topic) detector
----------------------------------------------------------------
This is a SEPARATE axis from mood/emotion (nlp.py handles that). Mood
answers "how does this feel" (sad, anxious, calm...). Situations
answers "what is this ABOUT" (pregnancy_postpartum, academic_stress,
harassment_safety...). Keeping them separate means advice can be
tailored to the actual topic, not just the emotional tone — e.g. two
very different situations can both come out "Unsettled" on mood, but
need completely different suggestions.

HYBRID DETECTION STRATEGY
--------------------------
1. KEYWORD RULES (checked first): a curated list of high-precision
   phrases per category. If the text contains one of these, we're
   confident enough to tag the category WITHOUT needing the ML model —
   this also means the app still works (just with lower recall) even
   if the ML model hasn't been trained yet, or scikit-learn isn't
   installed.
2. ML BACKUP (checked second): a small multi-label TF-IDF + Logistic
   Regression classifier, trained from training_data.csv via
   train_situations.py. Catches phrasings the keyword list doesn't,
   using a confidence threshold. Loaded lazily and wrapped in
   try/except so a missing/untrained model never crashes the app —
   it just means only keyword rules apply until training_situations.py
   has been run.

IMPORTANT — SMALL DATASET CAVEAT
---------------------------------
training_data.csv currently has ~96 rows split across 12 categories
(some with only 5-10 examples). A classifier trained on that will
overfit and will NOT generalize well to very different phrasing yet.
Treat the ML layer as a rough backup, not a source of truth, until the
dataset grows into the hundreds of examples per category. The keyword
layer is deliberately kept as the primary, more trustworthy signal.
"""

import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "situations_model.joblib")

CATEGORIES = [
    "pregnancy_postpartum",
    "body_image",
    "self_esteem_confidence",
    "harassment_safety",
    "academic_stress",
    "financial_stress",
    "work_life_balance",
    "family_relationships",
    "parenting_challenges",
    "loneliness_isolation",
    "relationship_marital",
    "general_other",
]

# ---------------------------------------------------------------------
# High-precision keyword/phrase rules. These are intentionally narrow —
# they should almost never misfire on unrelated text. Broader, fuzzier
# matching is left to the ML layer instead of loosening these.
# ---------------------------------------------------------------------
KEYWORD_RULES = {
    "pregnancy_postpartum": [
        "pregnan", "delivery", "postpartum", "the baby comes", "after having a baby",
        "since the baby arrived", "newborn", "my newborn", "feeding the baby",
    ],
    "body_image": [
        "hate how i look", "disgusted with my own body", "my weight", "how my body looks",
        "avoid looking at myself", "avoid the mirror", "uncomfortable with how my body",
        "clothes fit differently",
    ],
    "self_esteem_confidence": [
        "not attractive enough", "doubt myself", "doubting myself", "not good enough",
        "come up short", "feel worthless", "not smart enough",
    ],
    "harassment_safety": [
        "harass", "bully", "bullying", "bullied", "stalk", "won't stop messaging",
        "wont stop messaging", "keeps messaging", "followed me", "waiting near my usual route",
        "unwanted messages", "makes jokes about me", "humiliates me in front of",
        "mocking me", "keep staring and commenting", "cross a line", "makes me uncomfortable",
    ],
    "academic_stress": [
        "exam", "exams", "assignment", "assignments", "coursework", "study", "studied",
        "cramming", "scholarship", "my grades", "results are coming out", "the test",
    ],
    "financial_stress": [
        "rent this month", "bank balance", "loan payments", "can't afford", "cant afford",
        "lost my job", "losing my job", "budget", "bills", "medical expenses", "groceries",
    ],
    "work_life_balance": [
        "work calls", "extra shifts", "commute", "work emails", "overtime",
        "never truly off duty", "no weekend to myself", "running on empty",
    ],
    "family_relationships": [
        "my in-laws", "my mother", "my father", "family dinner", "my siblings",
        "keeping the peace in this family", "my relatives", "treats me like a child",
    ],
    "parenting_challenges": [
        "my son", "my daughter", "my child", "my kid", "my teenager", "pulling away",
        "goes straight to his room", "shuts me out",
    ],
    "loneliness_isolation": [
        "feel invisible", "no one notices", "haven't had a real conversation",
        "nobody really knows how i am doing", "withdrawing from friends", "lonely",
    ],
    "relationship_marital": [
        "my partner and i", "my spouse", "we keep having the same fight",
        "listens to respond rather than to understand", "the closeness between us",
    ],
}


def _keyword_matches(text_lower):
    matches = []
    for category, phrases in KEYWORD_RULES.items():
        if any(phrase in text_lower for phrase in phrases):
            matches.append({"category": category, "confidence": 0.95, "source": "keyword"})
    return matches


# ---------------------------------------------------------------------
# ML backup — loaded lazily so the app still runs (keyword-only) if
# scikit-learn isn't installed or the model hasn't been trained yet.
# ---------------------------------------------------------------------
_ml_bundle = None
_ml_load_attempted = False


def _load_ml_bundle():
    global _ml_bundle, _ml_load_attempted
    if _ml_load_attempted:
        return _ml_bundle
    _ml_load_attempted = True
    try:
        import joblib
        if os.path.exists(MODEL_PATH):
            _ml_bundle = joblib.load(MODEL_PATH)
    except Exception:
        # scikit-learn/joblib missing, or model file corrupt/incompatible —
        # fall back to keyword-only detection rather than crashing.
        _ml_bundle = None
    return _ml_bundle


def _ml_matches(text, already_matched_categories, threshold=0.45):
    bundle = _load_ml_bundle()
    if not bundle:
        return []

    try:
        vectorizer = bundle["vectorizer"]
        classifier = bundle["classifier"]
        mlb = bundle["mlb"]

        X = vectorizer.transform([text])
        probabilities = classifier.predict_proba(X)[0]

        matches = []
        for category, prob in zip(mlb.classes_, probabilities):
            if category in already_matched_categories:
                continue  # keyword layer already confidently tagged this one
            if category == "general_other":
                continue  # not useful as a "detected situation" tag
            if prob >= threshold:
                matches.append({"category": category, "confidence": round(float(prob), 2), "source": "ml"})
        return matches
    except Exception:
        return []


def detect_situations(text):
    """Returns a list of {category, confidence, source} dicts, most
    confident first. Empty list means nothing matched — that's normal
    for everyday journal entries that aren't "about" one of these
    specific topics."""
    text_lower = text.lower()

    keyword_results = _keyword_matches(text_lower)
    already_matched = {m["category"] for m in keyword_results}

    ml_results = _ml_matches(text, already_matched)

    all_results = keyword_results + ml_results
    all_results.sort(key=lambda m: m["confidence"], reverse=True)
    return all_results
