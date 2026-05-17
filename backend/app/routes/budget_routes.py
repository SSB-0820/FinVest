from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.budget_model import Budget
from app.models.account_model import Account, ensure_default_account
from app.models.category_model import Category, ensure_default_categories
from app.models.recurring_transaction_model import RecurringTransaction
from app.models.transaction_model import Transaction
from app.models.user_settings_model import get_or_create_user_settings
from app.utils.activity_logger import log_activity
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
    ensure_default_account(user_id)
    settings = get_or_create_user_settings(user_id)
    db.session.commit()

    accounts = Account.query.filter_by(user_id=user_id).order_by(Account.account_name.asc()).all()
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
    recurring_expenses = (
        RecurringTransaction.query.filter_by(user_id=user_id, type="expense")
        .order_by(RecurringTransaction.is_active.desc(), RecurringTransaction.next_run_date.asc())
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
        accounts=accounts,
        categories=expense_categories,
        recurring_expenses=recurring_expenses,
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
    if limit_amount <= 0:
        flash("Budget amount must be greater than 0")
        return redirect(url_for("budgets.budget_list", month=month, year=year))

    existing = Budget.query.filter_by(
        user_id=user_id, category_id=category_id, month=month, year=year
    ).first()
    if existing:
        existing.limit_amount = limit_amount
        log_activity(
            "budget_updated",
            f"Updated budget for category #{category_id} to {limit_amount:.2f}",
        )
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
        log_activity(
            "budget_added",
            f"Added budget for category #{category_id} with limit {limit_amount:.2f}",
        )
        flash("Budget added successfully")

    db.session.commit()
    return redirect(url_for("budgets.budget_list", month=month, year=year))


@budgets.route("/budgets/recurring", methods=["POST"])
@login_required
def add_recurring_expense():
    user_id = session["user_id"]
    account_id = int(request.form.get("account_id"))
    category_id = int(request.form.get("category_id"))
    amount = Decimal(request.form.get("amount", "0") or "0")
    frequency = request.form.get("frequency", "monthly").strip()
    try:
        start_date = date.fromisoformat(request.form.get("start_date", ""))
    except ValueError:
        flash("Choose a valid start date")
        return redirect(url_for("budgets.budget_list"))
    description = request.form.get("description", "").strip()

    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    category = Category.query.filter_by(id=category_id, user_id=user_id, type="expense").first()
    if not account or not category:
        flash("Choose a valid account and expense category")
        return redirect(url_for("budgets.budget_list"))
    if amount <= 0:
        flash("Recurring expense amount must be greater than 0")
        return redirect(url_for("budgets.budget_list"))
    if frequency not in {"daily", "monthly", "yearly"}:
        flash("Choose a valid recurring frequency")
        return redirect(url_for("budgets.budget_list"))

    db.session.add(
        RecurringTransaction(
            user_id=user_id,
            account_id=account_id,
            category_id=category_id,
            type="expense",
            amount=amount,
            description=description or f"{category.name} recurring expense",
            frequency=frequency,
            start_date=start_date,
            next_run_date=start_date,
        )
    )
    log_activity("recurring_expense_added", f"Added {frequency} recurring expense for {category.name}")
    db.session.commit()
    flash("Recurring expense saved successfully")
    return redirect(url_for("budgets.budget_list"))


@budgets.route("/budgets/recurring/<int:recurring_id>/toggle", methods=["POST"])
@login_required
def toggle_recurring_expense(recurring_id):
    item = RecurringTransaction.query.filter_by(
        id=recurring_id, user_id=session["user_id"], type="expense"
    ).first_or_404()
    item.is_active = not bool(item.is_active)
    log_activity(
        "recurring_expense_toggled",
        f"{'Activated' if item.is_active else 'Paused'} recurring expense #{item.id}",
    )
    db.session.commit()
    flash("Recurring expense updated successfully")
    return redirect(url_for("budgets.budget_list"))


@budgets.route("/budgets/recurring/<int:recurring_id>/delete", methods=["POST"])
@login_required
def delete_recurring_expense(recurring_id):
    item = RecurringTransaction.query.filter_by(
        id=recurring_id, user_id=session["user_id"], type="expense"
    ).first_or_404()
    log_activity("recurring_expense_deleted", f"Deleted recurring expense #{item.id}")
    db.session.delete(item)
    db.session.commit()
    flash("Recurring expense deleted successfully")
    return redirect(url_for("budgets.budget_list"))


@budgets.route("/budgets/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete_budget(budget_id):
    item = Budget.query.filter_by(id=budget_id, user_id=session["user_id"]).first_or_404()
    month = item.month
    year = item.year
    log_activity("budget_deleted", f"Deleted budget #{item.id}")
    db.session.delete(item)
    db.session.commit()
    flash("Budget deleted successfully")
    return redirect(url_for("budgets.budget_list", month=month, year=year))
