"""
nlp.py — MindMirror's NLP analysis engine (backend version)
----------------------------------------------------------
PRIMARY engine: a hosted emotion-classification model (Hugging Face's
free Inference API, model "j-hartmann/emotion-english-distilroberta-base")
called over a plain HTTPS request — no local ML library install
required. This matters specifically because this project has run into
Windows "Application Control" policies blocking locally-installed
native/compiled binaries (see the Google Sign-In note in app.py for
the same issue with `cryptography`'s Rust module) — a heavy local ML
library like `transformers`/`torch` would very likely hit the same
wall. A plain HTTPS call sidesteps that entirely.

This model actually understands SEMANTIC meaning, not just keyword
matching — so phrasing like "I'm unable to deal with my work life and
family life" (no individually "negative" words, but clearly
describing distress) gets classified correctly, which a pure
keyword/lexicon approach structurally cannot do reliably.

FALLBACK engine: if the API call fails for any reason (no API token
set, no internet, rate-limited, the model is "cold" and still
loading, or the response is malformed) — the analysis falls back to
the original approach: VADER + TextBlob (blended) for overall
valence, plus a keyword layer for identifying which emotion(s) are
present. This means the app ALWAYS produces a result, with or without
the API configured.

KEYWORD SANITY CHECK ON TOP OF THE HF MODEL: the HF model is trained
mostly on short, tweet-style text and can misread longer, nuanced
text — especially social-comparison journal entries that mention a
lot of positive words ABOUT OTHER PEOPLE ("married to a good family",
"studying in private medical", "successful vet") while the actual
emotional core is the writer's own sadness/inadequacy at the
comparison. Left unchecked, the model can score this as mostly "joy"
purely from lexical density of positive-sounding words, even though a
human reading it immediately sees the sadness. To guard against this,
after mapping the HF scores we check EMOTION_KEYWORDS for explicit
distress language in the text; if present alongside a HF "joy"
reading, we discount (not zero out — the text might still be
genuinely mixed) the joy score before picking the headline mood. See
_apply_keyword_sanity_check().

SETUP FOR THE HOSTED MODEL (optional but recommended):
  1. Create a free account at https://huggingface.co
  2. Go to Settings → Access Tokens → create a new token (Read access
     is enough)
  3. Add it to your .env file:
         HF_API_TOKEN=hf_your_token_here
  4. Restart the app. No package install needed for this part.
If you skip this, the app just uses the fallback engine — nothing
breaks.

On top of mood/emotion detection, this file also:
  - classifies a rough SEVERITY for negative moods (mild / moderate /
    severe)
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
    the normal mood pipeline — this check happens BEFORE either mood
    engine runs, and is unaffected by which one is active

BOOK COVERS: fetched live from Open Library's public cover API
(covers.openlibrary.org) using each book's ISBN-13.

GAME COVERS: fetched live from Steam's public CDN using each game's
Steam app ID.

VIDEO LINKS: link to a YouTube SEARCH results page for a specific
query rather than one fixed video — always valid, never a dead link.

NOTE ON SITUATION-AWARE SUGGESTIONS (2026-08-29):
Previously, _build_suggestions() always attached one random book and
one random game from the MOOD's pool (e.g. anxiety -> "Feeling Good" /
Stardew Valley), regardless of whether situations.py had already
detected a specific, more relevant topic (e.g. parenting_challenges,
work_life_balance). That meant a new parent writing about exhaustion
from caregiving could get a generic anxiety self-help book and a farm
simulator game — technically "for anxiety" but not actually relevant
to what they described. Now, when at least one situation category was
detected, the generic mood-pool book/game are skipped (the
situation-specific SITUATION_SUGGESTIONS tips/video below still apply,
plus each matched category can optionally define its own book/video
in SITUATION_SUGGESTIONS if one is truly relevant). The one mood-based
VIDEO is still included either way, since a short explainer video is
rarely a bad fit regardless of topic.

Install:
    pip install vaderSentiment textblob
"""

import json
import random
import urllib.error
import urllib.request

from urllib.parse import quote as _urlquote
import os

# Load .env automatically if python-dotenv is installed.
# This lets HF_API_TOKEN=... in .env work when Flask is started normally.
# override=True: matches app.py's load_dotenv(override=True) — without
# this, a stale/incorrect value already present in the current shell
# session (or inherited from a parent process) would silently win over
# a freshly-edited .env file, even after saving the file correctly.
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from huggingface_hub import InferenceClient
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from situations import detect_situations

analyzer = SentimentIntensityAnalyzer()

# ---------------------------------------------------------------------
# Hosted emotion-classification API (primary engine) — see module
# docstring for full reasoning. Model outputs: anger, disgust, fear,
# joy, neutral, sadness, surprise. Mapped down to this app's 5
# categories below; "disgust" folds partially into anger, "surprise"
# is dropped (doesn't map cleanly to any of the 5 and is rare in
# journal-style text anyway).
# ---------------------------------------------------------------------
HF_MODEL_URL = "https://api-inference.huggingface.co/models/j-hartmann/emotion-english-distilroberta-base"


def _call_hf_emotion_api(text):
    """Call Hugging Face's current Inference Providers API.

    Returns a dict of raw model label -> probability, or None if the
    API is unavailable. Failures are printed explicitly so we can tell
    whether the app is really using Hugging Face or the local fallback.
    """
    api_token = os.environ.get("HF_API_TOKEN", "").strip()

    if not api_token:
        print("[HF DEBUG] No HF_API_TOKEN found -> using local fallback")
        return None

    try:
        client = InferenceClient(
            provider="hf-inference",
            api_key=api_token,
        )

        result = client.text_classification(
            text,
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=7,
        )

        # text_classification normally returns a list of
        # TextClassificationOutput objects.
        scores = {}
        for item in result:
            label = str(item.label).lower().strip()
            score = float(item.score)
            scores[label] = score

        if not scores:
            print("[HF DEBUG] API returned no emotion scores -> using fallback")
            return None

        print("[HF DEBUG] Hugging Face SUCCESS")
        print("[HF DEBUG]", scores)
        return scores

    except Exception as exc:
        # IMPORTANT: do not silently hide the reason anymore.
        print("[HF DEBUG] Hugging Face FAILED:", repr(exc))
        return None

def _map_hf_emotions(hf_scores):
    """Maps the model's 7 raw labels onto this app's 7 display categories
    (renaming "fear"->"anxiety" and "neutral"->"calm" for consistency
    with the rest of this file), returns normalized proportions (sums
    to 1.0).

    NOTE (2026-08-29): previously this folded "disgust" into "anger"
    (at half weight) and dropped "surprise" entirely, so the UI only
    ever showed 5 fixed bars (joy/sadness/anxiety/anger/calm) no matter
    what the text actually contained. Now all 7 of the model's
    categories are kept distinct — disgust and surprise get their own
    bars when the model actually detects them, instead of being
    silently merged away or discarded. The headline MOOD (see
    CORE_MOOD_KEYS in analyze_text) still only ever picks from the
    original 5 — disgust/surprise are additional display-only
    information layered on top, not new headline moods, since
    MOOD_COPY/MESSAGES/suggestion pools don't have entries for them."""
    mapped = {
        "joy": hf_scores.get("joy", 0.0),
        "sadness": hf_scores.get("sadness", 0.0),
        "anxiety": hf_scores.get("fear", 0.0),
        "anger": hf_scores.get("anger", 0.0),
        "disgust": hf_scores.get("disgust", 0.0),
        "surprise": hf_scores.get("surprise", 0.0),
        "calm": hf_scores.get("neutral", 0.0),
    }
    total = sum(mapped.values()) or 1.0
    return {k: v / total for k, v in mapped.items()}


def _apply_keyword_sanity_check(mapped, text_lower):
    """Guards against the HF model misreading text as more "joy" than it
    should be — two related but distinct failure modes:

    1. STRONG override: long, nuanced text (esp. social-comparison
       journal entries full of positive words ABOUT OTHER PEOPLE) gets
       read as mostly joy/calm even though the emotional core is
       distress. Triggered when there are 2+ explicit distress-keyword
       hits AND joy+calm together currently dominate — we trust the
       keywords the same way the fallback engine already does, and pull
       the majority of the weight decisively into the keyword-indicated
       emotion.

    2. MILD dampening: the headline mood is already correctly a
       negative emotion (e.g. anger, from a single word like
       "irritated"), but HF's softmax still assigns joy a noticeably
       inflated share purely from spillover — this doesn't change the
       headline mood, but makes the emotion BARS shown to the user look
       wrong. Triggered when joy is NOT already the top emotion (so we
       never touch a genuinely joyful reading) and at least one distress
       keyword hit exists — moves half of joy's score into the
       keyword-indicated emotion instead of leaving it inflated.

    Returns (possibly adjusted) mapped dict, unchanged if no distress
    keywords were found at all."""
    keyword_counts = {
        emotion: _count_hits(text_lower, words)
        for emotion, words in EMOTION_KEYWORDS.items()
    }
    total_keyword_hits = sum(keyword_counts.values())
    if total_keyword_hits == 0:
        return mapped

    top_keyword_emotion = max(keyword_counts, key=keyword_counts.get)
    joy_is_top = max(mapped, key=mapped.get) == "joy"

    mapped = dict(mapped)

    if total_keyword_hits >= 2 and (mapped["joy"] + mapped["calm"]) > 0.5:
        mapped[top_keyword_emotion] = max(mapped[top_keyword_emotion], 0.6)
        remaining = 1.0 - mapped[top_keyword_emotion]
        other_keys = [k for k in mapped if k != top_keyword_emotion]
        other_total = sum(mapped[k] for k in other_keys) or 1.0
        for k in other_keys:
            mapped[k] = (mapped[k] / other_total) * remaining
    elif not joy_is_top and mapped["joy"] > 0.2:
        shift = mapped["joy"] * 0.5
        mapped["joy"] -= shift
        mapped[top_keyword_emotion] = mapped.get(top_keyword_emotion, 0) + shift
        total = sum(mapped.values()) or 1.0
        mapped = {k: v / total for k, v in mapped.items()}

    return mapped


def _hf_severity(mapped_emotions):
    top_negative = max(mapped_emotions["sadness"], mapped_emotions["anxiety"], mapped_emotions["anger"])
    if top_negative >= 0.75:
        return "severe"
    if top_negative >= 0.45:
        return "moderate"
    return "mild"


def _clean_bars_for_negative_mood(mapped, mood_key):
    """Cosmetic cleanup, applied AFTER the headline mood is already
    decided — never changes which mood was picked, only reshapes the
    displayed bar percentages. The HF model is a softmax over 7
    labels, so it near-always assigns SOME nontrivial probability to
    "joy" even on clearly negative text (e.g. "Charged" / 49% anger
    text still showing 28% joy) — which reads as visually
    contradictory in the UI once the headline mood is already
    negative. When the headline is sadness/anxiety/anger and joy's
    bar is still large, discount it into the dominant negative
    emotion's bucket."""
    if mood_key not in ("sadness", "anxiety", "anger"):
        return mapped
    if mapped["joy"] <= 0.15:
        return mapped

    mapped = dict(mapped)
    discount = mapped["joy"] * 0.6
    mapped["joy"] -= discount
    mapped[mood_key] += discount
    total = sum(mapped.values()) or 1.0
    return {k: v / total for k, v in mapped.items()}

# ---------------------------------------------------------------------
# TextBlob blend — VADER is generally better at informal text (slang,
# ALL-CAPS emphasis, negation like "not happy"), but blending in
# TextBlob's polarity score smooths out cases where VADER's lexicon
# misses a word TextBlob's does catch, and vice versa. Weighted 60/40
# toward VADER since it's the stronger signal for this kind of
# first-person journal writing. Wrapped in try/except + an
# availability flag so the app still runs on plain VADER if textblob
# isn't installed or its corpora haven't been downloaded yet — see
# requirements.txt / README for the one-time `python -m textblob.download_corpora` step.
# ---------------------------------------------------------------------
try:
    from textblob import TextBlob
    _TEXTBLOB_AVAILABLE = True
except Exception:
    _TEXTBLOB_AVAILABLE = False


def _blended_compound(text, vader_compound):
    if not _TEXTBLOB_AVAILABLE:
        return vader_compound
    try:
        textblob_polarity = TextBlob(text).sentiment.polarity  # -1..1
        return (vader_compound * 0.6) + (textblob_polarity * 0.4)
    except Exception:
        return vader_compound


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
    """A YouTube SEARCH-results link (not one fixed video) — used where
    no specific real video was verified. Always valid, never a dead
    link, but less precise than a direct link."""
    return {
        "type": "video",
        "title": title,
        "url": f"https://www.youtube.com/results?search_query={_urlquote(search_query)}",
    }


def _video_direct(title, watch_url):
    """A direct link to one SPECIFIC, real, verified video (checked via
    web search before being added here — never a guessed/fabricated
    URL). More precise than _video(), but only used where a genuinely
    good, real video was confirmed to exist."""
    return {"type": "video", "title": title, "url": watch_url}


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
    "will to live", "no will to live", "lost my will to live",
    "don't have the will to live", "dont have the will to live",
    "lost the will to live",
    "not worth living", "life isn't worth living", "life is not worth living",
    "no point in living", "no point living", "don't see the point of living",
    "dont see the point of living", "whats the point of living",
    "wish i was never born", "wish i wasn't born", "wish i wasnt born",
    "better off without me", "everyone better off without me",
    "everyone would be better off without me",
    "tired of living", "tired of life", "done with life", "done with everything",
    "nothing to live for", "no reason to keep going",
    "ready to die", "rather be dead", "rather not exist",
    "can't take it anymore", "cant take it anymore",
    "can't take this anymore", "cant take this anymore",
    "give up on life", "giving up on life",
    "thinking about death", "thoughts of dying", "thoughts of death",
    "want it all to end", "want this to end permanently",
    "disappear forever", "want to disappear forever",
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

# ---------------------------------------------------------------------
# Trauma response — used when situations.py detects "past_trauma_abuse"
# (disclosure of PAST abuse/trauma, e.g. "I was abused when I was
# younger"). Deliberately separate from SAFETY_RESPONSE above: that one
# assumes something is happening RIGHT NOW and gives advice for that
# (document it, tell someone, report it). Past-trauma disclosure needs
# different advice — validating what happened, naming that fear/
# avoidance is a common and valid trauma response, and pointing toward
# trauma-informed professional support — not "write down what happened
# with dates and times" (which reads as oddly bureaucratic for
# something from years ago).
# ---------------------------------------------------------------------
TRAUMA_RESPONSE = {
    "mood": "Heavy",
    "note": "Thank you for trusting this space with something so difficult.",
    "message": (
        "What happened to you was not your fault. Feeling afraid of people, or "
        "wanting to be alone, is a very common and understandable response to "
        "what you went through — it doesn't mean something is wrong with you."
    ),
    "emotions": {"joy": 0, "sadness": 40, "anxiety": 40, "anger": 10, "calm": 10},
    "severity": "moderate",
    "show_professional_help": True,
    "professional_message": (
        "Processing past abuse often goes much better with support than alone — "
        "a trauma-informed therapist or counselor can help in ways this app "
        "can't. Kaan Pete Roi offers free, confidential emotional support every "
        "day from 3 PM to 3 AM, and can help you think through next steps."
    ),
    "call_actions": [CALL_KAAN_PETE_ROI],
    "suggestions": [
        _tip("There's no timeline for healing from this — however you're feeling about it now is valid."),
        _tip("If and when you're ready, a trauma-informed therapist can help process this in a way that's paced to you, not rushed."),
        _tip("Small, low-pressure social contact (not forced) can help rebuild trust in people gradually, at your own speed."),
        _book("The Body Keeps the Score", "Bessel van der Kolk", "9780143127741"),
        _book("Speak", "Laurie Halse Anderson", "9780142414123"),
        _video_direct("On Grief, Loss & Trauma — Dr. K (psychiatrist)", "https://www.youtube.com/watch?v=C5qfKaVe89c"),
    ],
    "situations": [{"category": "past_trauma_abuse", "confidence": 1.0, "source": "trauma_response"}],
}

# ---------------------------------------------------------------------
# Eating-disorder response — used when situations.py detects
# "eating_disorder" (disclosure of disordered eating, body-shaming
# from family, restricting/purging/bingeing language). Kept SEPARATE
# from the generic body_image situation and the normal mood pipeline
# for a specific reason: eating disorders carry real physical health
# risk (electrolyte imbalance, cardiac strain, etc.), not just
# emotional weight — so unlike a normal "Heavy" mood entry, this
# response deliberately:
#   - pushes toward a DOCTOR, not just a mental health professional,
#     since physical monitoring matters here in a way it doesn't for
#     most other moods
#   - never surfaces a generic mood-pool book/game (which could easily
#     be food/diet/body-adjacent and land badly)
#   - keeps the book suggestion strictly body-ACCEPTANCE oriented
#     (never diet, weight-loss, or food-tracking related)
#   - gives no numeric/food/exercise guidance of any kind, in line
#     with how this is handled everywhere else in this project
# ---------------------------------------------------------------------
EATING_DISORDER_RESPONSE = {
    "mood": "Heavy",
    "note": "What you're describing carries real weight — thank you for writing it down.",
    "message": (
        "However this started, it's not your fault and it's not a personal "
        "failing. What you're describing sounds like it may be an eating "
        "disorder, which is a real and serious condition — not something to "
        "push through alone."
    ),
    "emotions": {"joy": 0, "sadness": 55, "anxiety": 25, "anger": 20, "calm": 0},
    "severity": "severe",
    "show_professional_help": True,
    "professional_message": (
        "Eating disorders can affect your body as well as your mind, so it's "
        "worth seeing a doctor for a physical check as well as talking to a "
        "mental health professional — the two matter equally here. Kaan Pete "
        "Roi offers free, confidential emotional support every day from 3 PM "
        "to 3 AM, and can help you think through next steps."
    ),
    "call_actions": [CALL_KAAN_PETE_ROI],
    "suggestions": [
        _tip("This is common, treatable, and not something to be ashamed of — many people recover fully with the right support."),
        _tip("A doctor can check in on the physical side of this too, which matters just as much as the emotional side."),
        _tip("Other people's comments about your body are about them, not a true reflection of your worth."),
        _book("The Body Is Not an Apology", "Sonya Renee Taylor", "9781626568517"),
        _video("Understanding eating disorders — a psychiatrist's perspective", "psychiatrist explains eating disorders"),
    ],
    "situations": [{"category": "eating_disorder", "confidence": 1.0, "source": "eating_disorder_response"}],
}


# Used to tell apart WHICH negative emotion(s) are present once VADER
# has already decided the text leans negative overall. Also used (see
# _apply_keyword_sanity_check above) as a sanity check on the HF model's
# joy/calm reading for longer, nuanced text.
# The 5 moods that MOOD_COPY/MESSAGES/suggestion pools are actually
# defined for. "disgust" and "surprise" (from the HF model, see
# _map_hf_emotions) are valid DISPLAY categories but never headline
# moods — there's no book/tip/video pool for "Disgust" as a mood, so
# picking it as mood_key would KeyError. Used to restrict the
# top-emotion search in analyze_text() to only these 5.
CORE_MOOD_KEYS = ("joy", "sadness", "anxiety", "anger", "calm")

EMOTION_KEYWORDS = {
    "anxiety": [
        "worried", "anxious", "afraid", "panic", "nervous", "overthink",
        "stress", "stressed", "scared", "overwhelmed", "racing",
        "worry", "uncertain", "unsure", "lack", "behind", "unprepared",
        "not ready", "pressure", "deadline", "doubt", "confused",
        "what if", "can't stop thinking", "racing thoughts",
        "unable to deal", "can't deal with", "cant deal with",
        "can't cope", "cant cope", "can't handle", "cant handle",
        "too much to handle", "can't manage", "cant manage",
        "struggling to cope", "falling apart", "can't keep up",
        "cant keep up",
    ],
    "anger": [
        "angry", "annoyed", "furious", "irritated", "frustrated", "mad",
        "resentful", "unfair", "hate", "betrayed", "fed up",
        "aggressive", "aggression",
    ],
    "sadness": [
        "sad", "down", "cry", "lonely", "lost", "empty", "hurt",
        "heavy", "numb", "worthless", "failure", "disappointed",
        "hopeless", "regret", "tired", "exhausted", "drained",
        "ache in my heart", "worse than them", "everyone is successful",
        "i am poor", "i'm poor", "better than them", "used to be better",
        "once i was better", "condition is very bad", "my condition is bad",
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
# ---------------------------------------------------------------------
# Suggestion POOLS — multiple books/videos per mood so repeated use
# doesn't always show the exact same recommendation. Tips stay fixed
# (always shown, since they're specific actionable steps, not "content
# to consume"); one book and one video are RANDOMLY chosen per request
# from these pools by _build_suggestions() below.
#
# NOTE (2026-08-29): the BOOK_POOLS and GAME_POOLS entries below are
# now only used when NO specific situation category was detected for
# this entry (see _build_suggestions). When a situation IS detected,
# its own SITUATION_SUGGESTIONS entry (further down) takes over that
# role instead, since it's tailored to the actual topic rather than
# just the mood.
#
# Video links marked "direct" point to one specific, real video —
# verified to actually exist via web search before being added here
# (never a guessed/fabricated URL). Where no specific video could be
# verified for a topic, a search-results link is used instead — still
# always valid, just less precise than a direct link.
# ---------------------------------------------------------------------
TIP_POOLS = {
    "joy": [
        _tip("Write down exactly what led to this feeling — it's a useful map for the next hard day."),
        _tip("Share this moment with someone — good feelings tend to grow when they're shared."),
    ],
    "calm": [
        _tip("Try the breathing exercise on this page to stretch this feeling a little longer."),
        _tip("A short, unhurried walk tends to pair well with this kind of headspace."),
    ],
    "anxiety": [
        _tip("Try the 4-4-4 breathing exercise below — it's built for exactly this."),
        _tip("Write down the single most worrying thought, then one small next step for it — just one."),
    ],
    "sadness": [
        _tip("Try naming one small thing that felt even slightly okay today — no pressure to feel better."),
    ],
    "anger": [
        _tip("Try writing the unfiltered version of what you'd want to say — then decide what's worth actually saying."),
        _tip("Physical movement — even 10 minutes — tends to metabolize this feeling faster than sitting with it."),
    ],
    "mixed": [
        _tip("Try journaling each feeling separately, one at a time, instead of all at once — it can untangle things."),
        _tip("The breathing exercise below can help settle things enough to think clearly."),
    ],
}

BOOK_POOLS = {
    "joy": [
        _book("The Book of Joy", "Dalai Lama & Desmond Tutu", "9780399185045"),
        _book("Atlas of the Heart", "Brené Brown", "9780399592555"),
    ],
    "calm": [
        _book("The Untethered Soul", "Michael A. Singer", "9781572245372"),
        _book("The Power of Now", "Eckhart Tolle", "9781577314806"),
    ],
    "anxiety": [
        _book("Feeling Good", "David D. Burns", "9780380810332"),
        _book("The Anxiety and Phobia Workbook", "Edmund J. Bourne", "9781626252158"),
        _book("Turtles All the Way Down", "John Green", "9780525555360"),
        _book("Every Last Word", "Tamara Ireland Stone", "9781484723601"),
    ],
    "sadness": [
        _book("Man's Search for Meaning", "Viktor Frankl", "9780807014295"),
        _book("The Body Keeps the Score", "Bessel van der Kolk", "9780143127741"),
        _book("Reasons to Stay Alive", "Matt Haig", "9780143130717"),
    ],
    "anger": [
        _book("Nonviolent Communication", "Marshall B. Rosenberg", "9781892005549"),
        _book("The Dance of Anger", "Harriet Lerner", "9780060919770"),
    ],
    "mixed": [
        _book("Atlas of the Heart", "Brené Brown", "9780399592555"),
        _book("The Untethered Soul", "Michael A. Singer", "9781572245372"),
        _book("Maybe You Should Talk to Someone", "Lori Gottlieb", "9781328662057"),
        _book("The Midnight Library", "Matt Haig", "9780525559474"),
    ],
}

GAME_POOLS = {
    "anxiety": [_game("Stardew Valley", "413150")],
    "sadness": [_game("Journey", "638230")],
}

VIDEO_POOLS = {
    "anxiety": [
        _video_direct("The Real Truth About Anxiety & ADHD — Dr. Tracey Marks", "https://www.youtube.com/watch?v=des_1dNbkfk"),
        _video("Psychiatrist explains social anxiety", "psychiatrist explains social anxiety"),
    ],
    "sadness": [
        _video_direct("3 Signs That Most Depressed People Have — Dr. Tracey Marks", "https://www.youtube.com/watch?v=eXR_EOJrXnQ"),
        _video("Psychiatrist explains low mood and depression", "psychiatrist explains low mood depression"),
    ],
    "anger": [
        _video("Managing anger, explained by a psychiatrist", "psychiatrist explains anger management"),
        _video("Anger as a secondary emotion, explained", "psychiatrist anger secondary emotion explained"),
    ],
    "mixed": [
        _video("Understanding mixed or hard-to-name feelings", "psychiatrist explains mixed emotions"),
        _video("Why you can't name what you're feeling", "psychiatrist alexithymia naming emotions"),
    ],
}


def _pick_one(pool):
    return random.choice(pool) if pool else None


def _build_suggestions(mood_key, has_situation=False):
    """Assembles one mood's suggestion list: all its fixed tips, plus
    ONE randomly-chosen video from that mood's pool (when available).

    NOTE (2026-08-29): the generic mood-pool BOOK and GAME are now only
    added when `has_situation` is False — i.e. when situations.py
    didn't detect any specific life-topic for this entry. When a
    situation WAS detected (e.g. parenting_challenges,
    work_life_balance), the caller layers on that situation's own
    SITUATION_SUGGESTIONS afterward instead, which is a much closer
    match to what the person actually described than a generic
    mood-only book/game would be. This stops cases like new-parent
    burnout getting a generic anxiety self-help book and a farm
    simulator game recommendation instead of something about new-
    parent exhaustion specifically."""
    items = list(TIP_POOLS.get(mood_key, []))

    if not has_situation:
        book = _pick_one(BOOK_POOLS.get(mood_key, []))
        if book:
            items.append(book)
        game = _pick_one(GAME_POOLS.get(mood_key, []))
        if game:
            items.append(game)

    video = _pick_one(VIDEO_POOLS.get(mood_key, []))
    if video:
        items.append(video)
    return items

# Extra, situation-specific suggestions layered ON TOP OF the mood-based
# SUGGESTIONS above when situations.py detects one of these topics.
# harassment_safety isn't here — it's handled entirely by SAFETY_RESPONSE.
#
# NOTE (2026-08-29): added a short physical-movement/rest tip to
# parenting_challenges, work_life_balance, and caregiving_burden —
# these three situations are the ones most likely to involve real
# physical exhaustion (new-parent sleep deprivation, caregiver burnout,
# overwork), where "try a breathing exercise" alone under-serves what's
# actually going on. This does NOT replace the mood-based breathing/
# journaling tips, it's additive.
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
        _book("You Are a Badass", "Jen Sincero", "9780762447695"),
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
        _tip("Even 10–15 minutes of movement or a short break away from screens can help offset the physical toll of a packed schedule."),
        _video("Burnout, explained by a psychiatrist", "psychiatrist burnout work life balance"),
    ],
    "family_relationships": [
        _tip("It can help to decide in advance which topics you're willing to discuss with certain relatives, and which you'll gently redirect."),
        _book("Adult Children of Emotionally Immature Parents", "Lindsay C. Gibson", "9781626251700"),
        _video("Difficult family relationships — a therapist's perspective", "therapist difficult family relationships boundaries"),
    ],
    "parenting_challenges": [
        _tip("Kids pulling away is often about needing space, not about you — a low-pressure shared activity (no deep talk required) can rebuild connection over time."),
        _tip("Round-the-clock caregiving takes a real physical toll — even short bursts of rest or movement when someone else can watch the baby matter."),
        _video("New-parent exhaustion and burnout, explained by a psychiatrist", "psychiatrist new parent burnout exhaustion"),
    ],
    "loneliness_isolation": [
        _tip("Even one small, low-stakes reach-out (a text, not a big conversation) can start to chip away at this."),
        _book("The Perks of Being a Wallflower", "Stephen Chbosky", "9781451696196"),
        _video("Understanding loneliness, explained by a psychiatrist", "psychiatrist loneliness isolation explains"),
    ],
    "relationship_marital": [
        _book("Nonviolent Communication", "Marshall B. Rosenberg", "9781892005549"),
        _video("Communication in relationships — Nonviolent Communication", "nonviolent communication relationship conflict explained"),
    ],
    "grief_loss": [
        _tip("There's no fixed timeline for grief — it doesn't move in a straight line, and that's normal."),
        _book("It's OK That You're Not OK", "Megan Devine", "9781622039083"),
        _video("Understanding grief, explained by a psychiatrist", "psychiatrist explains grief and loss"),
    ],
    "health_illness": [
        _tip("It can help to mention the emotional weight of this to your care team too, not just the physical symptoms."),
        _book("An Unquiet Mind", "Kay Redfield Jamison", "9780679763307"),
        _video("Coping with chronic illness — a psychologist's approach", "coping with chronic illness psychologist"),
    ],
    "career_uncertainty": [
        _tip("Try breaking the job search into one small action per day rather than measuring progress by outcomes you can't control."),
        _video("Navigating career uncertainty — a psychologist's advice", "career uncertainty psychologist advice"),
    ],
    "social_anxiety": [
        _tip("Starting with lower-stakes interactions (a short text, a quick hello) can help build tolerance before bigger ones."),
        _book("Eliza and Her Monsters", "Francesca Zappia", "9780062290166"),
        _video("Understanding social anxiety, explained by a psychiatrist", "psychiatrist explains social anxiety"),
    ],
    "caregiving_burden": [
        _tip("Caregiver burnout is real and common — your own needs matter too, not just the person you're caring for."),
        _tip("If even a short break is possible — someone else covering for an hour — it can meaningfully reduce the physical strain of constant caregiving."),
        _video("Caregiver burnout, explained by a psychologist", "caregiver burnout psychologist explains"),
    ],
    "sleep_issues": [
        _tip("A fixed wake-up time (even after a bad night) tends to help more than trying to fix bedtime directly."),
        _video("Why you can't sleep — a psychiatrist explains insomnia", "psychiatrist explains insomnia"),
    ],
}

PROFESSIONAL_HELP_MESSAGE = (
    "If this feeling has been sticking around for a while, or feels like more than "
    "you can carry on your own, it's worth talking to a mental health professional. "
    "Kaan Pete Roi offers free, confidential emotional support every day from "
    "3 PM to 3 AM."
)

# NOTE (2026-08-29): situations where prolonged exhaustion is likely to
# have a genuine PHYSICAL component too (new-parent sleep deprivation,
# caregiver burnout, an existing illness), not just an emotional one —
# for these, the professional-help nudge also mentions a doctor, not
# only a mental health professional, since the two aren't always the
# same next step.
PHYSICAL_TOLL_CATEGORIES = {"parenting_challenges", "caregiving_burden", "health_illness", "pregnancy_postpartum"}

PHYSICAL_TOLL_ADDENDUM = " Prolonged exhaustion like this can have a physical component too, so it's worth mentioning to a doctor as well."


def _count_hits(text_lower, words):
    return sum(text_lower.count(w) for w in words)


def _contains_crisis_language(text_lower):
    return any(phrase in text_lower for phrase in CRISIS_PHRASES)


def contains_crisis_language(text):
    """Public wrapper around the crisis-phrase check, for other modules
    (e.g. app.py's /api/analyze-condition route) that need to defer to
    the SAME deterministic crisis detection this file's main pipeline
    uses, instead of duplicating CRISIS_PHRASES or writing a separate
    check that could drift out of sync with this one."""
    return _contains_crisis_language(text.lower())


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

    if "past_trauma_abuse" in detected_categories:
        return dict(TRAUMA_RESPONSE)  # same reasoning — shallow copy of the shared template

    if "eating_disorder" in detected_categories:
        return dict(EATING_DISORDER_RESPONSE)  # same reasoning — shallow copy of the shared template

    hf_scores = _call_hf_emotion_api(text)

    if hf_scores:
        mapped = _map_hf_emotions(hf_scores)
        mapped = _apply_keyword_sanity_check(mapped, text_lower)

        # Headline mood only ever comes from these 5 — disgust/surprise
        # have no MOOD_COPY/MESSAGES/suggestion-pool entries, so they're
        # display-only extras layered on top, never the picked mood.
        core_emotions = [(k, mapped[k]) for k in CORE_MOOD_KEYS]
        sorted_emotions = sorted(core_emotions, key=lambda pair: pair[1], reverse=True)
        top_key, top_val = sorted_emotions[0]
        _, second_val = sorted_emotions[1]

        # "Mixed" when no single emotion clearly dominates — the top
        # two are close together and neither is a strong majority.
        if top_val < 0.55 and (top_val - second_val) < 0.15:
            mood_key = "mixed"
        else:
            mood_key = top_key

        # Cosmetic cleanup: reshape the displayed bars so they don't
        # visually contradict the headline mood we just picked (see
        # _clean_bars_for_negative_mood docstring). This never changes
        # mood_key itself, only the percentages shown.
        mapped = _clean_bars_for_negative_mood(mapped, mood_key)

        # Only show emotions with a MEANINGFUL presence in this entry —
        # not just technically nonzero. The HF model is a softmax over
        # several labels, so it almost always assigns SOME residual
        # probability (often rounding to 1-2%) to emotions that aren't
        # actually present in the text at all (e.g. "Joy 1%" on a
        # clearly negative entry) — that's model noise, not signal, and
        # showing it just clutters the bars without telling the person
        # anything true about what they wrote. >=2 was chosen as a
        # practical noise floor: real presence of an emotion the model
        # is picking up on tends to clear this easily, while 1% readings
        # are consistently just softmax leftover.
        emotions = {k: round(v * 100) for k, v in mapped.items() if round(v * 100) >= 2}

        is_negative_mood = mood_key in ("sadness", "anxiety", "anger") or (
            mood_key == "mixed" and mapped["joy"] < 0.3
        )
        severity = _hf_severity(mapped) if is_negative_mood else "none"
    else:
        # ---- fallback engine: VADER + TextBlob (blended) + keywords ----
        scores = analyzer.polarity_scores(text)
        compound = _blended_compound(text, scores["compound"])

        keyword_counts = {
            emotion: _count_hits(text_lower, words)
            for emotion, words in EMOTION_KEYWORDS.items()
        }
        total_keyword_hits = sum(keyword_counts.values())

        # ---- decide the headline mood ----
        # Order matters: explicit distress keywords (EMOTION_KEYWORDS) are
        # trusted even when VADER/TextBlob's compound score is weak or
        # neutral — phrases like "unable to deal with X" or "can't cope"
        # don't contain strongly negative individual words by themselves,
        # so lexicon-based compound scoring alone often misses them and
        # falls back to "Calm". Checking keywords BEFORE the compound
        # thresholds catches these cases.
        # NOTE: the multi-keyword-hit check runs FIRST, even before the
        # strong-positive-compound check. Text like a social-comparison
        # journal entry ("all my friends are successful... but I feel
        # this ache in my heart") can rack up a high compound score
        # purely from positive words describing OTHER people, even
        # while containing several explicit distress phrases about the
        # writer themselves. A single stray keyword shouldn't override
        # a genuinely strongly-positive compound (that's still handled
        # by the elif below, unchanged), but 2+ explicit distress hits
        # are a strong enough signal to distrust the compound score.
        if total_keyword_hits >= 2 and compound < 0.7:
            mood_key = max(keyword_counts, key=keyword_counts.get)
        elif compound >= 0.4:
            mood_key = "joy"
        elif total_keyword_hits > 0 and compound < 0.4:
            mood_key = max(keyword_counts, key=keyword_counts.get)
        elif compound <= -0.4:
            mood_key = "sadness"
        elif -0.15 <= compound <= 0.15:
            mood_key = "calm"
        else:
            mood_key = "mixed"

        # ---- build the emotion breakdown (bars in the UI) ----
        # Blend VADER's neg score with an explicit keyword-hit signal, so
        # bars stay consistent with the headline mood above even when the
        # underlying lexicon sentiment is weak. Also reduce the baseline
        # "calm" weight when distress keywords are present — a
        # grammatically neutral-sounding sentence describing real distress
        # ("unable to deal with...") shouldn't read as mostly Calm.
        emotions = {"joy": 0, "sadness": 0, "anxiety": 0, "anger": 0, "calm": 0}
        emotions["joy"] = scores["pos"] * 100

        calm_weight = 15 if total_keyword_hits > 0 else 40
        emotions["calm"] = scores["neu"] * calm_weight

        keyword_signal = min(total_keyword_hits * 25, 70)
        vader_neg_signal = scores["neg"] * 100
        negative_total = max(vader_neg_signal, keyword_signal)

        if negative_total > 0:
            if total_keyword_hits > 0:
                for emotion in ("sadness", "anxiety", "anger"):
                    share = keyword_counts[emotion] / total_keyword_hits
                    emotions[emotion] = negative_total * share
            else:
                emotions["sadness"] = negative_total

        total = sum(emotions.values()) or 1
        emotions = {k: round(v / total * 100) for k, v in emotions.items() if round(v / total * 100) >= 2}

        # ---- severity + professional-help nudge ----
        is_negative_mood = mood_key in ("sadness", "anxiety", "anger") or (mood_key == "mixed" and compound < 0)
        severity = _severity(compound) if is_negative_mood else "none"

    show_professional_help = is_negative_mood and severity in ("moderate", "severe")

    # NOTE (2026-08-29): 999 (emergency) is deliberately NOT included here,
    # even at severity="severe". "Severe" just means one negative emotion
    # scored very high on the mood model (e.g. 75%+ anxiety from writing
    # about parenting exhaustion) — that's genuinely difficult, but it is
    # NOT the same thing as an active emergency, and showing an emergency-
    # services button for every intense-but-ordinary journal entry both
    # dilutes what 999 means and can feel alarming/misplaced to someone
    # who was just venting about a hard week. 999 is reserved for
    # CRISIS_RESPONSE and SAFETY_RESPONSE above, which are only returned
    # when crisis language or an active safety threat was actually
    # detected — those already define their own call_actions directly.
    call_actions = []
    if show_professional_help:
        call_actions = [CALL_KAAN_PETE_ROI]

    professional_message = ""
    if show_professional_help:
        professional_message = PROFESSIONAL_HELP_MESSAGE
        if detected_categories & PHYSICAL_TOLL_CATEGORIES:
            professional_message += PHYSICAL_TOLL_ADDENDUM

    # ---- suggestions: mood-based, plus any matched situation's extra tips ----
    suggestions = _build_suggestions(mood_key, has_situation=bool(detected_categories))
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
        "professional_message": professional_message,
        "call_actions": call_actions,
        "suggestions": suggestions,
        "situations": detected_situations,
    }