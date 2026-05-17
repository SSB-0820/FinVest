from datetime import datetime, timedelta
from time import perf_counter
import json
import re
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.account_model import ensure_default_account
from app.models.category_model import ensure_default_categories
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import get_or_create_user_settings
from app.services.active_session_service import end_active_session, start_active_session
from app.utils.activity_logger import log_activity
from app.utils.decorators import ADMIN_EMAIL
from extensions.db import db
from extensions.mongo import get_collection

auth = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.]+$")
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+=\[\]{}|\\:;\"'<>,.?/]).{8,}$"
)

SECURITY_QUESTIONS = [
    "What was the name of your first school?",
    "What is your mother's maiden name?",
    "What city were you born in?",
    "What was your first pet's name?",
    "What is your favorite childhood book?",
]


def _normalize_answer(answer):
    return " ".join((answer or "").strip().lower().split())


def _security_payload_from_form():
    payload = []
    for index, question in enumerate(SECURITY_QUESTIONS):
        answer = _normalize_answer(request.form.get(f"security_answer_{index}", ""))
        if not answer:
            return None
        payload.append(
            {
                "question": question,
                "answer_hash": generate_password_hash(answer),
            }
        )
    return json.dumps(payload)


@auth.route("/")
def onboarding():
    stats = {
        "users": 0,
        "transactions": 0,
        "logs": 0,
        "db_ms": 0,
    }
    try:
        started_at = perf_counter()
        stats["users"] = User.query.filter_by(is_active=True).count()
        stats["transactions"] = Transaction.query.count()
        stats["db_ms"] = round((perf_counter() - started_at) * 1000, 2)
        activity_collection = get_collection("activity_logs")
        if activity_collection is not None:
            stats["logs"] = activity_collection.count_documents({})
    except Exception:
        db.session.rollback()
    return render_template("auth/onboarding.html", stats=stats)


@auth.route("/auth")
def auth_page():
    mode = request.args.get("mode", "login")
    return render_template(
        "auth/auth.html",
        mode=mode,
        security_questions=SECURITY_QUESTIONS,
        reset_email=None,
        reset_questions=[],
    )


@auth.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")
    security_answers = _security_payload_from_form()

    if not username or not email or not password or not security_answers:
        flash("Please fill all fields")
        return redirect(url_for("auth.auth_page", mode="signup"))

    username = username.strip()
    email = email.strip().lower()

    if not USERNAME_PATTERN.match(username):
        flash("Username can use only letters, numbers, underscore and dot")
        return redirect(url_for("auth.auth_page", mode="signup"))

    if not PASSWORD_PATTERN.match(password):
        flash("Password must be 8+ chars with uppercase, lowercase, number and special symbol")
        return redirect(url_for("auth.auth_page", mode="signup"))

    if password != confirm_password:
        flash("Passwords do not match")
        return redirect(url_for("auth.auth_page", mode="signup"))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash("Email already registered")
        return redirect(url_for("auth.auth_page", mode="signup"))

    if email.lower() == ADMIN_EMAIL:
        flash("This email is reserved for system admin")
        return redirect(url_for("auth.auth_page", mode="signup"))

    hashed_password = generate_password_hash(password)
    new_user = User(
        name=username,
        email=email,
        password_hash=hashed_password,
        security_answers=security_answers,
        role="user",
    )

    db.session.add(new_user)
    db.session.commit()

    get_or_create_user_settings(new_user.id)
    ensure_default_categories(new_user.id)
    ensure_default_account(new_user.id)
    db.session.commit()

    session.pop("login_attempts", None)
    session.pop("last_attempt_time", None)

    flash("Account created successfully! Please login")
    return redirect(url_for("auth.auth_page", mode="login"))


@auth.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

    if email:
        email = email.strip().lower()

    if "login_attempts" not in session:
        session["login_attempts"] = 0
        session["last_attempt_time"] = str(datetime.utcnow())

    last_time = datetime.fromisoformat(session["last_attempt_time"])
    if datetime.utcnow() - last_time > timedelta(minutes=2):
        session["login_attempts"] = 0

    if session["login_attempts"] >= 3:
        flash("Too many failed attempts. Try again after 2 minutes")
        return redirect(url_for("auth.auth_page", mode="login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        session["login_attempts"] += 1
        session["last_attempt_time"] = str(datetime.utcnow())
        flash(f"User not found. Attempts left: {3 - session['login_attempts']}")
        return redirect(url_for("auth.auth_page", mode="login"))

    if not check_password_hash(user.password_hash, password):
        session["login_attempts"] += 1
        session["last_attempt_time"] = str(datetime.utcnow())
        flash(f"Wrong Password! Attempts left: {3 - session['login_attempts']}")
        return redirect(url_for("auth.auth_page", mode="login"))

    if not user.is_active:
        flash("Your account is blocked. Please contact admin")
        return redirect(url_for("auth.auth_page", mode="login"))

    session["user_id"] = user.id
    session["username"] = user.name
    session["email"] = user.email
    session["role"] = user.role
    session["session_token"] = uuid4().hex
    session.pop("login_attempts", None)
    session.pop("last_attempt_time", None)
    start_active_session(user.id, session["session_token"])
    log_activity(
        "login",
        "Logged into the system",
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
    )
    db.session.commit()

    if user.role == "admin":
        return redirect(url_for("dashboard.admin_dashboard"))

    return redirect(url_for("dashboard.home"))


@auth.route("/forgot-password/questions", methods=["POST"])
def forgot_password_questions():
    email = request.form.get("reset_email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user or not user.security_answers:
        flash("Recovery questions are not available for this email")
        return redirect(url_for("auth.auth_page", mode="login"))

    questions = json.loads(user.security_answers)
    selected_indexes = [0, 3] if len(questions) >= 4 else [0, 1]
    reset_questions = [
        {"index": index, "question": questions[index]["question"]}
        for index in selected_indexes
    ]
    return render_template(
        "auth/auth.html",
        mode="login",
        security_questions=SECURITY_QUESTIONS,
        reset_email=email,
        reset_questions=reset_questions,
    )


@auth.route("/forgot-password/reset", methods=["POST"])
def forgot_password_reset():
    email = request.form.get("reset_email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user or not user.security_answers:
        flash("Recovery questions are not available for this email")
        return redirect(url_for("auth.auth_page", mode="login"))

    answers = json.loads(user.security_answers)
    for key, value in request.form.items():
        if not key.startswith("security_answer_"):
            continue
        index = int(key.replace("security_answer_", ""))
        expected = answers[index]["answer_hash"]
        if not check_password_hash(expected, _normalize_answer(value)):
            flash("Security answers did not match")
            return redirect(url_for("auth.auth_page", mode="login"))

    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not PASSWORD_PATTERN.match(new_password):
        flash("Password must be 8+ chars with uppercase, lowercase, number and special symbol")
        return redirect(url_for("auth.auth_page", mode="login"))
    if new_password != confirm_password:
        flash("Passwords do not match")
        return redirect(url_for("auth.auth_page", mode="login"))

    user.password_hash = generate_password_hash(new_password)
    log_activity(
        "password_reset",
        "Reset password using security questions",
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
    )
    db.session.commit()
    flash("Password reset successfully. Please login")
    return redirect(url_for("auth.auth_page", mode="login"))


@auth.route("/logout")
def logout():
    session_token = session.get("session_token")
    if session.get("user_id"):
        log_activity(
            "logout",
            "Logged out of the system",
            user_id=session.get("user_id"),
            user_name=session.get("username"),
            user_email=session.get("email"),
        )
        end_active_session(session_token)
        db.session.commit()
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for("auth.onboarding"))
