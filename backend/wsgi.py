"""Entry point for Render: the main app plus "Verify with Google".

Google verification works like the LinkedIn one: the student signs in with
Google (OpenID Connect) and we cross-check the Google name and email with the
SkillSwap profile. Needs GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.
"""
import os
import secrets
from urllib.parse import urlencode

import requests as http
from flask import jsonify, redirect, request
from flask_jwt_extended import jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import inspect, text

from app import app, db, error, frontend_url, my_id, names_match, utcnow, User

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
USERINFO_URL = os.getenv("GOOGLE_USERINFO_URL", "https://openidconnect.googleapis.com/v1/userinfo")
signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="google-verify")

COLUMNS = {
    "google_sub": "VARCHAR(100)",
    "google_name": "VARCHAR(150) DEFAULT ''",
    "google_email": "VARCHAR(150) DEFAULT ''",
    "google_status": "VARCHAR(20) NOT NULL DEFAULT 'unverified'",
    "google_email_match": "BOOLEAN DEFAULT FALSE",
    "google_checked_at": "TIMESTAMP",
}

with app.app_context():
    existing = {c["name"] for c in inspect(db.engine).get_columns("users")}
    with db.engine.begin() as conn:
        for name, ddl in COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
    db.engine.dispose()


def enabled():
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def redirect_uri():
    return os.getenv("GOOGLE_REDIRECT_URI") or request.host_url.rstrip("/") + "/api/google/callback"


def google_row(user_id):
    return db.session.execute(text(
        "SELECT google_status, google_name, google_email, google_email_match, google_checked_at "
        "FROM users WHERE id = :id"), {"id": user_id}).first()


@app.get("/api/google/config")
def google_config():
    return jsonify({"enabled": enabled()})


@app.get("/api/google/status")
@jwt_required()
def google_status():
    row = google_row(my_id())
    return jsonify({"status": row[0] or "unverified", "name": row[1] or "", "email": row[2] or "",
                    "email_match": bool(row[3]), "checked_at": row[4].isoformat() if row[4] else None})


@app.post("/api/google/start")
@jwt_required()
def google_start():
    if not enabled():
        return error("Google verification is not configured on the server yet.", 503)
    state = signer.dumps({"uid": my_id(), "n": secrets.token_urlsafe(8)})
    return jsonify({"url": AUTH_URL + "?" + urlencode({
        "response_type": "code", "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "redirect_uri": redirect_uri(), "scope": "openid email profile",
        "state": state, "prompt": "select_account"})})


@app.get("/api/google/callback")
def google_callback():
    def back(result):
        return redirect(frontend_url(f"profile.html?google={result}#verify"))

    if request.args.get("error"):
        return back("cancelled")
    try:
        uid = int(signer.loads(request.args.get("state", ""), max_age=600)["uid"])
    except SignatureExpired:
        return back("expired")
    except BadSignature:
        return back("error")
    user = db.session.get(User, uid)
    if not user or not request.args.get("code") or not enabled():
        return back("error")
    try:
        tok = http.post(TOKEN_URL, timeout=15, data={
            "grant_type": "authorization_code", "code": request.args["code"],
            "redirect_uri": redirect_uri(), "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET")})
        tok.raise_for_status()
        info = http.get(USERINFO_URL, timeout=15, headers={
            "Authorization": f"Bearer {tok.json()['access_token']}"})
        info.raise_for_status()
        info = info.json()
    except Exception:
        app.logger.exception("Google verification failed")
        return back("error")

    sub = str(info.get("sub") or "")
    if not sub:
        return back("error")
    taken = db.session.execute(text("SELECT 1 FROM users WHERE google_sub = :s AND id <> :id"),
                               {"s": sub, "id": uid}).first()
    if taken:
        return back("already_linked")
    name = (info.get("name") or f"{info.get('given_name', '')} {info.get('family_name', '')}").strip()
    email = (info.get("email") or "").strip().lower()
    ok, _score = names_match(user.name, name)
    email_match = bool(email and email == user.email and info.get("email_verified", True))
    status = "verified" if ok else "mismatch"
    db.session.execute(text(
        "UPDATE users SET google_sub=:sub, google_name=:n, google_email=:e, google_status=:st, "
        "google_email_match=:em, google_checked_at=:t WHERE id=:id"),
        {"sub": sub, "n": name[:150], "e": email[:150], "st": status, "em": email_match,
         "t": utcnow(), "id": uid})
    db.session.commit()
    return back(status)


@app.post("/api/google/use-name")
@jwt_required()
def google_use_name():
    row = google_row(my_id())
    if not row or not row[1]:
        return error("Connect Google first.")
    user = db.session.get(User, my_id())
    user.name = row[1][:100]
    db.session.execute(text("UPDATE users SET google_status='verified' WHERE id=:id"), {"id": user.id})
    db.session.commit()
    return jsonify({"message": "Your profile name now matches Google. Verified!"})


@app.post("/api/google/disconnect")
@jwt_required()
def google_disconnect():
    db.session.execute(text(
        "UPDATE users SET google_sub=NULL, google_name='', google_email='', google_status='unverified', "
        "google_email_match=FALSE, google_checked_at=NULL WHERE id=:id"), {"id": my_id()})
    db.session.commit()
    return jsonify({"message": "Google disconnected."})


# Add "google_verified" to every student returned by the API, so badges show
# on matches, profiles, connections and requests without touching app.py.
@app.after_request
def add_google_badges(response):
    if not request.path.startswith("/api/") or not response.is_json or response.status_code >= 400:
        return response
    data = response.get_json(silent=True)
    people = []

    def collect(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("id"), int) and "name" in obj:
                people.append(obj)
            if isinstance(obj.get("student_id"), int):
                people.append(obj)
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    collect(v)
        elif isinstance(obj, list):
            for v in obj:
                collect(v)

    collect(data)
    if not people:
        return response
    ids = {p.get("student_id", p.get("id")) for p in people}
    rows = db.session.execute(text("SELECT id FROM users WHERE google_status='verified' AND id = ANY(:ids)")
                              if db.engine.dialect.name == "postgresql" else
                              text("SELECT id FROM users WHERE google_status='verified'"),
                              {"ids": list(ids)}).all()
    verified = {r[0] for r in rows}
    for p in people:
        p["google_verified"] = p.get("student_id", p.get("id")) in verified
    response.set_data(jsonify(data).get_data())
    return response
