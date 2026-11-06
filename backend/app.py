"""SkillSwap API – Flask + Supabase PostgreSQL + Gemini + LinkedIn verification.

The same Flask app also serves the frontend, so in production the whole site
(pages + API) lives on one public URL.
"""
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode

import requests as http
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, get_jwt_identity, jwt_required,
    verify_jwt_in_request,
)
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder=None)
# Render (and most hosts) sit behind a proxy; this makes url_for/https correct.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-jwt-change-me")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is missing. Create backend/.env using backend/.env.example."
    )
# Supabase gives a postgresql:// (or postgres://) URL. Use the psycopg 3 driver.
for prefix in ("postgresql://", "postgres://"):
    if database_url.startswith(prefix):
        database_url = "postgresql+psycopg://" + database_url[len(prefix):]
        break

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
engine_options = {"pool_pre_ping": True, "pool_recycle": 280}
# Optional: keep SkillSwap's tables in their own PostgreSQL schema, so the app
# can safely share a database with another project (e.g. DB_SCHEMA=skillswap).
DB_SCHEMA = os.getenv("DB_SCHEMA", "").strip().lower()
if DB_SCHEMA:
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", DB_SCHEMA):
        raise RuntimeError("DB_SCHEMA may only contain letters, numbers and underscores.")
    engine_options["connect_args"] = {"options": f"-csearch_path={DB_SCHEMA}"}
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": cors_origins}})
db = SQLAlchemy(app)
jwt = JWTManager(app)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -------------------- DATABASE MODELS --------------------

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    college = db.Column(db.String(150), default="")
    branch = db.Column(db.String(100), default="")
    year = db.Column(db.String(30), default="")
    bio = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    # Public profile link (opt-in)
    is_public = db.Column(db.Boolean, default=False, server_default=db.false(), nullable=False)
    # LinkedIn verification
    linkedin_url = db.Column(db.String(255), default="")
    linkedin_sub = db.Column(db.String(100), unique=True, nullable=True)
    linkedin_name = db.Column(db.String(150), default="")
    linkedin_email = db.Column(db.String(150), default="")
    linkedin_picture = db.Column(db.String(1000), default="")
    linkedin_status = db.Column(db.String(20), default="unverified", server_default="unverified", nullable=False)
    linkedin_name_score = db.Column(db.Integer, default=0)
    linkedin_email_match = db.Column(db.Boolean, default=False)
    linkedin_checked_at = db.Column(db.DateTime, nullable=True)


class Skill(db.Model):
    __tablename__ = "skills"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class UserSkill(db.Model):
    __tablename__ = "user_skills"
    __table_args__ = (
        db.UniqueConstraint("user_id", "skill_id", "skill_type", name="uq_user_skill"),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)
    skill_type = db.Column(db.String(10), nullable=False)  # teach or learn
    proficiency = db.Column(db.String(30), default="Beginner")
    skill = db.relationship("Skill")


class MatchRequest(db.Model):
    __tablename__ = "match_requests"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message = db.Column(db.String(500), default="")
    status = db.Column(db.String(20), default="pending")  # pending/accepted/rejected
    created_at = db.Column(db.DateTime, default=utcnow)
    sender = db.relationship("User", foreign_keys=[sender_id])
    receiver = db.relationship("User", foreign_keys=[receiver_id])


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    sender = db.relationship("User", foreign_keys=[sender_id])


class LearningSession(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    topic = db.Column(db.String(150), nullable=False)
    session_date = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, default=60)
    status = db.Column(db.String(20), default="planned")  # planned/completed/cancelled
    created_at = db.Column(db.DateTime, default=utcnow)
    owner = db.relationship("User", foreign_keys=[user_id])
    partner = db.relationship("User", foreign_keys=[partner_id])


class Review(db.Model):
    __tablename__ = "reviews"
    __table_args__ = (
        db.UniqueConstraint("reviewer_id", "reviewed_user_id", name="uq_review_pair"),
    )
    id = db.Column(db.Integer, primary_key=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])


# Columns added after the first version. Existing Supabase databases created by
# the old app get them added automatically at startup (create_all never alters).
NEW_COLUMNS = {
    "users": {
        "is_public": "BOOLEAN NOT NULL DEFAULT FALSE",
        "linkedin_url": "VARCHAR(255) DEFAULT ''",
        "linkedin_sub": "VARCHAR(100)",
        "linkedin_name": "VARCHAR(150) DEFAULT ''",
        "linkedin_email": "VARCHAR(150) DEFAULT ''",
        "linkedin_picture": "VARCHAR(1000) DEFAULT ''",
        "linkedin_status": "VARCHAR(20) NOT NULL DEFAULT 'unverified'",
        "linkedin_name_score": "INTEGER DEFAULT 0",
        "linkedin_email_match": "BOOLEAN DEFAULT FALSE",
        "linkedin_checked_at": "TIMESTAMP",
    },
    "sessions": {"created_at": "TIMESTAMP"},
    "reviews": {"created_at": "TIMESTAMP"},
}


def init_database():
    if DB_SCHEMA:
        with db.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
    db.create_all()
    inspector = inspect(db.engine)
    with db.engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if db.engine.dialect.name == "postgresql":
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_linkedin_sub "
                "ON users (linkedin_sub) WHERE linkedin_sub IS NOT NULL"))


# Runs on import, so it works with `python app.py` AND with gunicorn on Render.
with app.app_context():
    init_database()
    db.engine.dispose()  # don't share pooled connections across forked workers


# -------------------- HELPERS --------------------

def my_id():
    return int(get_jwt_identity())


def current_user():
    return db.session.get(User, my_id())


def error(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


def body():
    return request.get_json(silent=True) or {}


def clean(value, limit):
    return (value or "").strip()[:limit] if isinstance(value, str) else ""


@jwt.user_lookup_error_loader
def _user_missing(_header, _payload):
    return error("Your account no longer exists. Please log in again.", 401)


@jwt.expired_token_loader
def _expired(_header, _payload):
    return error("Your session has expired. Please log in again.", 401, code="token_expired")


@jwt.invalid_token_loader
def _invalid(reason):
    return error("Invalid login token. Please log in again.", 401, code="token_invalid")


@jwt.unauthorized_loader
def _missing(reason):
    return error("Please log in to continue.", 401, code="token_missing")


def rating_summary(user_id):
    avg, count = db.session.query(
        db.func.avg(Review.rating), db.func.count(Review.id)
    ).filter(Review.reviewed_user_id == user_id).one()
    return {"avg_rating": round(float(avg), 1) if avg else None, "review_count": count}


def skills_of(user_id):
    rows = UserSkill.query.filter_by(user_id=user_id).join(Skill).order_by(Skill.name).all()
    return [{"id": r.id, "name": r.skill.name, "type": r.skill_type,
             "proficiency": r.proficiency} for r in rows]


def linkedin_badge(user):
    return {
        "linkedin_status": user.linkedin_status or "unverified",
        "linkedin_verified": user.linkedin_status == "verified",
        "linkedin_url": user.linkedin_url or "",
        "photo": user.linkedin_picture or "",
    }


def profile_completeness(user, skills):
    checks = [
        ("Add your college", bool(user.college)),
        ("Add your branch", bool(user.branch)),
        ("Select your year", bool(user.year)),
        ("Write a short bio", bool(user.bio)),
        ("Add a skill you can teach", any(s["type"] == "teach" for s in skills)),
        ("Add a skill you want to learn", any(s["type"] == "learn" for s in skills)),
        ("Verify with LinkedIn", user.linkedin_status == "verified"),
    ]
    done = sum(1 for _, ok in checks if ok)
    return {"percent": round(done * 100 / len(checks)),
            "missing": [label for label, ok in checks if not ok]}


def are_connected(user_a, user_b):
    return MatchRequest.query.filter(
        MatchRequest.status == "accepted",
        db.or_(
            db.and_(MatchRequest.sender_id == user_a, MatchRequest.receiver_id == user_b),
            db.and_(MatchRequest.sender_id == user_b, MatchRequest.receiver_id == user_a),
        ),
    ).first() is not None


def connection_ids(user_id):
    rows = MatchRequest.query.filter(
        MatchRequest.status == "accepted",
        db.or_(MatchRequest.sender_id == user_id, MatchRequest.receiver_id == user_id),
    ).all()
    return {r.receiver_id if r.sender_id == user_id else r.sender_id for r in rows}


def relationship_with(me, other):
    """none | connected | pending_sent | pending_received"""
    if are_connected(me, other):
        return "connected"
    pending = MatchRequest.query.filter(
        MatchRequest.status == "pending",
        db.or_(
            db.and_(MatchRequest.sender_id == me, MatchRequest.receiver_id == other),
            db.and_(MatchRequest.sender_id == other, MatchRequest.receiver_id == me),
        ),
    ).first()
    if pending:
        return "pending_sent" if pending.sender_id == me else "pending_received"
    return "none"


def iso(value):
    return value.isoformat() if value else None


# -------------------- AUTHENTICATION --------------------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.post("/api/register")
def register():
    data = body()
    name = clean(data.get("name"), 100)
    email = clean(data.get("email"), 150).lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return error("Name, email and password are required.")
    if not EMAIL_RE.match(email):
        return error("Please enter a valid email address.")
    if len(password) < 8:
        return error("Password must contain at least 8 characters.")
    if User.query.filter_by(email=email).first():
        return error("An account with this email already exists.")

    user = User(name=name, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "Account created.", "token": token,
                    "user": {"id": user.id, "name": user.name, "email": user.email}}), 201


@app.post("/api/login")
def login():
    data = body()
    email = clean(data.get("email"), 150).lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return error("Invalid email or password.", 401)

    token = create_access_token(identity=str(user.id))
    return jsonify({"message": "Login successful.", "token": token,
                    "user": {"id": user.id, "name": user.name, "email": user.email}})


# -------------------- PROFILE AND SKILLS --------------------

LINKEDIN_URL_RE = re.compile(
    r"^(https?://)?([a-z]{2,3}\.)?linkedin\.com/(in|pub)/[A-Za-z0-9\-_%.]{2,100}/?(\?.*)?$", re.I)


def normalize_linkedin_url(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not LINKEDIN_URL_RE.match(value):
        raise ValueError("Enter a LinkedIn profile link like https://www.linkedin.com/in/your-name")
    value = value.split("?")[0].rstrip("/")
    if not value.lower().startswith("http"):
        value = "https://" + value
    return value


@app.get("/api/profile")
@jwt_required()
def get_profile():
    user = current_user()
    skills = skills_of(user.id)
    return jsonify({
        "id": user.id, "name": user.name, "email": user.email,
        "college": user.college, "branch": user.branch, "year": user.year,
        "bio": user.bio, "is_public": bool(user.is_public),
        "skills": skills,
        "completeness": profile_completeness(user, skills),
        **linkedin_badge(user),
        "linkedin_name": user.linkedin_name or "",
        "linkedin_email": user.linkedin_email or "",
        "linkedin_name_score": user.linkedin_name_score or 0,
        "linkedin_email_match": bool(user.linkedin_email_match),
        "linkedin_checked_at": iso(user.linkedin_checked_at),
        **rating_summary(user.id),
    })


@app.put("/api/profile")
@jwt_required()
def update_profile():
    user = current_user()
    data = body()
    name = clean(data.get("name"), 100)
    if not name:
        return error("Name cannot be empty.")
    try:
        linkedin_url = normalize_linkedin_url(data.get("linkedin_url"))
    except ValueError as exc:
        return error(str(exc))

    name_changed = name != user.name
    user.name = name
    user.college = clean(data.get("college"), 150)
    user.branch = clean(data.get("branch"), 100)
    user.year = clean(data.get("year"), 30)
    user.bio = clean(data.get("bio"), 1000)
    user.linkedin_url = linkedin_url
    if "is_public" in data:
        user.is_public = bool(data.get("is_public"))

    # Changing your name after verification re-runs the cross-check, so a
    # verified badge always reflects the name currently on the profile.
    note = ""
    if name_changed and user.linkedin_sub:
        ok, score = names_match(user.name, user.linkedin_name)
        user.linkedin_name_score = score
        user.linkedin_status = "verified" if ok else "mismatch"
        if not ok:
            note = " Your new name no longer matches your LinkedIn name, so the verified badge was removed."
    db.session.commit()
    return jsonify({"message": "Profile updated." + note})


@app.post("/api/skills")
@jwt_required()
def add_skill():
    data = body()
    name = re.sub(r"\s+", " ", clean(data.get("name"), 80))
    skill_type = data.get("type")
    proficiency = data.get("proficiency") or "Beginner"

    if not name or skill_type not in ("teach", "learn"):
        return error("Provide a skill name and type: teach or learn.")
    if proficiency not in ("Beginner", "Intermediate", "Advanced"):
        return error("Proficiency must be Beginner, Intermediate or Advanced.")
    skill = Skill.query.filter(db.func.lower(Skill.name) == name.lower()).first()
    if not skill:
        skill = Skill(name=name)
        db.session.add(skill)
        db.session.flush()

    existing = UserSkill.query.filter_by(
        user_id=my_id(), skill_id=skill.id, skill_type=skill_type).first()
    if existing:
        db.session.rollback()
        return error("This skill is already in your list.")
    row = UserSkill(user_id=my_id(), skill_id=skill.id,
                    skill_type=skill_type, proficiency=proficiency)
    db.session.add(row)
    db.session.commit()
    return jsonify({"message": "Skill added.", "id": row.id}), 201


@app.delete("/api/skills/<int:skill_row_id>")
@jwt_required()
def delete_skill(skill_row_id):
    row = UserSkill.query.filter_by(id=skill_row_id, user_id=my_id()).first()
    if not row:
        return error("Skill not found.", 404)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "Skill removed."})


@app.get("/api/skills/suggestions")
@jwt_required()
def skill_suggestions():
    rows = Skill.query.order_by(Skill.name).limit(300).all()
    return jsonify([s.name for s in rows])


# -------------------- DASHBOARD --------------------

@app.get("/api/dashboard")
@jwt_required()
def dashboard():
    user = current_user()
    skills = skills_of(user.id)
    now = utcnow()
    session_filter = db.or_(LearningSession.user_id == user.id,
                            LearningSession.partner_id == user.id)
    upcoming = LearningSession.query.filter(
        session_filter, LearningSession.status == "planned",
        db.or_(LearningSession.session_date.is_(None), LearningSession.session_date >= now),
    ).order_by(LearningSession.session_date.asc().nulls_last()).all()
    return jsonify({
        "name": user.name, "college": user.college, "branch": user.branch,
        "bio": user.bio,
        "teach_count": sum(1 for s in skills if s["type"] == "teach"),
        "learn_count": sum(1 for s in skills if s["type"] == "learn"),
        "connections": len(connection_ids(user.id)),
        "pending_incoming": MatchRequest.query.filter_by(
            receiver_id=user.id, status="pending").count(),
        "upcoming_sessions": [{
            "id": s.id, "topic": s.topic, "session_date": iso(s.session_date),
            "partner_name": (s.partner.name if s.user_id == user.id and s.partner
                             else s.owner.name if s.user_id != user.id else None),
        } for s in upcoming[:3]],
        "upcoming_count": len(upcoming),
        "completeness": profile_completeness(user, skills),
        **linkedin_badge(user),
        "is_public": bool(user.is_public),
    })


# -------------------- MATCHING --------------------

@app.get("/api/matches")
@jwt_required()
def get_matches():
    me = my_id()
    all_rows = UserSkill.query.join(Skill).all()
    teach, learn = {}, {}
    for row in all_rows:
        target = teach if row.skill_type == "teach" else learn
        target.setdefault(row.user_id, {})[row.skill.name.lower()] = row.skill.name

    my_teach, my_learn = teach.get(me, {}), learn.get(me, {})
    results = []
    for person in User.query.filter(User.id != me).all():
        their_teach, their_learn = teach.get(person.id, {}), learn.get(person.id, {})
        can_learn = sorted(their_teach[k] for k in set(my_learn) & set(their_teach))
        can_teach = sorted(my_teach[k] for k in set(my_teach) & set(their_learn))
        if not can_learn and not can_teach:
            continue

        # 50 points for each direction of the exchange, plus a small bonus for
        # each extra overlapping skill. A two-way swap always ranks first.
        score = (50 if can_learn else 0) + (40 if can_teach else 0)
        score += min(10, 3 * (len(can_learn) + len(can_teach) - 1))
        if can_learn and can_teach:
            score = max(score, 90)
        results.append({
            "id": person.id, "name": person.name, "college": person.college,
            "branch": person.branch, "year": person.year, "bio": person.bio,
            "score": min(score, 100), "mutual": bool(can_learn and can_teach),
            "they_can_teach_me": can_learn, "i_can_teach_them": can_teach,
            "relationship": relationship_with(me, person.id),
            **linkedin_badge(person), **rating_summary(person.id),
        })

    results.sort(key=lambda x: (x["score"], x["linkedin_verified"]), reverse=True)
    return jsonify(results)


# -------------------- USER PROFILES (shareable link) --------------------

@app.get("/api/users/<int:user_id>")
def view_user(user_id):
    """Logged-in students can view any profile. Anyone can view a profile the
    owner made public – that's the shareable public link."""
    verify_jwt_in_request(optional=True)
    viewer = get_jwt_identity()
    viewer = int(viewer) if viewer else None
    user = db.session.get(User, user_id)
    if not user or (viewer is None and not user.is_public):
        return error("This profile is private or does not exist.", 404)

    reviews = Review.query.filter_by(reviewed_user_id=user.id).order_by(
        Review.created_at.desc()).limit(20).all()
    data = {
        "id": user.id, "name": user.name, "college": user.college,
        "branch": user.branch, "year": user.year, "bio": user.bio,
        "is_public": bool(user.is_public), "member_since": iso(user.created_at),
        "skills": skills_of(user.id), **linkedin_badge(user), **rating_summary(user.id),
        "reviews": [{"rating": r.rating, "comment": r.comment,
                     "reviewer_name": r.reviewer.name, "created_at": iso(r.created_at)}
                    for r in reviews],
        "is_me": viewer == user.id,
    }
    if viewer and viewer != user.id:
        data["relationship"] = relationship_with(viewer, user.id)
        mine = Review.query.filter_by(reviewer_id=viewer, reviewed_user_id=user.id).first()
        data["my_review"] = {"rating": mine.rating, "comment": mine.comment} if mine else None
    return jsonify(data)


# -------------------- LEARNING REQUESTS --------------------

REJECTION_COOLDOWN = timedelta(days=7)


@app.post("/api/requests")
@jwt_required()
def send_request():
    me = my_id()
    data = body()
    try:
        receiver_id = int(data.get("receiver_id"))
    except (TypeError, ValueError):
        return error("A valid receiver_id is required.")
    if receiver_id == me or not db.session.get(User, receiver_id):
        return error("Invalid student.")

    relation = relationship_with(me, receiver_id)
    if relation == "connected":
        return error("You are already connected with this student.")
    if relation == "pending_sent":
        return error("You already have a pending request with this student.")
    if relation == "pending_received":
        return error("This student already sent you a request. Accept it on the Requests page.")

    recent_rejection = MatchRequest.query.filter(
        MatchRequest.sender_id == me, MatchRequest.receiver_id == receiver_id,
        MatchRequest.status == "rejected",
        MatchRequest.created_at >= utcnow() - REJECTION_COOLDOWN,
    ).first()
    if recent_rejection:
        return error("This student declined your request recently. You can try again after 7 days.")

    item = MatchRequest(sender_id=me, receiver_id=receiver_id,
                        message=clean(data.get("message"), 500))
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "Learning request sent.", "id": item.id}), 201


@app.get("/api/requests")
@jwt_required()
def list_requests():
    me = my_id()
    incoming = MatchRequest.query.filter_by(receiver_id=me).order_by(
        MatchRequest.created_at.desc()).all()
    outgoing = MatchRequest.query.filter_by(sender_id=me).order_by(
        MatchRequest.created_at.desc()).all()

    def serialize(item, direction):
        other = item.sender if direction == "incoming" else item.receiver
        return {"id": item.id, "direction": direction, "status": item.status,
                "message": item.message, "student_id": other.id,
                "student_name": other.name, "created_at": iso(item.created_at),
                "linkedin_verified": other.linkedin_status == "verified"}

    return jsonify({
        "incoming": [serialize(x, "incoming") for x in incoming],
        "outgoing": [serialize(x, "outgoing") for x in outgoing],
    })


@app.put("/api/requests/<int:request_id>")
@jwt_required()
def update_request(request_id):
    item = MatchRequest.query.filter_by(id=request_id, receiver_id=my_id()).first()
    if not item:
        return error("Request not found.", 404)
    if item.status != "pending":
        return error(f"This request was already {item.status}.")
    status = body().get("status")
    if status not in ("accepted", "rejected"):
        return error("Status must be accepted or rejected.")
    item.status = status
    db.session.commit()
    return jsonify({"message": f"Request {status}."})


@app.delete("/api/requests/<int:request_id>")
@jwt_required()
def cancel_request(request_id):
    item = MatchRequest.query.filter_by(id=request_id, sender_id=my_id()).first()
    if not item:
        return error("Request not found.", 404)
    if item.status != "pending":
        return error("Only pending requests can be cancelled.")
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Request cancelled."})


@app.get("/api/connections")
@jwt_required()
def list_connections():
    me = my_id()
    people = User.query.filter(User.id.in_(connection_ids(me))).order_by(User.name).all() \
        if connection_ids(me) else []
    out = []
    for p in people:
        last = Message.query.filter(db.or_(
            db.and_(Message.sender_id == me, Message.receiver_id == p.id),
            db.and_(Message.sender_id == p.id, Message.receiver_id == me),
        )).order_by(Message.created_at.desc()).first()
        out.append({"id": p.id, "name": p.name, "college": p.college, "branch": p.branch,
                    "last_message": last.body[:80] if last else "",
                    "last_message_at": iso(last.created_at) if last else None,
                    **linkedin_badge(p), **rating_summary(p.id)})
    return jsonify(out)


# -------------------- BASIC MESSAGING --------------------

@app.get("/api/messages/<int:other_user_id>")
@jwt_required()
def get_messages(other_user_id):
    me = my_id()
    if not are_connected(me, other_user_id):
        return error("Messaging is available after a learning request is accepted.", 403)
    query = Message.query.filter(db.or_(
        db.and_(Message.sender_id == me, Message.receiver_id == other_user_id),
        db.and_(Message.sender_id == other_user_id, Message.receiver_id == me),
    ))
    after = request.args.get("after", type=int)
    if after:
        query = query.filter(Message.id > after)
    messages = query.order_by(Message.created_at.asc(), Message.id.asc()).all()
    return jsonify([{
        "id": m.id, "sender_id": m.sender_id, "body": m.body,
        "mine": m.sender_id == me, "created_at": iso(m.created_at),
    } for m in messages])


@app.post("/api/messages/<int:other_user_id>")
@jwt_required()
def send_message(other_user_id):
    me = my_id()
    if not are_connected(me, other_user_id):
        return error("Messaging is available after a learning request is accepted.", 403)
    text_body = clean(body().get("body"), 3001)
    if not text_body or len(text_body) > 3000:
        return error("Message must contain 1 to 3000 characters.")
    message = Message(sender_id=me, receiver_id=other_user_id, body=text_body)
    db.session.add(message)
    db.session.commit()
    return jsonify({"message": "Message sent.", "id": message.id}), 201


# -------------------- LEARNING SESSIONS --------------------

SESSION_STATUSES = ("planned", "completed", "cancelled")


def serialize_session(s, me):
    other = s.partner if s.user_id == me else s.owner
    return {"id": s.id, "topic": s.topic, "partner_id": other.id if other else None,
            "partner_name": other.name if other else None,
            "created_by_me": s.user_id == me,
            "session_date": iso(s.session_date),
            "duration_minutes": s.duration_minutes, "status": s.status}


@app.get("/api/sessions")
@jwt_required()
def list_sessions():
    me = my_id()
    rows = LearningSession.query.filter(db.or_(
        LearningSession.user_id == me, LearningSession.partner_id == me,
    )).order_by(LearningSession.session_date.desc().nulls_last(),
                LearningSession.id.desc()).all()
    return jsonify([serialize_session(x, me) for x in rows])


@app.post("/api/sessions")
@jwt_required()
def create_session():
    me = my_id()
    data = body()
    topic = clean(data.get("topic"), 150)
    if not topic:
        return error("Session topic is required.")
    partner_id = data.get("partner_id")
    if partner_id in ("", None):
        partner_id = None
    else:
        try:
            partner_id = int(partner_id)
        except (ValueError, TypeError):
            return error("Invalid partner ID.")
        if not are_connected(me, partner_id):
            return error("You can schedule sessions with accepted partners only.", 403)
    session_date = None
    if data.get("session_date"):
        try:
            session_date = datetime.fromisoformat(str(data["session_date"]).replace("Z", ""))
        except ValueError:
            return error("Invalid session date. Use ISO date/time.")
    try:
        duration = int(data.get("duration_minutes", 60))
    except (TypeError, ValueError):
        return error("Duration must be a number of minutes.")
    if not 15 <= duration <= 240:
        return error("Duration must be between 15 and 240 minutes.")
    row = LearningSession(user_id=me, partner_id=partner_id, topic=topic,
                          session_date=session_date, duration_minutes=duration)
    db.session.add(row)
    db.session.commit()
    return jsonify({"message": "Session created.", "id": row.id}), 201


@app.put("/api/sessions/<int:session_id>")
@jwt_required()
def update_session(session_id):
    me = my_id()
    row = LearningSession.query.filter(
        LearningSession.id == session_id,
        db.or_(LearningSession.user_id == me, LearningSession.partner_id == me),
    ).first()
    if not row:
        return error("Session not found.", 404)
    status = body().get("status")
    if status not in SESSION_STATUSES:
        return error("Status must be planned, completed or cancelled.")
    row.status = status
    db.session.commit()
    return jsonify({"message": f"Session marked {status}."})


@app.delete("/api/sessions/<int:session_id>")
@jwt_required()
def delete_session(session_id):
    row = LearningSession.query.filter_by(id=session_id, user_id=my_id()).first()
    if not row:
        return error("Only the student who created a session can delete it.", 404)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "Session deleted."})


# -------------------- REVIEWS --------------------

@app.post("/api/reviews")
@jwt_required()
def save_review():
    me = my_id()
    data = body()
    try:
        reviewed_id = int(data.get("reviewed_user_id"))
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        return error("reviewed_user_id and rating are required.")
    if reviewed_id == me:
        return error("You cannot review yourself.")
    if not 1 <= rating <= 5:
        return error("Rating must be between 1 and 5.")
    if not are_connected(me, reviewed_id):
        return error("You can only review students you are connected with.", 403)
    review = Review.query.filter_by(reviewer_id=me, reviewed_user_id=reviewed_id).first()
    created = review is None
    if created:
        review = Review(reviewer_id=me, reviewed_user_id=reviewed_id, rating=rating)
        db.session.add(review)
    review.rating = rating
    review.comment = clean(data.get("comment"), 500)
    db.session.commit()
    return jsonify({"message": "Review saved." if created else "Review updated."}), 201 if created else 200


@app.get("/api/users/<int:user_id>/reviews")
@jwt_required()
def list_reviews(user_id):
    rows = Review.query.filter_by(reviewed_user_id=user_id).order_by(
        Review.created_at.desc()).all()
    return jsonify({**rating_summary(user_id), "reviews": [
        {"rating": r.rating, "comment": r.comment, "reviewer_name": r.reviewer.name,
         "created_at": iso(r.created_at)} for r in rows]})


# -------------------- LINKEDIN VERIFICATION --------------------
# Uses "Sign In with LinkedIn using OpenID Connect". LinkedIn returns the
# member's verified name, email and photo, which we cross-check against the
# details the student entered on SkillSwap.

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = os.getenv("LINKEDIN_TOKEN_URL", "https://www.linkedin.com/oauth/v2/accessToken")
LINKEDIN_USERINFO_URL = os.getenv("LINKEDIN_USERINFO_URL", "https://api.linkedin.com/v2/userinfo")
state_signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="linkedin-verify")


def linkedin_enabled():
    return bool(os.getenv("LINKEDIN_CLIENT_ID") and os.getenv("LINKEDIN_CLIENT_SECRET"))


def linkedin_redirect_uri():
    return os.getenv("LINKEDIN_REDIRECT_URI") or (request.host_url.rstrip("/") + "/api/linkedin/callback")


def frontend_url(path):
    base = os.getenv("FRONTEND_URL") or request.host_url.rstrip("/")
    return base.rstrip("/") + "/" + path.lstrip("/")


def name_tokens(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return [t for t in re.split(r"[^a-z]+", value) if t]


def names_match(profile_name, linkedin_name):
    """Return (match?, score 0-100). Every part of the shorter name must be
    found in the longer one (initials allowed, small typos tolerated) and at
    least one full name part must match exactly."""
    a, b = name_tokens(profile_name), name_tokens(linkedin_name)
    if not a or not b:
        return False, 0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    matched, exact = 0, 0
    for token in short:
        if token in long_:
            matched += 1
            exact += len(token) > 1
        elif len(token) == 1 and any(t.startswith(token) for t in long_):
            matched += 1
        elif any(len(t) == 1 and token.startswith(t) for t in long_):
            matched += 1
        elif any(SequenceMatcher(None, token, t).ratio() >= 0.85 for t in long_):
            matched += 1
    coverage = matched / len(short)
    whole = SequenceMatcher(None, " ".join(sorted(a)), " ".join(sorted(b))).ratio()
    score = round(100 * max(coverage if exact else coverage * 0.6, whole))
    return (coverage == 1 and exact >= 1) or whole >= 0.92, min(score, 100)


@app.get("/api/linkedin/config")
def linkedin_config():
    return jsonify({"enabled": linkedin_enabled()})


@app.post("/api/linkedin/start")
@jwt_required()
def linkedin_start():
    if not linkedin_enabled():
        return error("LinkedIn verification is not configured on the server yet.", 503)
    state = state_signer.dumps({"uid": my_id(), "n": secrets.token_urlsafe(8)})
    params = {
        "response_type": "code",
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "redirect_uri": linkedin_redirect_uri(),
        "state": state,
        "scope": "openid profile email",
    }
    return jsonify({"url": f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"})


@app.get("/api/linkedin/callback")
def linkedin_callback():
    def back(result):
        return redirect(frontend_url(f"profile.html?linkedin={result}#verify"))

    if request.args.get("error"):
        return back("cancelled")
    try:
        state = state_signer.loads(request.args.get("state", ""), max_age=600)
    except SignatureExpired:
        return back("expired")
    except BadSignature:
        return back("error")
    user = db.session.get(User, int(state["uid"]))
    code = request.args.get("code")
    if not user or not code or not linkedin_enabled():
        return back("error")

    try:
        token_res = http.post(LINKEDIN_TOKEN_URL, timeout=15, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": linkedin_redirect_uri(),
            "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
            "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET"),
        })
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]
        info_res = http.get(LINKEDIN_USERINFO_URL, timeout=15,
                            headers={"Authorization": f"Bearer {access_token}"})
        info_res.raise_for_status()
        info = info_res.json()
    except Exception:
        app.logger.exception("LinkedIn verification failed")
        return back("error")

    sub = str(info.get("sub") or "")
    if not sub:
        return back("error")
    other = User.query.filter(User.linkedin_sub == sub, User.id != user.id).first()
    if other:
        return back("already_linked")

    li_name = (info.get("name") or
               f"{info.get('given_name', '')} {info.get('family_name', '')}").strip()
    li_email = (info.get("email") or "").strip().lower()
    ok, score = names_match(user.name, li_name)
    user.linkedin_sub = sub
    user.linkedin_name = li_name[:150]
    user.linkedin_email = li_email[:150]
    user.linkedin_picture = (info.get("picture") or "")[:1000]
    user.linkedin_name_score = score
    user.linkedin_email_match = bool(li_email and li_email == user.email
                                     and info.get("email_verified", True))
    user.linkedin_status = "verified" if ok else "mismatch"
    user.linkedin_checked_at = utcnow()
    db.session.commit()
    return back(user.linkedin_status)


@app.post("/api/linkedin/use-name")
@jwt_required()
def linkedin_use_name():
    """Fix a mismatch by adopting the exact name from LinkedIn."""
    user = current_user()
    if not user.linkedin_sub or not user.linkedin_name:
        return error("Connect LinkedIn first.")
    user.name = user.linkedin_name[:100]
    user.linkedin_name_score = 100
    user.linkedin_status = "verified"
    db.session.commit()
    return jsonify({"message": "Your profile name now matches LinkedIn. Verified!"})


@app.post("/api/linkedin/disconnect")
@jwt_required()
def linkedin_disconnect():
    user = current_user()
    user.linkedin_sub = None
    user.linkedin_name = user.linkedin_email = user.linkedin_picture = ""
    user.linkedin_status = "unverified"
    user.linkedin_name_score = 0
    user.linkedin_email_match = False
    user.linkedin_checked_at = None
    db.session.commit()
    return jsonify({"message": "LinkedIn disconnected."})


# -------------------- GEMINI AI ROADMAP --------------------

@app.post("/api/ai/roadmap")
@jwt_required()
def generate_roadmap():
    data = body()
    topic = clean(data.get("topic"), 120)
    level = clean(data.get("level"), 30) or "Beginner"
    goal = clean(data.get("goal"), 500)

    if not topic:
        return error("Please provide a skill or topic.")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return error("Gemini API key is not configured on the server.", 503)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        prompt = f"""
Create a practical 4-week learning roadmap for a college student.
Skill: {topic}
Current level: {level}
Goal: {goal or "Build a small project and understand the fundamentals."}
Use Markdown: a "## Week N: title" heading per week, bullet points for topics
and practical tasks, and finish with a "## Mini-project" section.
Keep it realistic for a student. Do not claim the learner has completed anything.
"""
        response = client.models.generate_content(model=model, contents=prompt)
        return jsonify({"topic": topic, "roadmap": response.text or "No roadmap was generated."})
    except Exception:
        app.logger.exception("Gemini request failed")
        return error("AI service could not generate a roadmap. Check the API key, model and quota.", 502)


@app.get("/api/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"
    return jsonify({"status": "ok", "service": "SkillSwap API", "database": database,
                    "linkedin": linkedin_enabled(), "gemini": bool(os.getenv("GEMINI_API_KEY"))})


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return error("Not found.", 404)
    return send_from_directory(FRONTEND_DIR, "index.html"), 404


@app.errorhandler(500)
def server_error(_e):
    db.session.rollback()
    return error("Something went wrong on the server.", 500)


# -------------------- FRONTEND (same URL as the API) --------------------

@app.get("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def frontend(path):
    if path.startswith("api/"):
        return error("Not found.", 404)
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", port=int(os.getenv("PORT", 5000)))
