"""
check_situations_model.py — one-time sanity check
----------------------------------------------------
Run this to confirm situations_model.joblib still has the RIGHT
label set (life-topic categories for situations.py's tier-3 fallback)
and wasn't accidentally overwritten by the group member's original
train_condition.py (which used to point at this same filename before
we fixed MODEL_PATH to condition_model.joblib).

Usage:
    python check_situations_model.py
"""

import os
import joblib

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "situations_model.joblib")

if not os.path.exists(PATH):
    print(f"'{PATH}' not found — nothing to check (situations.py will just skip its tier-3 ML fallback).")
    raise SystemExit

bundle = joblib.load(PATH)

print("Keys in the saved bundle:", list(bundle.keys()))

if "mlb" in bundle:
    classes = list(bundle["mlb"].classes_)
    print("\nClasses found in situations_model.joblib:")
    for c in classes:
        print(" -", c)

    # Heuristic: situations.py's own labels are lowercase_with_underscores
    # life-topic categories. The group member's condition dataset labels
    # are capitalized clinical-sounding words.
    looks_like_situations = any("_" in c or c.islower() for c in classes)
    looks_like_condition = any(c in {"Depression", "Anxiety", "Bipolar", "Suicide",
                                       "Stress", "Normal", "Personality disorder"} for c in classes)

    print("\n--- VERDICT ---")
    if looks_like_condition and not looks_like_situations:
        print("⚠️  This file has been OVERWRITTEN by the condition-classifier script.")
        print("    It now holds Depression/Anxiety/Bipolar-style labels instead of")
        print("    situations.py's life-topic categories (academic_stress, grief_loss, etc).")
        print("    Fix: delete this file and re-run train_situations.py (against")
        print("    training_data.csv, NOT cleaned_mental_health_data.csv) to regenerate it.")
    elif looks_like_situations and not looks_like_condition:
        print("✅  This file looks correct — life-topic categories, not clinical labels.")
        print("    situations.py's tier-3 fallback should be working as intended.")
    else:
        print("Ambiguous result — please paste this script's full output back so I can check.")
else:
    print("\nNo 'mlb' key found in the bundle — this doesn't match either expected format.")
    print("Please paste this full output back so I can take a look.")
