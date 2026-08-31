"""
app.py — MindMirror backend (Flask)
------------------------------------
What this gives you:
  POST /api/register    { name, email, password }  -> creates a user, logs them in
  POST /api/login        { email, password }        -> logs an existing user in
  POST /api/auth/google  { credential }              -> logs in / signs up via Google
  POST /api/logout                                   -> logs out
  POST /api/onboarding   { ageGroup, gender, wakeTime, bedTime, interests }
                                                      -> saves onboarding answers (login required)
  POST /api/analyze      { text }                    -> runs NLP, no login required
  POST /api/entries      { text }                     -> saves a journal entry (login required)
  GET  /api/entries                                   -> returns the logged-in user's history
  GET  /api/profile                                   -> returns the logged-in user's profile
                                                          (name, email, age group, gender, sleep
                                                          schedule, interests) PLUS their full
                                                          journal history in one call, so the
                                                          frontend's Profile tab can render both
                                                          the profile card and the history/trend
                                                          view from a single request.

Run:
    pip install -r requirements.txt
    python app.py

Then it's live at http://127.0.0.1:5000

NOTE ON DATABASE LOCATION — CLOUD vs LOCAL:
This app reads cloud database settings from a ".env" file (see
.env.example) as SEPARATE fields (PGHOST, PGUSER, PGPASSWORD,
PGDATABASE) rather than one connection-string line. This is
deliberate: cloud providers like Neon generate passwords that can
contain characters (@, /, %, #, etc.) that break a hand-pasted
connection-string URL if they aren't percent-encoded — SQLAlchemy's
URL.create() below builds the URL properly and escapes those
characters automatically, so this can't happen regardless of what's
in the password.

If PGHOST is NOT set, the app falls back to a local SQLite file at
C:/mindmirror-data/mindmirror.db (only visible on this one PC).

SETUP FOR CLOUD (recommended — do this once):
  1. Create a free account at https://neon.tech and a new project.
  2. On the connection details page, click "Connection parameters"
     (next to "Connection string") — this shows Host / Database /
     User / Password separately.
  3. Create a file named ".env" in this project folder (same folder
     as app.py) with those four values, one per line:
         PGHOST=ep-xxxxx.us-east-2.aws.neon.tech
         PGUSER=neondb_owner
         PGPASSWORD=your-password-exactly-as-shown
         PGDATABASE=neondb
  4. pip install -r requirements.txt
  5. Run the app as usual. Do this same ".env" step on every PC you
     want to use the app from — same PGHOST/PGUSER/etc everywhere
     means same data everywhere, no more re-registering per machine.

If you skip the .env file entirely, the app still works exactly as
before, using the local SQLite file — nothing breaks.

NOTE ON GOOGLE SIGN-IN:
/api/auth/google verifies the Google ID token by calling Google's own
public "tokeninfo" endpoint (a simple HTTPS GET request) instead of
using the `google-auth` package's local cryptographic verification.
This is deliberate: `google-auth` depends on the `cryptography`
package, which ships a compiled Rust (.pyd) binary — on some
Windows machines with an "Application Control" security policy
(common on school/work-managed laptops), that binary gets blocked
from loading, crashing the app on startup with a DLL error you can't
fix without admin rights. Calling Google's tokeninfo endpoint instead
needs no extra native dependencies at all — just Python's built-in
urllib — so it can't hit that DLL-block problem. It's slightly less
suited to very high-traffic production use (Google notes this
endpoint isn't meant for heavy volume), but is fine for an app like
this one.

If the email doesn't match an existing user, a new account is created
with no password (password_hash stays NULL — that's why the column
is nullable now).

NOTE ON get_json() GUARDS (2026-08-29 fix):
Every route below now calls `request.get_json(silent=True) or {}`
instead of a bare `request.get_json()`. Flask's get_json() returns
None (rather than raising) when the request body is missing/empty or
the client didn't send `Content-Type: application/json` — and calling
`.get(...)` on None crashes with an unhandled 500 error instead of a
clean 400 response. `silent=True` additionally stops Flask from
raising its own 400 on malformed JSON, so we can return our own
friendlier message instead. This mirrors the pattern that
google_login()/save_onboarding() already used correctly.
"""

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import URL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from nlp import analyze_text, contains_crisis_language
from condition_model import predict_condition

GOOGLE_CLIENT_ID = "273728656708-4airnra74qebgsnp6oknuedo72qq85hd.apps.googleusercontent.com"

load_dotenv(override=True)  # reads PGHOST/PGUSER/PGPASSWORD/PGDATABASE from a .env file, if present
                             # override=True: .env always wins over any stale system env var

app = Flask(__name__)

# CHANGE THIS before deploying anywhere real — this key is what keeps
# login sessions secure. For local development/demo it's fine as is.
app.config["SECRET_KEY"] = "change-this-to-something-random-later"

# Cloud database (built from separate PG* fields — see the note at the
# top of this file for why) if PGHOST is set via .env, otherwise a
# local SQLite file outside the project folder (avoids Live Server
# reload loops, since Live Server watches everything inside the
# project folder and the .db file changes on every save).
_pg_host = os.environ.get("PGHOST", "").strip()
if _pg_host:
    _db_url = URL.create(
        "postgresql+psycopg2",
        username=os.environ.get("PGUSER", "").strip(),
        password=os.environ.get("PGPASSWORD", "").strip(),
        host=_pg_host,
        database=os.environ.get("PGDATABASE", "").strip(),
        query={"sslmode": "require"},
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///C:/mindmirror-data/mindmirror.db"

db = SQLAlchemy(app)

# Lets the frontend (served separately, e.g. VS Code Live Server on
# port 5500) call this API and send/receive the login cookie.
CORS(app, supports_credentials=True, origins=[
    "http://127.0.0.1:5500", "http://localhost:5500"
])


# ---------------- Database models ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # nullable: Google-only accounts have no password

    # Onboarding answers — filled in once via age.html -> gender.html ->
    # sleep.html -> interests.html, right after registration. All
    # nullable because a brand-new user hasn't answered them yet; that's
    # also how we detect whether someone still needs the onboarding flow
    # (see `onboarded` in the login/register responses below).
    age_group = db.Column(db.String(40))
    gender = db.Column(db.String(40))
    wake_time = db.Column(db.String(10))
    bed_time = db.Column(db.String(10))
    interests = db.Column(db.Text)   # comma-separated list, e.g. "Journaling,Meditation"


class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    mood = db.Column(db.String(40))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()   # creates tables automatically on first run — see note
    # above re: deleting mindmirror.db if upgrading from an older schema.


def current_user():
    user_id = session.get("user_id")
    # db.session.get(...) is the SQLAlchemy 2.0-style replacement for the
    # legacy Query.get(...) — same behavior, no more LegacyAPIWarning.
    return db.session.get(User, user_id) if user_id else None


# ---------------- Google token verification (no google-auth dependency) ----------------

def verify_google_token(token):
    """Calls Google's public tokeninfo endpoint to verify an ID token.
    Returns the decoded claims dict on success, or None if invalid/
    expired/wrong audience. No cryptography/native dependencies —
    see the module docstring for why that matters here."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            claims = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None

    if claims.get("aud") != GOOGLE_CLIENT_ID:
        return None
    return claims


# ---------------- Auth routes ----------------

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"message": "Name, email and password are all required."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "An account with that email already exists."}), 409

    user = User(name=name, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id
    # Brand new user -> age_group is definitely still empty -> onboarded=False.
    return jsonify({"name": user.name, "email": user.email, "onboarded": bool(user.age_group)})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Incorrect email or password."}), 401

    session["user_id"] = user.id
    # If age_group is already set, this user finished onboarding before —
    # the frontend uses this to skip straight to the app instead of
    # asking age/gender/sleep/interests again.
    return jsonify({"name": user.name, "email": user.email, "onboarded": bool(user.age_group)})


@app.route("/api/auth/google", methods=["POST"])
def google_login():
    data = request.get_json(silent=True) or {}
    token = data.get("credential")
    if not token:
        return jsonify({"message": "No credential provided."}), 400

    claims = verify_google_token(token)
    if not claims:
        return jsonify({"message": "Invalid Google token."}), 401

    email = (claims.get("email") or "").strip().lower()
    name = claims.get("name") or (email.split("@")[0] if email else "Google user")

    if not email:
        return jsonify({"message": "Google account has no email."}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        # New account via Google — no password, password_hash stays NULL.
        user = User(name=name, email=email, password_hash=None)
        db.session.add(user)
        db.session.commit()

    session["user_id"] = user.id
    return jsonify({"name": user.name, "email": user.email, "onboarded": bool(user.age_group)})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out."})


# ---------------- Onboarding answers (login required) ----------------

@app.route("/api/onboarding", methods=["POST"])
def save_onboarding():
    user = current_user()
    if not user:
        return jsonify({"message": "Please log in first."}), 401

    data = request.get_json(silent=True) or {}
    user.age_group = data.get("ageGroup")
    user.gender = data.get("gender")
    user.wake_time = data.get("wakeTime")
    user.bed_time = data.get("bedTime")
    interests = data.get("interests") or []
    user.interests = ",".join(interests)

    db.session.commit()
    return jsonify({"message": "Onboarding saved."})


# ---------------- NLP route (works whether logged in or not) ----------------

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"message": "No text provided."}), 400

    return jsonify(analyze_text(text))


# ---------------- Journal entries (login required) ----------------

@app.route("/api/entries", methods=["POST"])
def save_entry():
    user = current_user()
    if not user:
        return jsonify({"message": "Please log in first."}), 401

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"message": "No text provided."}), 400

    result = analyze_text(text)
    entry = JournalEntry(user_id=user.id, text=text, mood=result["mood"])
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        "id": entry.id,
        "text": entry.text,
        "mood": entry.mood,
        # Timezone fix: append "Z" so the frontend's `new Date(...)`
        # parses this as UTC instead of local time.
        "created_at": entry.created_at.isoformat() + "Z",
        "analysis": result
    })


@app.route("/api/entries", methods=["GET"])
def list_entries():
    user = current_user()
    if not user:
        return jsonify({"message": "Please log in first."}), 401

    entries = (JournalEntry.query
               .filter_by(user_id=user.id)
               .order_by(JournalEntry.created_at.desc())
               .all())

    return jsonify([
        {
            "id": e.id,
            "text": e.text,
            "mood": e.mood,
            "created_at": e.created_at.isoformat() + "Z",
        }
        for e in entries
    ])


# ---------------- Profile (login required) ----------------

@app.route("/api/profile", methods=["GET"])
def get_profile():
    """Returns the logged-in user's profile (name, email, onboarding
    answers) PLUS their full journal history in one response, so the
    frontend's Profile tab can render the profile card and the
    history/trend view from a single fetch instead of two.

    `interests` is split back into a list here (stored comma-separated
    in the DB — see save_onboarding above) so the frontend doesn't
    need to parse it itself."""
    user = current_user()
    if not user:
        return jsonify({"message": "Please log in first."}), 401

    entries = (JournalEntry.query
               .filter_by(user_id=user.id)
               .order_by(JournalEntry.created_at.desc())
               .all())

    interests = [i for i in (user.interests or "").split(",") if i]

    return jsonify({
        "name": user.name,
        "email": user.email,
        "age_group": user.age_group,
        "gender": user.gender,
        "wake_time": user.wake_time,
        "bed_time": user.bed_time,
        "interests": interests,
        "entry_count": len(entries),
        "member_since": entries[-1].created_at.isoformat() + "Z" if entries else None,
        "entries": [
            {
                "id": e.id,
                "text": e.text,
                "mood": e.mood,
                "created_at": e.created_at.isoformat() + "Z",
            }
            for e in entries
        ],
    })


# ---------------- Condition-pattern route (separate feature, no login required) ----------------

@app.route("/api/analyze-condition", methods=["POST"])
def analyze_condition():
    """Runs the SEPARATE condition-pattern classifier (condition_model.py)
    — deliberately kept apart from /api/analyze's mood pipeline and
    situations.py's life-topic detection. Crisis language is checked
    FIRST, using the exact same deterministic check nlp.py's main
    pipeline uses (via contains_crisis_language) — if it fires, the
    condition classifier is never even called, and the frontend should
    show the same crisis response /api/analyze already gives (call
    999 / Kaan Pete Roi), not a softer ML-guessed label."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"message": "No text provided."}), 400

    if contains_crisis_language(text):
        return jsonify({"label": None, "confidence": None, "message": None, "crisis": True})

    result = predict_condition(text)
    if not result:
        return jsonify({"label": None, "confidence": None, "message": None, "crisis": False})

    result["crisis"] = False
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)