"""
test_nlp.py — regression test suite for nlp.py + situations.py
------------------------------------------------------------------
WHY THIS EXISTS: without this, every fix is "whack-a-mole" — you fix
one case, might silently break or forget to properly ship another
(this happened once already: a CRISIS_PHRASES fix was made locally
but an older, shorter version got shipped by mistake — this test
would have caught that immediately).

HOW TO USE:
    python test_nlp.py

Run this after ANY change to nlp.py, situations.py, or
training_data.csv (+ retraining). It prints PASS/FAIL for each case
and a final summary. A red FAIL means something regressed — fix it
before moving on, don't ignore it.

HOW TO ADD A NEW TEST CASE: found a new bug (like the "will to live"
one)? Once you fix it, ALSO add the exact sentence that was broken to
the relevant list below (CRISIS_CASES / SAFETY_CASES / SITUATION_CASES
/ MOOD_CASES). That way it can never silently break again.
"""

from nlp import analyze_text
from situations import detect_situations

passed = 0
failed = 0
failures = []


def check(description, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {description}")
    else:
        failed += 1
        failures.append(description)
        print(f"  FAIL  {description}")


# =====================================================================
# CRISIS DETECTION — these must ALWAYS trigger the crisis response.
# This is the highest-stakes category: a missed case here is far worse
# than a false positive, so keep adding real-world phrasings you find.
# =====================================================================
CRISIS_CASES = [
    "i dont have the will to live on",
    "I want to kill myself",
    "I don't want to live anymore",
    "there's no point in living",
    "I wish I was never born",
    "everyone would be better off without me",
    "I'm thinking about ending my life",
    "I want to disappear forever",
    "I can't take it anymore, I'm done",
]

print("\n=== Crisis detection ===")
for text in CRISIS_CASES:
    r = analyze_text(text)
    check(
        f'"{text}" -> crisis response (severe + call buttons)',
        r["severity"] == "severe" and len(r.get("call_actions", [])) >= 1,
    )

# =====================================================================
# SAFETY / HARASSMENT DETECTION — should route to SAFETY_RESPONSE,
# not a generic mood label.
# =====================================================================
SAFETY_CASES = [
    "a boy is harassing me everyday",
    "someone followed me home and I still feel shaken",
    "he won't stop messaging me after I said no",
    "my manager makes jokes about me that cross a line",
]

print("\n=== Safety / harassment detection ===")
for text in SAFETY_CASES:
    r = analyze_text(text)
    situations = r.get("situations", [])
    check(
        f'"{text}" -> harassment_safety detected',
        any(s["category"] == "harassment_safety" for s in situations),
    )

# =====================================================================
# PAST TRAUMA / ABUSE DISCLOSURE — should route to a validating,
# trauma-informed response (TRAUMA_RESPONSE), NOT the ongoing-
# harassment SAFETY_RESPONSE (different advice needed) and NOT a
# generic mood label.
# =====================================================================
TRAUMA_CASES = [
    "i was abused when i was younger. from then on i am afraid of people. i like to be alone.",
    "I was sexually abused as a child and I still have flashbacks",
    "growing up in an abusive household left me with a lot of childhood trauma",
    "i have grown up watching my mother get beaten by my father which awaken a trauma in me that i fear to get married",
    "i saw my father beating my dad which gave trauma and i can nott trust man easily.",
]

print("\n=== Past trauma / abuse disclosure ===")
for text in TRAUMA_CASES:
    r = analyze_text(text)
    situations = r.get("situations", [])
    check(
        f'"{text}" -> past_trauma_abuse detected (trauma-informed response, not generic mood)',
        any(s["category"] == "past_trauma_abuse" for s in situations),
    )

# =====================================================================
# SITUATION / TOPIC DETECTION — spot-checks across the categories in
# situations.py. Add a case here whenever a new category is added.
# =====================================================================
SITUATION_CASES = [
    ("my exams start next week and I haven't studied enough", "academic_stress"),
    ("I don't know how I'm going to cover rent this month", "financial_stress"),
    ("my mother still treats me like a child", "family_relationships"),
    ("we lost him three months ago and the house feels so empty", "grief_loss"),
    ("my chronic pain flared up again", "health_illness"),
    ("I've sent out dozens of applications and heard nothing back", "career_uncertainty"),
    ("my hands shake every time I have to speak up in a group", "social_anxiety"),
    ("caring for my father is exhausting", "caregiving_burden"),
    ("I lie awake for hours no matter how tired I am", "sleep_issues"),
    ("I feel invisible in this house, like no one notices", "loneliness_isolation"),
    ("my cg condition is very bad. i am poor. all my friends are successful.", "financial_stress"),
]

print("\n=== Situation / topic detection ===")
for text, expected_category in SITUATION_CASES:
    found = detect_situations(text)
    categories = {s["category"] for s in found}
    check(
        f'"{text}" -> "{expected_category}" detected',
        expected_category in categories,
    )

# =====================================================================
# MOOD / EMOTION SANITY CHECKS — softer checks, since exact mood
# depends on the sentiment engine (VADER/TextBlob or the HF API).
# These check the STRUCTURE is valid and obviously-wrong results
# (e.g. clearly distressed text reading as "Calm") don't happen.
# =====================================================================
MOOD_CASES = [
    # (text, moods that would be WRONG / a red flag if returned)
    ("i am unable to deal with my work life and family life", ["Bright", "Steady"]),
    ("I feel so anxious and overwhelmed about everything", ["Bright", "Steady"]),
    ("I am absolutely thrilled, today was amazing", ["Heavy"]),
    # Regression case: HF emotion model previously read this as mostly
    # "Joy" (42%) because the text mentions several positive-sounding
    # things about OTHER people (married well, studying medicine,
    # successful vet) — while the actual emotional core is the
    # writer's own sadness/inadequacy at the comparison. Fixed via
    # _apply_keyword_sanity_check() in nlp.py.
    (
        "my cg condition is very bad. i am poor. all my friends are successful. "
        "one got married to a good family, one's husband lives in abroad, one "
        "studying in private medical, one is successful vet. but once i was "
        "better student than them. how do i lessen this ache in my heart?",
        ["Bright", "Steady"],
    ),
]

print("\n=== Mood sanity checks (should NOT be these moods) ===")
for text, wrong_moods in MOOD_CASES:
    r = analyze_text(text)
    check(
        f'"{text}" -> mood is "{r["mood"]}" (not one of {wrong_moods})',
        r["mood"] not in wrong_moods,
    )

# =====================================================================
# STRUCTURAL CHECKS — every response, regardless of content, must have
# these fields with sane types/values. Catches accidental key
# renames/removals when refactoring.
# =====================================================================
print("\n=== Structural checks ===")
sample = analyze_text("just a normal day, nothing special happened")
required_keys = {
    "mood", "note", "message", "emotions", "severity",
    "show_professional_help", "professional_message", "call_actions",
    "suggestions", "situations",
}
check("response has all required keys", required_keys.issubset(sample.keys()))
check("emotions has all 5 categories", set(sample["emotions"].keys()) == {"joy", "sadness", "anxiety", "anger", "calm"})
check("emotions roughly sum to 100", 95 <= sum(sample["emotions"].values()) <= 105)
check("suggestions is a list", isinstance(sample["suggestions"], list))
check("call_actions is a list", isinstance(sample["call_actions"], list))

# =====================================================================
# SUMMARY
# =====================================================================
print(f"\n{'='*60}")
print(f"RESULT: {passed} passed, {failed} failed (out of {passed + failed})")
if failed:
    print("\nFailed cases:")
    for f in failures:
        print(f"  - {f}")
    print("\nFix these before shipping — do not ignore a FAIL here.")
else:
    print("All checks passed.")
print(f"{'='*60}\n")
