"""
situations.py — MindMirror's "situation" (life-topic) detector
----------------------------------------------------------------
This is a SEPARATE axis from mood/emotion (nlp.py handles that). Mood
answers "how does this feel" (sad, anxious, calm...). Situations
answers "what is this ABOUT" (pregnancy_postpartum, academic_stress,
harassment_safety...). Keeping them separate means advice can be
tailored to the actual topic, not just the emotional tone.

THREE-TIER DETECTION STRATEGY
-------------------------------
1. KEYWORD RULES (always checked first): a curated list of
   high-precision phrases per category. If the text contains one of
   these, we're confident enough to tag the category immediately —
   this also means the app still works (just with lower recall) even
   with no internet connection or no HF_API_TOKEN configured.

2. ZERO-SHOT TRANSFORMER (checked second, for whatever the keyword
   layer didn't already catch): calls Hugging Face's hosted
   "facebook/bart-large-mnli" model via a plain HTTPS request — no
   local ML library install needed (see the note in nlp.py about why
   that matters on this project's Windows setup). "Zero-shot" means
   it was never trained on training_data.csv or MindMirror's category
   names at all — it's a general-purpose model that can classify text
   against ANY list of category labels you hand it at request time,
   using real contextual/semantic understanding rather than keyword
   matching or memorized training examples. This is what actually
   solves the "TextBlob/keyword-only can't understand context" gap —
   without needing thousands of labeled examples per category first.

3. LOCAL ML FALLBACK (only used if HF_API_TOKEN isn't set, or the API
   call fails/times out): a pure-Python (no numpy/pandas/scikit-learn)
   reimplementation of the original TF-IDF + Logistic Regression
   classifier, trained from training_data.csv via train_situations.py.
   See the note below (2026-08-29) for why this is pure-Python now.

   IMPORTANT — SMALL DATASET CAVEAT (applies to tier 3 only)
   -----------------------------------------------------------
   training_data.csv currently has under 200 rows split across 12
   categories. A classifier trained on that will overfit and won't
   generalize well to very different phrasing. This ONLY affects tier
   3 (the local fallback) — tier 2 (zero-shot) doesn't use
   training_data.csv at all, so it isn't limited by dataset size.
   Setting HF_API_TOKEN (see .env.example) is what actually raises
   accuracy here; growing training_data.csv mainly helps the offline
   fallback.

NOTE ON PURE-PYTHON TIER 3 (2026-08-29):
Tier 3 used to load situations_model.joblib directly via joblib/
scikit-learn at runtime. That's a problem on machines where Windows
Smart App Control (or a similar Application Control policy) blocks
compiled .pyd/DLL files — numpy/scikit-learn can't even be imported
there, silently disabling this whole tier (wrapped in try/except so
it fails quietly instead of crashing, which is exactly why it can go
unnoticed). situations_ml.py re-implements the same trained model's
math (TF-IDF + one binary logistic regression per category, matching
OneVsRestClassifier's genuinely multi-label behavior) using only
json/re/math from the standard library, reading its weights from
situations_model_weights.json instead of the .joblib file. Verified
against the original scikit-learn model: 0 threshold-crossing
mismatches across all 1100 (text, category) pairs in
training_data.csv. situations_model.joblib itself is no longer read
by this file — regenerate situations_model_weights.json instead
(see export_situations.py) if training_data.csv changes.

NOTE ON KEYWORD EXPANSION (2026-08-29):
parenting_challenges' keyword list previously only caught phrases
about an already-verbal child pulling away ("my son", "goes straight
to his room", etc). Journal entries about the EARLY, exhausting phase
of parenting a baby/newborn ("since becoming a parent", "taking care
of my baby while also managing the household") weren't matching
anything here, so the app fell through to a generic mood-only
suggestion set (random anxiety book/game) with nothing tailored to
new-parent burnout. Added a set of phrases for that phase below.
"""

import json
import os
import urllib.error
import urllib.request

from situations_ml import ml_matches as _pure_python_ml_matches

MODEL_PATH = os.path.join(os.path.dirname(__file__), "situations_model.joblib")
HF_ZERO_SHOT_MODEL_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

CATEGORIES = [
    "pregnancy_postpartum",
    "body_image",
    "eating_disorder",
    "self_esteem_confidence",
    "harassment_safety",
    "past_trauma_abuse",
    "academic_stress",
    "financial_stress",
    "work_life_balance",
    "family_relationships",
    "parenting_challenges",
    "loneliness_isolation",
    "relationship_marital",
    "grief_loss",
    "health_illness",
    "career_uncertainty",
    "social_anxiety",
    "caregiving_burden",
    "sleep_issues",
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
    "eating_disorder": [
        "eating disorder", "disordered eating", "binge eating", "binge and purge",
        "purging after i eat", "purge after eating", "throwing up after i eat",
        "throw up after eating", "starving myself", "starve myself",
        "restrict my food", "restricting food", "restricting what i eat",
        "obsessed with calories", "counting every calorie", "afraid to eat",
        "scared to eat", "body shame", "shamed my body", "shame my body",
        "shame me about my body", "shame me about my weight",
    ],
    "body_image": [
        "hate how i look", "disgusted with my own body", "my weight", "how my body looks",
        "avoid looking at myself", "avoid the mirror", "uncomfortable with how my body",
        "clothes fit differently",

    ],
    "self_esteem_confidence": [
        "not attractive enough", "doubt myself", "doubting myself", "not good enough",
        "come up short", "feel worthless", "not smart enough",
        "better than them", "worse than them", "used to be better",
        "once i was better", "better student than", "used to be the best",
    ],
    "harassment_safety": [
        "harass", "bully", "bullying", "bullied", "stalk", "won't stop messaging",
        "wont stop messaging", "keeps messaging", "followed me", "waiting near my usual route",
        "unwanted messages", "makes jokes about me", "humiliates me in front of",
        "mocking me", "keep staring and commenting", "cross a line", "makes me uncomfortable",
    ],
    "past_trauma_abuse": [
        "i was abused", "was abused when i was", "was abused as a child",
        "sexually abused", "physically abused", "emotionally abused",
        "abusive childhood", "abusive parent", "abusive household",
        "growing up i was abused", "molested", "was molested",
        "was assaulted", "assaulted me when i was", "childhood abuse",
        "childhood trauma", "was traumatized", "ptsd from",
        "flashbacks of the abuse", "flashbacks from", "survivor of abuse",
        "the abuse i went through", "the abuse i experienced",
        "get beaten by", "got beaten by", "beaten by my father", "beaten by my mother",
        "watched my mother get hit", "watched my father get hit",
        "watching my mother get hit", "watching my father get hit",
        "watching my mother get beaten", "watching my father get beaten",
        "domestic violence", "witnessed domestic violence",
        "grew up watching abuse", "grew up around violence",
        "used to hit my mother", "used to hit my father",
        "would hit my mother", "would hit my father",
        "witnessed abuse", "witnessed violence growing up",
        "saw my parents fight violently", "awaken a trauma", "awakened a trauma",
        "triggered a trauma", "trauma in me",
        "gave me trauma", "gave trauma", "which gave me trauma", "which gave trauma",
        "father beating", "mother beating", "beating my mother", "beating my father",
        "beating my mom", "beating my dad", "saw my father beating", "saw my mother beating",
        "witnessed my father beating", "witnessed my mother beating",
        "cant trust man", "can't trust man", "cant trust men", "can't trust men",
        "dont trust man", "don't trust man", "dont trust men", "don't trust men",
        "trust man easily", "trust men easily", "trust a man easily", "trust men easily",
        "afraid of man", "afraid of men",
    ],
    "academic_stress": [
        "exam", "exams", "assignment", "assignments", "coursework", "study", "studied",
        "cramming", "scholarship", "my grades", "results are coming out", "the test",
    ],
    "financial_stress": [
        "rent this month", "bank balance", "loan payments", "can't afford", "cant afford",
        "lost my job", "losing my job", "budget", "bills", "medical expenses", "groceries",
        "i am poor", "i'm poor", "we are poor", "my family is poor",
    ],
    "work_life_balance": [
        "work calls", "extra shifts", "commute", "work emails", "overtime",
        "never truly off duty", "no weekend to myself", "running on empty",
        "work life and family life", "work and family", "balancing work and family",
        "juggling work and family", "deal with my work life",
        "managing the household", "manage the household",
    ],
    "family_relationships": [
        "my in-laws", "my mother", "my father", "family dinner", "my siblings",
        "keeping the peace in this family", "my relatives", "treats me like a child",
        "becomes aggressive during arguments", "gets aggressive during arguments",
        "aggressive during arguments", "doesn't feel safe because someone in my family",
        "aggressive when we argue", "turns aggressive when we fight",
    ],
    "parenting_challenges": [
        "my son", "my daughter", "my child", "my kid", "my teenager", "pulling away",
        "goes straight to his room", "shuts me out",
        # New-parent / early-childcare phase — see module note above.
        "since becoming a parent", "since i became a parent", "since we became parents",
        "since having a baby", "since the baby was born", "new parent", "new mom",
        "new dad", "new mother", "new father", "juggling parenting",
        "taking care of my baby", "caring for my baby", "looking after my baby",
        "taking care of my newborn", "caring for my newborn",
    ],
    "loneliness_isolation": [
        "feel invisible", "no one notices", "haven't had a real conversation",
        "nobody really knows how i am doing", "withdrawing from friends", "lonely",
    ],
    "relationship_marital": [
        "my partner and i", "my spouse", "we keep having the same fight",
        "listens to respond rather than to understand", "the closeness between us",
    ],
    "grief_loss": [
        "we lost him", "we lost her", "since he passed", "since she passed",
        "losing my mother", "losing my father", "he's gone", "she's gone",
        "since we lost", "grief", "grieving", "miss him so much", "miss her so much",
        "after losing", "he passed", "she passed",
    ],
    "health_illness": [
        "diagnosis", "chronic pain", "test results", "my scan", "my biopsy",
        "doctor is going to say", "medication every day", "health scare",
        "chronic illness", "my symptoms",
    ],
    "career_uncertainty": [
        "sent out dozens of applications", "job search", "switching careers",
        "my career anymore", "contract ends", "stuck in a job",
        "interview went badly", "career uncertain", "career figured out",
    ],
    "social_anxiety": [
        "small talk", "speak up in a group", "rehearsed what to say",
        "hands shake", "room full of people i don't know", "declining invitations",
        "froze when everyone", "cringing at what i said", "afraid to speak up",
    ],
    "caregiving_burden": [
        "caring for my father", "caring for my mother", "take care of my grandmother",
        "caregiver", "taking care of him full time", "no one to relieve me",
        "caring for everyone else", "care for my parent",
    ],
    "sleep_issues": [
        "can't sleep", "cant sleep", "lie awake", "can't fall asleep",
        "cant fall asleep", "insomnia", "wake up at 3am", "four hours of sleep",
        "staring at the ceiling", "won't let me rest", "wont let me rest",
    ],
}


def _keyword_matches(text_lower):
    matches = []
    for category, phrases in KEYWORD_RULES.items():
        if any(phrase in text_lower for phrase in phrases):
            matches.append({"category": category, "confidence": 0.95, "source": "keyword"})
    return matches


def _ml_matches(text, already_matched_categories, threshold=0.55):
    """Thin wrapper kept for backwards compatibility with the rest of
    this module — the actual work now happens in situations_ml.py
    (pure Python, no sklearn/numpy). Wrapped in try/except so a
    missing/corrupt weights file never crashes the app, same safety
    guarantee the old joblib-based version had.

    NOTE (2026-08-29): threshold raised from 0.45 to 0.55 after a real
    false positive was observed in testing — "I can't sleep because I
    keep worrying about my future, and now I can't focus on my
    studies." (a sleep/academic-stress entry) was also tagged
    pregnancy_postpartum at 0.46 confidence. This is the small-dataset
    overfitting risk already documented at the top of this file — with
    only ~11 pregnancy examples out of 100 total rows and 916 TF-IDF
    features, a few unrelated word combinations picked up spurious
    weight. 0.55 was verified (see threshold_check.py) to fully
    eliminate this false positive on the current training_data.csv
    with zero loss of true positives. Revisit this number as more
    training examples are added.

    IMPORTANT: this threshold only matters when tier 3 (this local
    fallback) is actually the tier being used — i.e. when
    HF_API_TOKEN isn't configured, or the zero-shot API call fails.
    Once HF_API_TOKEN is working, tier 2 (zero-shot) runs instead and
    this function is never called, so this specific false positive
    shouldn't reappear as long as the token keeps working."""
    try:
        return _pure_python_ml_matches(text, already_matched_categories, threshold=threshold)
    except Exception:
        return []


# ---------------------------------------------------------------------
# Natural-language versions of each category, used ONLY when calling
# the zero-shot API. Zero-shot NLI models like bart-large-mnli work by
# checking whether the input text "entails" a hypothesis built from
# the label — feeding it a raw identifier like "past_trauma_abuse"
# produces a much weaker signal than a real phrase like "past trauma
# or abuse", since the model has no training exposure to snake_case
# tokens as meaningful language. This mapping is the fix for that.
# ---------------------------------------------------------------------
CATEGORY_LABELS = {
    "pregnancy_postpartum": "pregnancy or postpartum struggles",
    "body_image": "body image concerns",
    "eating_disorder": "disordered eating or an eating disorder",
    "self_esteem_confidence": "low self-esteem or confidence issues",
    "harassment_safety": "harassment or a personal safety concern",
    "past_trauma_abuse": "past trauma or abuse",
    "academic_stress": "academic or exam stress",
    "financial_stress": "financial stress or money worries",
    "work_life_balance": "work-life balance struggles",
    "family_relationships": "family relationship conflict",
    "parenting_challenges": "parenting challenges",
    "loneliness_isolation": "loneliness or social isolation",
    "relationship_marital": "romantic relationship or marital problems",
    "grief_loss": "grief or the loss of a loved one",
    "health_illness": "physical health or illness worries",
    "career_uncertainty": "career uncertainty or job search stress",
    "social_anxiety": "social anxiety or fear of social situations",
    "caregiving_burden": "burnout from caring for a sick or elderly family member",
    "sleep_issues": "sleep problems or insomnia",
}

_DEBUG = os.environ.get("NLP_DEBUG", "").strip() == "1"


def _debug_log(*args):
    if _DEBUG:
        print("[situations.py debug]", *args)


def _call_zero_shot_api(text, candidate_categories, threshold=0.4):
    """Calls Hugging Face's hosted zero-shot classifier. Returns a list
    of {category, confidence, source} dicts for categories scoring
    above threshold, or an empty list if HF_API_TOKEN isn't set, the
    request fails, or the response is malformed — every failure mode
    just means "let the caller fall back to the local ML model", same
    pattern as nlp.py's emotion API call.

    Set NLP_DEBUG=1 in .env to print what this function is doing —
    useful for confirming whether HF_API_TOKEN is actually being used
    and what the API returns."""
    if not candidate_categories:
        return []

    api_token = os.environ.get("HF_API_TOKEN", "").strip()
    if not api_token:
        _debug_log("no HF_API_TOKEN set — skipping zero-shot, using local ML fallback")
        return []

    # Build human-readable labels for the API call, and a reverse map
    # to translate the model's answers back to our internal category keys.
    label_to_category = {CATEGORY_LABELS.get(c, c): c for c in candidate_categories}
    candidate_labels = list(label_to_category.keys())

    payload = {
        "inputs": text,
        # multi_label=True: lets multiple categories score independently
        # (a journal entry can genuinely be "about" more than one thing)
        # instead of forcing scores to sum to 1 across all candidates.
        "parameters": {"candidate_labels": candidate_labels, "multi_label": True},
    }
    req = urllib.request.Request(
        HF_ZERO_SHOT_MODEL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as e:
        _debug_log("zero-shot API call failed:", repr(e))
        return []

    if not isinstance(result, dict) or "labels" not in result or "scores" not in result:
        _debug_log("zero-shot API returned unexpected response (model cold-starting?):", result)
        return []  # e.g. {"error": "...", "estimated_time": ...} while the model is cold-starting

    _debug_log("zero-shot raw result:", list(zip(result["labels"], [round(s, 2) for s in result["scores"]])))

    matches = []
    for label, score in zip(result["labels"], result["scores"]):
        category = label_to_category.get(label)
        if category and score >= threshold:
            matches.append({"category": category, "confidence": round(float(score), 2), "source": "zero_shot"})
    return matches


def detect_situations(text):
    """Returns a list of {category, confidence, source} dicts, most
    confident first. Empty list means nothing matched — that's normal
    for everyday journal entries that aren't "about" one of these
    specific topics."""
    text_lower = text.lower()

    keyword_results = _keyword_matches(text_lower)
    already_matched = {m["category"] for m in keyword_results}

    remaining_candidates = [
        c for c in CATEGORIES if c not in already_matched and c != "general_other"
    ]
    zero_shot_results = _call_zero_shot_api(text, remaining_candidates)

    if zero_shot_results:
        # Zero-shot succeeded (HF_API_TOKEN is set and the API responded)
        # — trust it over the small locally-trained backup, since it
        # actually understands context rather than matching keywords or
        # a ~96-example memorized pattern.
        supplementary_results = zero_shot_results
    else:
        # No HF_API_TOKEN, or the API call failed/timed out — fall back
        # to the local classifier trained on training_data.csv.
        supplementary_results = _ml_matches(text, already_matched)

    all_results = keyword_results + supplementary_results
    all_results.sort(key=lambda m: m["confidence"], reverse=True)
    return all_results