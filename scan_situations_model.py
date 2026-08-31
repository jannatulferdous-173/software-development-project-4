"""
scan_situations_model.py
---------------------------
Checks situations_model.joblib WITHOUT unpickling it (so it works even
though sklearn/numpy are blocked on this machine). A joblib/pickle file
stores plain Python strings as readable bytes internally, so we can just
scan the raw file for known label names to tell which model is really
saved there — no sklearn import, no upload needed.

Usage:
    python scan_situations_model.py
"""

import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "situations_model.joblib")

SITUATIONS_LABELS = [
    "academic_stress", "financial_stress", "grief_loss",
    "relationship_issues", "work_stress", "family_conflict",
    "health_anxiety", "loneliness", "self_esteem", "future_uncertainty",
]

CONDITION_LABELS = [
    "Depression", "Anxiety", "Bipolar", "Suicide",
    "Stress", "Personality disorder", "Normal",
]

if not os.path.exists(PATH):
    print(f"'{PATH}' not found.")
    raise SystemExit

with open(PATH, "rb") as f:
    raw = f.read()

# Decode ignoring errors so binary pickle framing bytes don't crash this —
# we only care about the readable ASCII label strings mixed in.
text = raw.decode("latin-1", errors="ignore")

found_situations = [lbl for lbl in SITUATIONS_LABELS if lbl in text]
found_condition = [lbl for lbl in CONDITION_LABELS if lbl in text]

print(f"File size: {len(raw)} bytes\n")
print("Situations-style labels found:", found_situations if found_situations else "NONE")
print("Condition-style labels found:", found_condition if found_condition else "NONE")

print("\n--- VERDICT ---")
if found_situations and not found_condition:
    print("✅ This file looks correct — it's situations.py's own life-topic model. No action needed.")
elif found_condition and not found_situations:
    print("⚠️ This file has been OVERWRITTEN with the condition-classifier's labels.")
    print("   Fix: delete situations_model.joblib and re-run train_situations.py")
    print("   (against training_data.csv, NOT cleaned_mental_health_data.csv).")
elif found_situations and found_condition:
    print("⚠️ Both label sets found — unusual. Paste this full output back so I can take a closer look.")
else:
    print("Neither known label set was found as plain text. This could mean the labels use")
    print("different exact wording than my guesses above, or the file uses a compressed/binary")
    print("pickle protocol. Paste this full output back and, if you know the actual category")
    print("names situations.py uses, tell me and I'll adjust the scan.")
