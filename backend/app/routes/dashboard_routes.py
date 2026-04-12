from collections import defaultdict
from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.account_model import Account, ensure_default_account
from app.models.budget_model import Budget
from app.models.category_model import Category, ensure_default_categories
from app.models.goal_model import Goal
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import get_or_create_user_settings
from app.utils.decorators import admin_required, login_required
from extensions.db import db

dashboard = Blueprint("dashboard", __name__)


def _currency_symbol(currency_code):
    symbols = {
        "INR": "Rs.",
        "USD": "$",
        "EUR": "EUR",
        "GBP": "GBP",
    }
    return symbols.get(currency_code, currency_code)


def _build_dashboard_data(user_id):
    settings = get_or_create_user_settings(user_id)
    ensure_default_categories(user_id)
    ensure_default_account(user_id)
    db.session.commit()

    today = date.today()
    transactions = (
        Transaction.query.filter_by(user_id=user_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    accounts = Account.query.filter_by(user_id=user_id).order_by(Account.id.desc()).all()
    goals = Goal.query.filter_by(user_id=user_id).order_by(Goal.id.desc()).all()
    budgets = (
        Budget.query.filter_by(user_id=user_id, month=today.month, year=today.year)
        .order_by(Budget.id.desc())
        .all()
    )

    current_month_transactions = [
        txn
        for txn in transactions
        if txn.date and txn.date.month == today.month and txn.date.year == today.year
    ]
    monthly_income = sum(
        Decimal(txn.amount or 0)
        for txn in current_month_transactions
        if txn.type == "income"
    )
    monthly_expense = sum(
        Decimal(txn.amount or 0)
        for txn in current_month_transactions
        if txn.type == "expense"
    )
    total_balance = sum(Decimal(account.balance or 0) for account in accounts)

    monthly_map = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0")})
    for txn in transactions:
        if not txn.date:
            continue
        key = (txn.date.year, txn.date.month)
        monthly_map[key][txn.type] += Decimal(txn.amount or 0)

    month_labels = []
    year = today.year
    month = today.month
    for _ in range(4):
        month_labels.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    month_labels.reverse()

    monthly_stats = []
    max_month_value = Decimal("1")
    for stat_year, stat_month in month_labels:
        stats = monthly_map[(stat_year, stat_month)]
        max_month_value = max(max_month_value, stats["income"], stats["expense"])
        monthly_stats.append(
            {
                "label": f"{date(stat_year, stat_month, 1):%b}",
                "income": stats["income"],
                "expense": stats["expense"],
            }
        )

    for item in monthly_stats:
        item["income_width"] = int((item["income"] / max_month_value) * 100) if max_month_value else 0
        item["expense_width"] = int((item["expense"] / max_month_value) * 100) if max_month_value else 0

    expense_by_category = defaultdict(Decimal)
    for txn in current_month_transactions:
        if txn.type == "expense" and txn.category_id:
            category_name = getattr(txn.category, "name", "Other")
            expense_by_category[category_name] += Decimal(txn.amount or 0)

    budget_rows = []
    for item in budgets:
        spent = expense_by_category.get(getattr(item.category, "name", ""), Decimal("0"))
        limit_amount = Decimal(item.limit_amount or 0)
        percent = int((spent / limit_amount) * 100) if limit_amount else 0
        budget_rows.append(
            {
                "budget": item,
                "spent": spent,
                "percent": max(0, percent),
            }
        )

    total_expense_for_chart = sum(expense_by_category.values()) or Decimal("0")
    chart_colors = ["#C9A84C", "#4f8ef7", "#5ECB8C", "#e07070", "#8A8F9E", "#8090f0"]
    chart_segments = []
    chart_legend = []
    start = 0
    for index, (name, amount) in enumerate(sorted(expense_by_category.items(), key=lambda item: item[1], reverse=True)[:6]):
        percent = float((amount / total_expense_for_chart) * 100) if total_expense_for_chart else 0
        sweep = (percent / 100) * 360
        end = start + sweep
        color = chart_colors[index % len(chart_colors)]
        chart_segments.append(f"{color} {start:.2f}deg {end:.2f}deg")
        chart_legend.append(
            {
                "name": name,
                "amount": amount,
                "percent": round(percent, 1),
                "color": color,
            }
        )
        start = end

    pie_chart_style = (
        f"background: conic-gradient({', '.join(chart_segments)});"
        if chart_segments
        else "background: conic-gradient(#1A2035 0deg 360deg);"
    )

    recent_transactions = transactions[:5]
    top_goal = goals[0] if goals else None
    goal_percent = 0
    if top_goal and top_goal.target_amount:
        goal_percent = int((Decimal(top_goal.current_amount or 0) / Decimal(top_goal.target_amount)) * 100)
        goal_percent = max(0, min(goal_percent, 100))

    return {
        "settings": settings,
        "currency_symbol": _currency_symbol(settings.currency or "INR"),
        "total_balance": total_balance,
        "monthly_income": monthly_income,
        "monthly_expense": monthly_expense,
        "monthly_stats": monthly_stats,
        "recent_transactions": recent_transactions,
        "pie_chart_style": pie_chart_style,
        "chart_legend": chart_legend,
        "accounts": accounts,
        "budget_rows": budget_rows[:4],
        "top_goal": top_goal,
        "goal_percent": goal_percent,
    }


@dashboard.route("/home")
@login_required
def home():
    data = _build_dashboard_data(session["user_id"])
    return render_template("dashboard/home.html", active_page="dashboard", **data)


@dashboard.route("/account")
@login_required
def account():
    user = User.query.get_or_404(session["user_id"])
    settings = get_or_create_user_settings(user.id)
    ensure_default_categories(user.id)
    ensure_default_account(user.id)
    db.session.commit()
    accounts = Account.query.filter_by(user_id=user.id).order_by(Account.id.desc()).all()
    return render_template(
        "dashboard/account.html",
        active_page="account",
        user=user,
        settings=settings,
        accounts=accounts,
    )


@dashboard.route("/account/profile", methods=["POST"])
@login_required
def update_profile():
    user = User.query.get_or_404(session["user_id"])
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name is required")
        return redirect(url_for("dashboard.account"))

    user.name = name
    session["username"] = name
    db.session.commit()
    flash("Profile updated successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/account/settings", methods=["POST"])
@login_required
def update_settings():
    settings = get_or_create_user_settings(session["user_id"])
    settings.currency = request.form.get("currency", "INR").strip() or "INR"
    settings.locale = request.form.get("locale", "en-IN").strip() or "en-IN"
    settings.month_start_day = int(request.form.get("month_start_day", 1) or 1)
    settings.month_start_day = min(max(settings.month_start_day, 1), 28)
    settings.monthly_salary = Decimal(request.form.get("monthly_salary", "0") or "0")
    db.session.commit()
    flash("Settings updated successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/account/accounts", methods=["POST"])
@login_required
def add_account():
    account_name = request.form.get("account_name", "").strip()
    account_type = request.form.get("type", "Cash").strip()
    balance = Decimal(request.form.get("balance", "0") or "0")

    if not account_name:
        flash("Account name is required")
        return redirect(url_for("dashboard.account"))

    db.session.add(
        Account(
            user_id=session["user_id"],
            account_name=account_name,
            type=account_type,
            balance=balance,
        )
    )
    db.session.commit()
    flash("Account added successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/account/accounts/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_account(account_id):
    account = Account.query.filter_by(id=account_id, user_id=session["user_id"]).first_or_404()
    db.session.delete(account)
    db.session.commit()
    flash("Account deleted successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_admins = User.query.filter_by(role="admin").count()
    total_transactions = Transaction.query.count()
    total_categories = db.session.query(db.func.count(Category.id)).scalar() or 0
    total_budgets = Budget.query.count()
    total_goals = Goal.query.count()
    recent_users = User.query.order_by(User.created_at.desc(), User.id.desc()).limit(5).all()
    recent_transactions = (
        Transaction.query.order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard/admin.html",
        active_page="admin",
        total_users=total_users,
        total_admins=total_admins,
        total_transactions=total_transactions,
        total_categories=total_categories,
        total_budgets=total_budgets,
        total_goals=total_goals,
        recent_users=recent_users,
        recent_admin_transactions=recent_transactions,
    )
