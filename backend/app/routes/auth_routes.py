from datetime import datetime, timedelta
import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.account_model import ensure_default_account
from app.models.category_model import ensure_default_categories
from app.models.user_model import User
from app.models.user_settings_model import get_or_create_user_settings
from app.utils.activity_logger import log_activity
from app.utils.decorators import ADMIN_EMAIL
from extensions.db import db

auth = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.]+$")
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_\-+=\[\]{}|\\:;\"'<>,.?/]).{8,}$"
)


@auth.route("/")
def onboarding():
    return render_template("auth/onboarding.html")


@auth.route("/auth")
def auth_page():
    mode = request.args.get("mode", "login")
    return render_template("auth/auth.html", mode=mode)


@auth.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")

    if not username or not email or not password:
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
    session.pop("login_attempts", None)
    session.pop("last_attempt_time", None)
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


@auth.route("/logout")
def logout():
    if session.get("user_id"):
        log_activity(
            "logout",
            "Logged out of the system",
            user_id=session.get("user_id"),
            user_name=session.get("username"),
            user_email=session.get("email"),
        )
        db.session.commit()
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for("auth.onboarding"))
