"""
nlp.py — MindMirror's NLP analysis engine (backend version)
----------------------------------------------------------
This replaces the frontend's simple word-counting LEXICON with a
real, established sentiment-analysis tool: VADER (Valence Aware
Dictionary and sEntiment Reasoner). Unlike plain keyword counting,
VADER actually understands:

  - negation:      "not happy" is scored differently from "happy"
  - intensifiers:  "very happy" scores stronger than "happy"
  - emphasis:      "SO happy!!" scores stronger than "so happy"

VADER gives an overall positive/negative/neutral score (it can't
tell anxiety from anger from sadness on its own), so this file
still uses a small keyword list — same idea as the frontend's
LEXICON — but only to decide WHICH negative emotion VADER's
negative score most likely reflects. That's a reasonable, honest
middle ground between "plain word counting" and a full deep-
learning model.

Install:
    pip install vaderSentiment
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

# Used only to tell apart WHICH negative emotion is present once
# VADER has already decided the text leans negative overall.
EMOTION_KEYWORDS = {
    "anxiety": ["worried", "anxious", "afraid", "panic", "nervous", "overthink",
                "stress", "scared", "overwhelmed", "racing"],
    "anger":   ["angry", "annoyed", "furious", "irritated", "frustrated", "mad", "resentful"],
    "sadness": ["sad", "down", "cry", "lonely", "lost", "tired", "empty", "hurt",
                "heavy", "numb"],
}

MOOD_COPY = {
    "joy":     {"word": "Bright",    "note": "There's a clear thread of positivity in the writing."},
    "sadness": {"word": "Heavy",     "note": "Something seems to be weighing on you."},
    "anxiety": {"word": "Unsettled", "note": "The thoughts seem to be moving pretty fast."},
    "anger":   {"word": "Charged",   "note": "Something seems to be sitting under the surface."},
    "calm":    {"word": "Steady",    "note": "The tone of the writing feels grounded and slow."},
    "mixed":   {"word": "Mixed",     "note": "A few different feelings are showing up together."},
}

MESSAGES = {
    "joy":     "This feeling is worth holding onto. It might help to notice what brought it on.",
    "sadness": "Writing the hard stuff down takes courage. Sharing it with someone you trust could help too.",
    "anxiety": "There's a lot circling in your head. Try picking apart one thought at a time.",
    "anger":   "Better out than bottled up. It might help to trace where this feeling started.",
    "calm":    "There's a steadiness in this writing. Worth holding onto, as much as you can.",
    "mixed":   "It's completely normal for several feelings to show up at once.",
}


def _guess_negative_emotion(text_lower):
    """Counts keyword hits per negative-emotion category and returns
    whichever one shows up most. Falls back to 'sadness' if none of
    the keywords are present but VADER still says it's negative."""
    counts = {emotion: 0 for emotion in EMOTION_KEYWORDS}
    for emotion, words in EMOTION_KEYWORDS.items():
        for word in words:
            counts[emotion] += text_lower.count(word)

    best_emotion = max(counts, key=counts.get)
    return best_emotion if counts[best_emotion] > 0 else "sadness"


def analyze_text(text):
    """Main entry point. Takes raw journal text, returns a dict shaped
    exactly like the frontend's analyzeText() output, so it's a drop-in
    replacement:
        { mood, note, message, emotions: {joy, sadness, anxiety, anger, calm} }
    """
    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]          # -1 (very negative) .. +1 (very positive)
    text_lower = text.lower()

    if compound >= 0.4:
        mood_key = "joy"
    elif compound <= -0.4:
        mood_key = _guess_negative_emotion(text_lower)
    elif -0.15 <= compound <= 0.15:
        mood_key = "calm"
    else:
        mood_key = "mixed"

    # Build a percentage breakdown across all 5 categories, for the
    # emotion bars in the UI.
    emotions = {"joy": 0, "sadness": 0, "anxiety": 0, "anger": 0, "calm": 0}
    emotions["joy"] = round(scores["pos"] * 100)
    emotions["calm"] = round(scores["neu"] * 40)  # scaled down so neutral doesn't dominate every result
    if compound < 0:
        emotions[_guess_negative_emotion(text_lower)] = round(scores["neg"] * 100)

    total = sum(emotions.values()) or 1
    emotions = {k: round(v / total * 100) for k, v in emotions.items()}

    copy = MOOD_COPY[mood_key]
    return {
        "mood": copy["word"],
        "note": copy["note"],
        "message": MESSAGES[mood_key],
        "emotions": emotions,
    }
