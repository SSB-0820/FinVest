from functools import wraps

from flask import flash, redirect, session, url_for


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first")
            return redirect(url_for("auth.auth_page", mode="login"))
        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "role" not in session or session["role"] != "admin":
            flash("Access denied")
            return redirect(url_for("auth.auth_page"))
        return func(*args, **kwargs)

    return wrapper
