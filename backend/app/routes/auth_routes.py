from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.user_model import User
from extensions.db import db

auth = Blueprint("auth", __name__)


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

    if password != confirm_password:
        flash("Passwords do not match")
        return redirect(url_for("auth.auth_page", mode="signup"))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash("Email already registered")
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

    session.pop("login_attempts", None)
    session.pop("last_attempt_time", None)

    flash("Account created successfully! Please login")
    return redirect(url_for("auth.auth_page", mode="login"))


@auth.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

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

    session["user_id"] = user.id
    session["username"] = user.name
    session["role"] = user.role
    session.pop("login_attempts", None)
    session.pop("last_attempt_time", None)

    if user.role == "admin":
        return redirect(url_for("dashboard.admin_dashboard"))

    return redirect(url_for("dashboard.home"))


@auth.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for("auth.onboarding"))
