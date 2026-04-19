from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.category_model import Category, ensure_default_categories
from app.utils.activity_logger import log_activity
from app.utils.decorators import login_required
from extensions.db import db

categories = Blueprint("categories", __name__)


@categories.route("/categories")
@login_required
def category_list():
    ensure_default_categories(session["user_id"])
    db.session.commit()
    items = (
        Category.query.filter_by(user_id=session["user_id"])
        .order_by(Category.type.asc(), Category.name.asc())
        .all()
    )
    return render_template(
        "dashboard/categories.html",
        active_page="categories",
        categories=items,
    )


@categories.route("/categories", methods=["POST"])
@login_required
def add_category():
    name = request.form.get("name", "").strip()
    category_type = request.form.get("type", "expense").strip()

    if not name:
        flash("Category name is required")
        return redirect(url_for("categories.category_list"))

    existing = Category.query.filter_by(
        user_id=session["user_id"], name=name, type=category_type
    ).first()
    if existing:
        flash("Category already exists")
        return redirect(url_for("categories.category_list"))

    db.session.add(
        Category(user_id=session["user_id"], name=name, type=category_type)
    )
    log_activity("category_added", f"Added {category_type} category {name}")
    db.session.commit()
    flash("Category added successfully")
    return redirect(url_for("categories.category_list"))


@categories.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    category = Category.query.filter_by(
        id=category_id, user_id=session["user_id"]
    ).first_or_404()
    log_activity("category_deleted", f"Deleted category {category.name}")
    db.session.delete(category)
    db.session.commit()
    flash("Category deleted successfully")
    return redirect(url_for("categories.category_list"))
