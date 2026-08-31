"""
encode_for_upload.py
----------------------
Converts situations_model.joblib into a plain-text base64 file
(situations_model_b64.txt) so it can be uploaded through a chat
interface that only accepts text-like files.

This uses ONLY Python's built-in base64/os modules — no numpy,
pandas, or scikit-learn — so it will run even with sklearn/numpy
blocked by Smart App Control.

Usage:
    python encode_for_upload.py
"""

import base64
import os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "situations_model.joblib")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "situations_model_b64.txt")

if not os.path.exists(SRC):
    print(f"Couldn't find {SRC} — make sure this script is in the same folder as situations_model.joblib.")
    raise SystemExit

with open(SRC, "rb") as f:
    raw = f.read()

encoded = base64.b64encode(raw)

with open(DST, "wb") as f:
    f.write(encoded)

print(f"Done. Wrote {DST} ({len(encoded)} bytes).")
print("Upload that .txt file in the chat.")
