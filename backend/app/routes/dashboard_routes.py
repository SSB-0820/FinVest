from flask import Blueprint, render_template

from app.utils.decorators import admin_required, login_required

dashboard = Blueprint("dashboard", __name__)


@dashboard.route("/home")
@login_required
def home():
    return render_template("dashboard/home.html")


@dashboard.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    return render_template("dashboard/admin.html")
