"""
app.py — MindMirror backend (Flask)
------------------------------------
What this gives you:
  POST /api/register   { name, email, password }  -> creates a user, logs them in
  POST /api/login       { email, password }        -> logs an existing user in
  POST /api/logout                                  -> logs out
  POST /api/analyze     { text }                    -> runs NLP, no login required
  POST /api/entries     { text }                    -> saves a journal entry (login required)
  GET  /api/entries                                  -> returns the logged-in user's history

Run:
    pip install -r requirements.txt
    python app.py

Then it's live at http://127.0.0.1:5000
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from nlp import analyze_text

app = Flask(__name__)

# CHANGE THIS before deploying anywhere real — this key is what keeps
# login sessions secure. For local development/demo it's fine as is.
app.config["SECRET_KEY"] = "change-this-to-something-random-later"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mindmirror.db"
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
    password_hash = db.Column(db.String(255), nullable=False)


class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    mood = db.Column(db.String(40))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()   # creates mindmirror.db automatically on first run


def current_user():
    user_id = session.get("user_id")
    return User.query.get(user_id) if user_id else None


# ---------------- Auth routes ----------------

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
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
    return jsonify({"name": user.name, "email": user.email})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Incorrect email or password."}), 401

    session["user_id"] = user.id
    return jsonify({"name": user.name, "email": user.email})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out."})


# ---------------- NLP route (works whether logged in or not) ----------------

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
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

    data = request.get_json()
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
        "created_at": entry.created_at.isoformat(),
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
        {"id": e.id, "text": e.text, "mood": e.mood, "created_at": e.created_at.isoformat()}
        for e in entries
    ])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
