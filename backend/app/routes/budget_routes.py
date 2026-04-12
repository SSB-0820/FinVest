from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.budget_model import Budget
from app.models.category_model import Category, ensure_default_categories
from app.models.transaction_model import Transaction
from app.models.user_settings_model import get_or_create_user_settings
from app.utils.decorators import login_required
from extensions.db import db

budgets = Blueprint("budgets", __name__)


@budgets.route("/budgets")
@login_required
def budget_list():
    user_id = session["user_id"]
    today = date.today()
    month = int(request.args.get("month", today.month))
    year = int(request.args.get("year", today.year))

    ensure_default_categories(user_id)
    settings = get_or_create_user_settings(user_id)
    db.session.commit()

    expense_categories = (
        Category.query.filter_by(user_id=user_id, type="expense")
        .order_by(Category.name.asc())
        .all()
    )
    items = (
        Budget.query.filter_by(user_id=user_id, month=month, year=year)
        .order_by(Budget.id.desc())
        .all()
    )

    spent_map = {}
    monthly_expenses = (
        Transaction.query.filter_by(user_id=user_id, type="expense")
        .filter(db.extract("month", Transaction.date) == month)
        .filter(db.extract("year", Transaction.date) == year)
        .all()
    )
    for txn in monthly_expenses:
        spent_map[txn.category_id] = spent_map.get(txn.category_id, Decimal("0")) + Decimal(txn.amount or 0)

    budget_rows = []
    for item in items:
        spent = spent_map.get(item.category_id, Decimal("0"))
        limit_amount = Decimal(item.limit_amount or 0)
        percent = int((spent / limit_amount) * 100) if limit_amount else 0
        budget_rows.append(
            {
                "budget": item,
                "spent": spent,
                "remaining": limit_amount - spent,
                "percent": max(0, percent),
            }
        )

    return render_template(
        "dashboard/budgets.html",
        active_page="budgets",
        budgets=budget_rows,
        categories=expense_categories,
        month=month,
        year=year,
        settings=settings,
    )


@budgets.route("/budgets", methods=["POST"])
@login_required
def add_budget():
    user_id = session["user_id"]
    category_id = int(request.form.get("category_id"))
    month = int(request.form.get("month"))
    year = int(request.form.get("year"))
    limit_amount = Decimal(request.form.get("limit_amount", "0") or "0")

    existing = Budget.query.filter_by(
        user_id=user_id, category_id=category_id, month=month, year=year
    ).first()
    if existing:
        existing.limit_amount = limit_amount
        flash("Budget updated successfully")
    else:
        db.session.add(
            Budget(
                user_id=user_id,
                category_id=category_id,
                limit_amount=limit_amount,
                month=month,
                year=year,
            )
        )
        flash("Budget added successfully")

    db.session.commit()
    return redirect(url_for("budgets.budget_list", month=month, year=year))


@budgets.route("/budgets/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete_budget(budget_id):
    item = Budget.query.filter_by(id=budget_id, user_id=session["user_id"]).first_or_404()
    month = item.month
    year = item.year
    db.session.delete(item)
    db.session.commit()
    flash("Budget deleted successfully")
    return redirect(url_for("budgets.budget_list", month=month, year=year))
