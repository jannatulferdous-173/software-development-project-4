"""
nlp.py — MindMirror's NLP analysis engine (backend version)
----------------------------------------------------------
Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) for overall
positive/negative/neutral valence, PLUS a keyword layer to (a) figure out
WHICH negative emotion(s) are present and (b) blend them proportionally
instead of dumping the whole negative score into a single "winner"
category.

On top of the emotion breakdown, this file also:
  - classifies a rough SEVERITY for negative moods (mild / moderate /
    severe), based on how strongly negative VADER's compound score is
  - returns richer, more actionable advice: a short message, plus a
    list of STRUCTURED suggestions — each one typed so the frontend can
    render it appropriately:
        {"type": "tip",   "text": "..."}
        {"type": "book",  "title": "...", "author": "...", "cover_url": "..."}
        {"type": "game",  "title": "...", "cover_url": "..."}
        {"type": "video", "title": "...", "url": "..."}
  - flags when the message should nudge toward professional support,
    and includes "call_actions" — a list of {"label", "tel"} pairs the
    frontend renders as tappable call buttons (tel: links)
  - checks first for language suggesting active crisis / self-harm
    intent, and separately for harassment/safety language (via
    situations.py), and routes those to dedicated responses instead of
    the normal mood pipeline

BOOK COVERS: fetched live from Open Library's public cover API
(covers.openlibrary.org) using each book's ISBN-13. This is a stable,
intended-for-this-purpose public service — no images are stored in
this repo. If an ISBN is ever slightly wrong, Open Library serves a
blank placeholder rather than an error, and the frontend also treats a
failed image load as "hide the image, keep the caption" so a bad ID
never shows a broken-image icon.

GAME COVERS: fetched live from Steam's public CDN using each game's
Steam app ID (verified against the game's real store page).

VIDEO LINKS: rather than pointing to one specific YouTube video (which
can be deleted, region-locked, or just wrong), these link to a YouTube
SEARCH results page for a specific query — always valid, and surfaces
real, current videos on the topic. Where a channel is verified real
(Dr. Tracey Marks, a practicing psychiatrist with a well-known mental
health YouTube channel), her name is included in the query so her
videos surface near the top.

Install:
    pip install vaderSentiment
"""

from urllib.parse import quote as _urlquote

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from situations import detect_situations

analyzer = SentimentIntensityAnalyzer()


# ---------------------------------------------------------------------
# Small helpers for building structured suggestion entries.
# ---------------------------------------------------------------------
def _tip(text):
    return {"type": "tip", "text": text}


def _book(title, author, isbn13):
    return {
        "type": "book",
        "title": title,
        "author": author,
        "cover_url": f"https://covers.openlibrary.org/b/isbn/{isbn13}-M.jpg",
    }


def _game(title, steam_appid):
    return {
        "type": "game",
        "title": title,
        "cover_url": f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_appid}/header.jpg",
    }


def _video(title, search_query):
    return {
        "type": "video",
        "title": title,
        "url": f"https://www.youtube.com/results?search_query={_urlquote(search_query)}",
    }


CALL_KAAN_PETE_ROI = {"label": "Call Kaan Pete Roi — 09612-119911", "tel": "+8809612119911"}
CALL_999 = {"label": "Call 999 (Emergency)", "tel": "999"}

# ---------------------------------------------------------------------
# Crisis-language check — runs BEFORE any mood scoring. If any of these
# phrases show up, we skip straight to a direct, supportive message
# with tappable call buttons instead of trying to label an "emotion".
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
        "If you're in immediate danger, call 999 right now. Kaan Pete Roi "
        "also offers free, confidential emotional support every day from "
        "3 PM to 3 AM."
    ),
    "call_actions": [CALL_999, CALL_KAAN_PETE_ROI],
    "suggestions": [],
    "situations": [],
}

# ---------------------------------------------------------------------
# Safety response — used when situations.py detects "harassment_safety"
# (via keyword rules, ML backup, or both). Kept separate from the
# emotion pipeline: this is describing something happening TO the
# person, not a feeling to label — it needs safety-specific next
# steps, not a book recommendation.
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
        "Kaan Pete Roi can also help you think through what to do next, "
        "confidentially."
    ),
    "call_actions": [CALL_999, CALL_KAAN_PETE_ROI],
    "suggestions": [
        _tip("Write down what happened, with dates and times — this makes it easier to report later, and to be believed."),
        _tip("Tell someone you trust in person — a parent, teacher, or friend — even just saying it out loud is a step."),
        _tip("If it's happening online, use the platform's block and report tools; keep screenshots as evidence."),
        _tip("You are not overreacting, and this is not your fault."),
        _video("How to report harassment or bullying safely", "how to report harassment or bullying safely"),
    ],
    "situations": [{"category": "harassment_safety", "confidence": 1.0, "source": "safety_response"}],
}

# Used to tell apart WHICH negative emotion(s) are present once VADER
# has already decided the text leans negative overall.
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

MESSAGES = {
    "joy":     "This feeling is worth holding onto. It might help to notice what brought it on.",
    "sadness": "Writing the hard stuff down takes courage. You don't have to carry it alone.",
    "anxiety": "There's a lot circling in your head. Try picking apart one thought at a time.",
    "anger":   "Better out than bottled up. It might help to trace where this feeling started.",
    "calm":    "There's a steadiness in this writing. Worth holding onto, as much as you can.",
    "mixed":   "It's completely normal for several feelings to show up at once.",
}

# Structured suggestions per mood. cover_url values are fetched live at
# render time from Open Library / Steam (see module docstring).
SUGGESTIONS = {
    "joy": [
        _tip("Write down exactly what led to this feeling — it's a useful map for the next hard day."),
        _book("The Book of Joy", "Dalai Lama & Desmond Tutu", "9780399185045"),
        _tip("Share this moment with someone — good feelings tend to grow when they're shared."),
    ],
    "calm": [
        _tip("Try the breathing exercise on this page to stretch this feeling a little longer."),
        _book("The Untethered Soul", "Michael A. Singer", "9781572245372"),
        _tip("A short, unhurried walk tends to pair well with this kind of headspace."),
    ],
    "anxiety": [
        _tip("Try the 4-4-4 breathing exercise below — it's built for exactly this."),
        _tip("Write down the single most worrying thought, then one small next step for it — just one."),
        _book("Feeling Good", "David D. Burns", "9780380810332"),
        _game("Stardew Valley", "413150"),
        _video("Psychiatrist explains anxiety — Dr. Tracey Marks", "Dr Tracey Marks anxiety"),
    ],
    "sadness": [
        _tip("Try naming one small thing that felt even slightly okay today — no pressure to feel better."),
        _book("Man's Search for Meaning", "Viktor Frankl", "9780807014295"),
        _game("Journey", "638230"),
        _video("Psychiatrist explains low mood — Dr. Tracey Marks", "Dr Tracey Marks depression low mood"),
    ],
    "anger": [
        _tip("Try writing the unfiltered version of what you'd want to say — then decide what's worth actually saying."),
        _book("Nonviolent Communication", "Marshall B. Rosenberg", "9781892005549"),
        _tip("Physical movement — even 10 minutes — tends to metabolize this feeling faster than sitting with it."),
        _video("Managing anger, explained by a psychiatrist", "psychiatrist explains anger management"),
    ],
    "mixed": [
        _tip("Try journaling each feeling separately, one at a time, instead of all at once — it can untangle things."),
        _book("Atlas of the Heart", "Brené Brown", "9780399592555"),
        _tip("The breathing exercise below can help settle things enough to think clearly."),
        _video("Understanding mixed or hard-to-name feelings", "psychiatrist explains mixed emotions"),
    ],
}

# Extra, situation-specific suggestions layered ON TOP OF the mood-based
# SUGGESTIONS above when situations.py detects one of these topics.
# harassment_safety isn't here — it's handled entirely by SAFETY_RESPONSE.
SITUATION_SUGGESTIONS = {
    "pregnancy_postpartum": [
        _tip("What you're feeling is common and has a name — perinatal/postpartum mood changes are well-recognized and treatable; it's worth mentioning to your doctor or midwife."),
        _video("Postpartum depression & anxiety, explained", "postpartum depression anxiety psychiatrist explains"),
    ],
    "body_image": [
        _tip("Try limiting time on accounts/apps that make comparison worse — a small, low-effort boundary that adds up."),
        _book("The Body Is Not an Apology", "Sonya Renee Taylor", "9781626568517"),
    ],
    "self_esteem_confidence": [
        _tip("Try keeping a short running list of things you did well, however small — it's easy to only remember the misses."),
        _video("Building self-esteem — a psychologist's approach", "psychologist self esteem confidence building"),
    ],
    "academic_stress": [
        _tip("Try breaking the workload into the next single task only, not the whole exam or deadline at once."),
        _video("Managing exam stress, a psychiatrist's take", "psychiatrist exam stress anxiety tips"),
    ],
    "financial_stress": [
        _tip("If it's available, a free financial counseling service or a trusted elder's advice can help make a plan feel less overwhelming."),
        _video("Coping with financial stress and anxiety", "psychiatrist financial stress anxiety coping"),
    ],
    "work_life_balance": [
        _tip("Try picking one fixed boundary this week (e.g. no work messages after a set time) rather than trying to fix everything at once."),
        _video("Burnout, explained by a psychiatrist", "psychiatrist burnout work life balance"),
    ],
    "family_relationships": [
        _tip("It can help to decide in advance which topics you're willing to discuss with certain relatives, and which you'll gently redirect."),
        _video("Difficult family relationships — a therapist's perspective", "therapist difficult family relationships boundaries"),
    ],
    "parenting_challenges": [
        _tip("Kids pulling away is often about needing space, not about you — a low-pressure shared activity (no deep talk required) can rebuild connection over time."),
        _video("When your child pulls away — a psychologist's view", "child psychologist child pulling away parenting"),
    ],
    "loneliness_isolation": [
        _tip("Even one small, low-stakes reach-out (a text, not a big conversation) can start to chip away at this."),
        _video("Understanding loneliness, explained by a psychiatrist", "psychiatrist loneliness isolation explains"),
    ],
    "relationship_marital": [
        _book("Nonviolent Communication", "Marshall B. Rosenberg", "9781892005549"),
        _video("Communication in relationships — Nonviolent Communication", "nonviolent communication relationship conflict explained"),
    ],
}

PROFESSIONAL_HELP_MESSAGE = (
    "If this feeling has been sticking around for a while, or feels like more than "
    "you can carry on your own, it's worth talking to a mental health professional. "
    "Kaan Pete Roi offers free, confidential emotional support every day from "
    "3 PM to 3 AM."
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
          severity, show_professional_help, professional_message, call_actions,
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
        mood_key = max(keyword_counts, key=keyword_counts.get) if total_keyword_hits > 0 else "sadness"
    elif -0.15 <= compound <= 0.15:
        mood_key = "calm"
    else:
        mood_key = "mixed"

    # ---- build the emotion breakdown (bars in the UI) ----
    emotions = {"joy": 0, "sadness": 0, "anxiety": 0, "anger": 0, "calm": 0}
    emotions["joy"] = scores["pos"] * 100
    emotions["calm"] = scores["neu"] * 40

    if scores["neg"] > 0:
        if total_keyword_hits > 0:
            for emotion in ("sadness", "anxiety", "anger"):
                share = keyword_counts[emotion] / total_keyword_hits
                emotions[emotion] = scores["neg"] * 100 * share
        else:
            emotions["sadness"] = scores["neg"] * 100

    total = sum(emotions.values()) or 1
    emotions = {k: round(v / total * 100) for k, v in emotions.items()}

    # ---- severity + professional-help nudge ----
    is_negative_mood = mood_key in ("sadness", "anxiety", "anger") or (mood_key == "mixed" and compound < 0)
    severity = _severity(compound) if is_negative_mood else "none"
    show_professional_help = is_negative_mood and severity in ("moderate", "severe")

    call_actions = []
    if show_professional_help:
        call_actions = [CALL_999, CALL_KAAN_PETE_ROI] if severity == "severe" else [CALL_KAAN_PETE_ROI]

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
        "call_actions": call_actions,
        "suggestions": suggestions,
        "situations": detected_situations,
    }
