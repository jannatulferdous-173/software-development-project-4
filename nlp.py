"""
nlp.py — MindMirror's NLP analysis engine (backend version)
----------------------------------------------------------
Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) for overall
positive/negative/neutral valence, PLUS a keyword layer to (a) figure out
WHICH negative emotion(s) are present and (b) blend them proportionally
instead of dumping the whole negative score into a single "winner"
category. That's what makes results like "Mixed" more accurate — if a
piece of writing has both anxiety and sadness cues, both bars move
instead of one emotion swallowing the whole score.

On top of the emotion breakdown, this file now also:
  - classifies a rough SEVERITY for negative moods (mild / moderate /
    severe), based on how strongly negative VADER's compound score is
  - returns richer, more actionable advice per mood: a short message,
    plus 2-4 concrete suggestions (breathing/journaling prompts, a
    well-known book, a calming activity/app)
  - flags when the message should nudge toward professional support,
    and includes a verified Bangladesh helpline (Kaan Pete Roi) for
    that nudge
  - checks first for language suggesting active crisis / self-harm
    intent, and if found, skips all mood-scoring and returns a direct,
    supportive message pointing to crisis resources

Install:
    pip install vaderSentiment
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from situations import detect_situations

analyzer = SentimentIntensityAnalyzer()

# ---------------------------------------------------------------------
# Crisis-language check — runs BEFORE any mood scoring. If any of these
# phrases show up, we skip straight to a direct, supportive response
# with helpline info instead of trying to label an "emotion".
# Keep this list to clear, unambiguous phrases only (avoid single common
# words that would false-positive on ordinary journal entries).
# ---------------------------------------------------------------------
CRISIS_PHRASES = [
    "kill myself", "killing myself", "end my life", "ending my life",
    "want to die", "wanted to die", "don't want to live", "dont want to live",
    "no reason to live", "suicidal", "suicide", "self harm", "self-harm",
    "hurt myself", "hurting myself", "cut myself", "cutting myself",
    "better off dead", "can't go on", "cant go on",
]

CRISIS_RESPONSE = {
    "mood": "Heavy",
    "note": "What you wrote sounds really painful.",
    "message": (
        "Please don't sit with this alone. It's worth talking to someone "
        "right now — a trusted person, or a trained listener who can "
        "help in the moment."
    ),
    "emotions": {"joy": 0, "sadness": 60, "anxiety": 40, "anger": 0, "calm": 0},
    "severity": "severe",
    "show_professional_help": True,
    "professional_message": (
        "In Bangladesh, Kaan Pete Roi offers free, confidential emotional "
        "support every day from 3 PM to 3 AM: 09612-119911. "
        "For an immediate emergency, call the national emergency service: 999."
    ),
    "suggestions": [],
    "situations": [],
}

# ---------------------------------------------------------------------
# Safety response — used when situations.py detects "harassment_safety"
# (via its keyword rules, its ML backup, or both). This is DELIBERATELY
# separate from the emotion pipeline below: text like "a boy is
# harassing me every day" is not really describing an emotion to be
# labeled (VADER just sees generic negativity and, with no
# "sad"/"anxious"/etc keyword present, used to default to plain
# sadness) — it's describing something happening TO the person that
# needs safety-specific next steps, not a book recommendation.
# ---------------------------------------------------------------------
SAFETY_RESPONSE = {
    "mood": "Unsettled",
    "note": "What you're describing sounds like it's happening TO you, not just a feeling to sit with.",
    "message": (
        "No one has the right to make you feel unsafe. This is worth telling "
        "someone about, not carrying quietly."
    ),
    "emotions": {"joy": 0, "sadness": 30, "anxiety": 40, "anger": 30, "calm": 0},
    "severity": "moderate",
    "show_professional_help": True,
    "professional_message": (
        "If you're in immediate danger, call 999. Otherwise, telling a "
        "trusted adult, teacher, or authority figure is a strong first step — "
        "Kaan Pete Roi (09612-119911, daily 3 PM–3 AM) can also help you "
        "think through what to do next, confidentially."
    ),
    "suggestions": [
        "Write down what happened, with dates and times — this makes it easier to report later, and to be believed.",
        "Tell someone you trust in person — a parent, teacher, or friend — even just saying it out loud is a step.",
        "If it's happening online, use the platform's block and report tools; keep screenshots as evidence.",
        "You are not overreacting, and this is not your fault.",
    ],
    "situations": [{"category": "harassment_safety", "confidence": 1.0, "source": "safety_response"}],
}

# ---------------------------------------------------------------------
# Extra, situation-specific tips layered ON TOP OF the mood-based
# SUGGESTIONS below when situations.py detects one of these topics.
# Kept short (1-2 each) since they're appended, not a replacement.
# harassment_safety isn't here — it's handled entirely by
# SAFETY_RESPONSE above instead.
# ---------------------------------------------------------------------
SITUATION_SUGGESTIONS = {
    "pregnancy_postpartum": [
        "What you're feeling is common and has a name — perinatal/postpartum anxiety and mood changes are well-recognized and treatable; it's worth mentioning to your doctor or midwife at your next visit.",
    ],
    "body_image": [
        "Try limiting time on accounts/apps that make comparison worse — a small, low-effort boundary that adds up.",
        "Book: \"The Body Is Not an Apology\" by Sonya Renee Taylor.",
    ],
    "self_esteem_confidence": [
        "Try keeping a short running list of things you did well, however small — it's easy to only remember the misses.",
    ],
    "academic_stress": [
        "Try breaking the workload into the next single task only, not the whole exam or deadline at once.",
    ],
    "financial_stress": [
        "If it's available, a free financial counseling service or even a trusted elder's advice can help make a plan feel less overwhelming.",
    ],
    "work_life_balance": [
        "Try picking one fixed boundary this week (e.g. no work messages after a set time) rather than trying to fix everything at once.",
    ],
    "family_relationships": [
        "It can help to decide in advance which topics you're willing to discuss with certain relatives, and which you'll gently redirect.",
    ],
    "parenting_challenges": [
        "Kids pulling away is often about needing space, not about you — a low-pressure shared activity (no deep talk required) can rebuild connection over time.",
    ],
    "loneliness_isolation": [
        "Even one small, low-stakes reach-out (a text, not a big conversation) can start to chip away at this.",
    ],
    "relationship_marital": [
        "Book: \"Nonviolent Communication\" by Marshall Rosenberg — useful for conversations that keep going in circles.",
    ],
}

# Used to tell apart WHICH negative emotion(s) are present once VADER
# has already decided the text leans negative overall. A word can only
# live in one category, but a sentence can (and often does) hit words
# from more than one — that's what lets the blend below produce a real
# "Mixed" result instead of always picking one winner.
EMOTION_KEYWORDS = {
    "anxiety": [
        "worried", "anxious", "afraid", "panic", "nervous", "overthink",
        "stress", "stressed", "scared", "overwhelmed", "racing",
        "worry", "uncertain", "unsure", "lack", "behind", "unprepared",
        "not ready", "pressure", "deadline", "doubt", "confused",
        "what if", "can't stop thinking", "racing thoughts",
    ],
    "anger": [
        "angry", "annoyed", "furious", "irritated", "frustrated", "mad",
        "resentful", "unfair", "hate", "betrayed", "fed up",
    ],
    "sadness": [
        "sad", "down", "cry", "lonely", "lost", "empty", "hurt",
        "heavy", "numb", "worthless", "failure", "disappointed",
        "hopeless", "regret", "tired", "exhausted", "drained",
    ],
}

MOOD_COPY = {
    "joy":     {"word": "Bright",    "note": "There's a clear thread of positivity in the writing."},
    "sadness": {"word": "Heavy",     "note": "Something seems to be weighing on you."},
    "anxiety": {"word": "Unsettled", "note": "The thoughts seem to be moving pretty fast."},
    "anger":   {"word": "Charged",   "note": "Something seems to be sitting under the surface."},
    "calm":    {"word": "Steady",    "note": "The tone of the writing feels grounded and slow."},
    "mixed":   {"word": "Mixed",     "note": "A few different feelings are showing up together."},
}

# Base one-line message per mood — always shown.
MESSAGES = {
    "joy":     "This feeling is worth holding onto. It might help to notice what brought it on.",
    "sadness": "Writing the hard stuff down takes courage. You don't have to carry it alone.",
    "anxiety": "There's a lot circling in your head. Try picking apart one thought at a time.",
    "anger":   "Better out than bottled up. It might help to trace where this feeling started.",
    "calm":    "There's a steadiness in this writing. Worth holding onto, as much as you can.",
    "mixed":   "It's completely normal for several feelings to show up at once.",
}

# Concrete, low-effort suggestions per mood: a mix of an in-app action,
# a widely-known book, and an activity/app — not medical advice, just
# gentle next steps. Keep book picks to well-known, broadly-recommended
# titles rather than anything hyper-specific to one condition.
SUGGESTIONS = {
    "joy": [
        "Write down exactly what led to this feeling — it's a useful map for the next hard day.",
        "Book: \"The Book of Joy\" by the Dalai Lama and Desmond Tutu.",
        "Share this moment with someone — good feelings tend to grow when they're shared.",
    ],
    "calm": [
        "Try the breathing exercise on this page to stretch this feeling a little longer.",
        "Book: \"The Untethered Soul\" by Michael A. Singer.",
        "A short, unhurried walk tends to pair well with this kind of headspace.",
    ],
    "anxiety": [
        "Try the 4-4-4 breathing exercise below — it's built for exactly this.",
        "Write down the single most worrying thought, then one small next step for it — just one.",
        "Book: \"Feeling Good\" by David D. Burns, or the app Headspace for guided calm-downs.",
        "If racing thoughts are frequent, a mental health professional can teach tools that help long-term.",
    ],
    "sadness": [
        "Try naming one small thing that felt even slightly okay today — no pressure to feel better.",
        "Book: \"Man's Search for Meaning\" by Viktor Frankl.",
        "A gentle, low-stakes game (something like Stardew Valley or a puzzle app) can help without demanding much energy.",
        "If this heaviness sticks around for more than a couple of weeks, talking to a mental health professional is a good next step.",
    ],
    "anger": [
        "Try writing the unfiltered version of what you'd want to say — then decide what's worth actually saying.",
        "Book: \"Rewire Your Anxious Brain\" (covers anger's overlap with stress too), or \"Nonviolent Communication\" by Marshall Rosenberg.",
        "Physical movement — even 10 minutes — tends to metabolize this feeling faster than sitting with it.",
    ],
    "mixed": [
        "Try journaling each feeling separately, one at a time, instead of all at once — it can untangle things.",
        "Book: \"Atlas of the Heart\" by Brené Brown, great for naming mixed or hard-to-place feelings.",
        "The breathing exercise below can help settle things enough to think clearly.",
    ],
}

PROFESSIONAL_HELP_MESSAGE = (
    "If this feeling has been sticking around for a while, or feels like more than "
    "you can carry on your own, it's worth talking to a mental health professional. "
    "In Bangladesh, Kaan Pete Roi offers free, confidential emotional support every "
    "day from 3 PM to 3 AM: 09612-119911."
)


def _count_hits(text_lower, words):
    return sum(text_lower.count(w) for w in words)


def _contains_crisis_language(text_lower):
    return any(phrase in text_lower for phrase in CRISIS_PHRASES)


def _severity(compound):
    """Rough severity tier for negative-leaning text. Only meaningful
    when compound < 0 — callers should ignore this for joy/calm."""
    if compound <= -0.7:
        return "severe"
    if compound <= -0.4:
        return "moderate"
    return "mild"


def analyze_text(text):
    """Main entry point. Takes raw journal text, returns a dict:
        {
          mood, note, message, emotions,
          severity, show_professional_help, professional_message,
          suggestions, situations
        }
    """
    text_lower = text.lower()

    if _contains_crisis_language(text_lower):
        return dict(CRISIS_RESPONSE)  # shallow copy so callers can't mutate the shared template

    detected_situations = detect_situations(text)
    detected_categories = {s["category"] for s in detected_situations}

    if "harassment_safety" in detected_categories:
        return dict(SAFETY_RESPONSE)  # same reasoning — shallow copy of the shared template

    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]

    keyword_counts = {
        emotion: _count_hits(text_lower, words)
        for emotion, words in EMOTION_KEYWORDS.items()
    }
    total_keyword_hits = sum(keyword_counts.values())

    # ---- decide the headline mood ----
    if compound >= 0.4:
        mood_key = "joy"
    elif compound <= -0.4:
        # pick whichever negative emotion has the most keyword hits;
        # falls back to sadness if nothing specific was detected
        mood_key = max(keyword_counts, key=keyword_counts.get) if total_keyword_hits > 0 else "sadness"
    elif -0.15 <= compound <= 0.15:
        mood_key = "calm"
    else:
        mood_key = "mixed"

    # ---- build the emotion breakdown (bars in the UI) ----
    # Instead of handing the whole negative score to one "winner"
    # category, split it proportionally across every negative emotion
    # that actually showed up in the text.
    emotions = {"joy": 0, "sadness": 0, "anxiety": 0, "anger": 0, "calm": 0}
    emotions["joy"] = scores["pos"] * 100
    emotions["calm"] = scores["neu"] * 40  # scaled down so neutral doesn't dominate every result

    if scores["neg"] > 0:
        if total_keyword_hits > 0:
            for emotion in ("sadness", "anxiety", "anger"):
                share = keyword_counts[emotion] / total_keyword_hits
                emotions[emotion] = scores["neg"] * 100 * share
        else:
            # negative tone with no specific keyword cues — default to sadness
            emotions["sadness"] = scores["neg"] * 100

    total = sum(emotions.values()) or 1
    emotions = {k: round(v / total * 100) for k, v in emotions.items()}

    # ---- severity + professional-help nudge ----
    is_negative_mood = mood_key in ("sadness", "anxiety", "anger") or (mood_key == "mixed" and compound < 0)
    severity = _severity(compound) if is_negative_mood else "none"
    show_professional_help = is_negative_mood and severity in ("moderate", "severe")

    # ---- suggestions: mood-based, plus any matched situation's extra tips ----
    suggestions = list(SUGGESTIONS[mood_key])
    for category in detected_categories:
        suggestions.extend(SITUATION_SUGGESTIONS.get(category, []))

    copy = MOOD_COPY[mood_key]
    return {
        "mood": copy["word"],
        "note": copy["note"],
        "message": MESSAGES[mood_key],
        "emotions": emotions,
        "severity": severity,
        "show_professional_help": show_professional_help,
        "professional_message": PROFESSIONAL_HELP_MESSAGE if show_professional_help else "",
        "suggestions": suggestions,
        "situations": detected_situations,
    }