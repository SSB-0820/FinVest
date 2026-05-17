from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from time import perf_counter

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask import jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.account_model import Account, ensure_default_account
from app.models.activity_log_model import ActivityLog
from app.models.budget_model import Budget
from app.models.category_model import Category, ensure_default_categories
from app.models.goal_model import Goal
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import get_or_create_user_settings
from app.services.automation_service import process_monthly_salary
from app.services.active_session_service import count_active_sessions
from app.services.i18n_service import normalize_language
from app.utils.activity_logger import log_activity
from app.utils.decorators import admin_required, login_required
from extensions.db import db
from extensions.mongo import get_collection

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
    average_monthly_expense = Decimal("0")

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

    expense_totals = [item["expense"] for item in monthly_stats if Decimal(item["expense"] or 0) > 0]
    if expense_totals:
        average_monthly_expense = sum(expense_totals) / Decimal(len(expense_totals))

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
    top_spending_category = None
    start = 0
    for index, (name, amount) in enumerate(sorted(expense_by_category.items(), key=lambda item: item[1], reverse=True)[:6]):
        percent = float((amount / total_expense_for_chart) * 100) if total_expense_for_chart else 0
        sweep = (percent / 100) * 360
        end = start + sweep
        color = chart_colors[index % len(chart_colors)]
        if top_spending_category is None:
            top_spending_category = name
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
        f"background: conic-gradient(from -90deg, {', '.join(chart_segments)}, #1A2035 {start:.2f}deg 360deg);"
        if chart_segments
        else "background: conic-gradient(from -90deg, #1A2035 0deg 360deg);"
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
        "average_monthly_expense": average_monthly_expense,
        "monthly_stats": monthly_stats,
        "recent_transactions": recent_transactions,
        "pie_chart_style": pie_chart_style,
        "chart_legend": chart_legend,
        "top_spending_category": top_spending_category,
        "accounts": accounts,
        "budget_rows": budget_rows[:4],
        "top_goal": top_goal,
        "goal_percent": goal_percent,
    }


@dashboard.route("/home")
@login_required
def home():
    data = _build_dashboard_data(session["user_id"])
    data["show_guide"] = not session.get("guide_dismissed", False)
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
    log_activity("profile_updated", "Updated account profile name")
    db.session.commit()
    flash("Profile updated successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/account/settings", methods=["POST"])
@login_required
def update_settings():
    settings = get_or_create_user_settings(session["user_id"])
    settings.currency = request.form.get("currency", "INR").strip() or "INR"
    settings.locale = request.form.get("locale", "en-IN").strip() or "en-IN"
    settings.language = normalize_language(request.form.get("language", "en"))
    settings.month_start_day = int(request.form.get("month_start_day", 1) or 1)
    settings.month_start_day = min(max(settings.month_start_day, 1), 28)
    settings.monthly_salary = Decimal(request.form.get("monthly_salary", "0") or "0")
    log_activity("settings_updated", "Updated account settings")
    process_monthly_salary(session["user_id"])
    db.session.commit()
    flash("Settings updated successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/account/password", methods=["POST"])
@login_required
def update_password():
    user = User.query.get_or_404(session["user_id"])
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not check_password_hash(user.password_hash, current_password):
        flash("Current password is incorrect")
        return redirect(url_for("dashboard.account"))
    if len(new_password) < 8:
        flash("New password must be at least 8 characters")
        return redirect(url_for("dashboard.account"))
    if new_password != confirm_password:
        flash("New password and confirmation do not match")
        return redirect(url_for("dashboard.account"))

    user.password_hash = generate_password_hash(new_password)
    log_activity("password_updated", "Updated account password")
    db.session.commit()
    flash("Password updated successfully")
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
    log_activity("account_added", f"Added account {account_name}")
    db.session.commit()
    flash("Account added successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/account/accounts/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_account(account_id):
    account = Account.query.filter_by(id=account_id, user_id=session["user_id"]).first_or_404()
    log_activity("account_deleted", f"Deleted account {account.account_name}")
    db.session.delete(account)
    db.session.commit()
    flash("Account deleted successfully")
    return redirect(url_for("dashboard.account"))


@dashboard.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    selected_user_id = request.args.get("user_id", "").strip()
    today = date.today()
    total_users = User.query.count()
    total_admins = User.query.filter_by(role="admin").count()
    blocked_users = User.query.filter_by(is_active=False).count()
    total_transactions = Transaction.query.count()
    total_categories = db.session.query(db.func.count(Category.id)).scalar() or 0
    total_budgets = Budget.query.count()
    total_goals = Goal.query.count()
    users = User.query.order_by(User.created_at.desc(), User.id.desc()).all()
    users_created_today = [user for user in users if user.created_at and user.created_at.date() == today]

    transaction_query = Transaction.query.order_by(Transaction.created_at.desc(), Transaction.id.desc())
    activity_query = ActivityLog.query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    if selected_user_id:
        transaction_query = transaction_query.filter_by(user_id=int(selected_user_id))
        activity_query = activity_query.filter_by(user_id=int(selected_user_id))

    system_transactions = transaction_query.all()
    activity_logs = []
    activity_collection = get_collection("activity_logs")
    if activity_collection is not None:
        mongo_filter = {}
        if selected_user_id:
            mongo_filter["user_id"] = int(selected_user_id)
        mongo_logs = list(activity_collection.find(mongo_filter).sort("_id", -1).limit(25))
        if mongo_logs:
            activity_logs = mongo_logs
    if not activity_logs:
        activity_logs = activity_query.limit(25).all()

    activity_rows = []
    for item in activity_logs:
        created_at = getattr(item, "created_at", None)
        if isinstance(item, dict):
            created_at = item.get("created_at")
            created_label = str(created_at or "-")
            activity_rows.append(
                {
                    "user_name": item.get("user_name", "Unknown User"),
                    "action": item.get("action", "activity"),
                    "details": item.get("details", ""),
                    "created_at_label": created_label,
                    "created_on": str(created_at or "")[:10],
                }
            )
        else:
            created_label = created_at.strftime("%d %b %Y %I:%M %p") if created_at else "-"
            activity_rows.append(
                {
                    "user_name": item.user_name,
                    "action": item.action,
                    "details": item.details,
                    "created_at_label": created_label,
                    "created_on": created_at.strftime("%Y-%m-%d") if created_at else "",
                }
            )

    activity_source_rows = activity_rows
    today_key = today.strftime("%Y-%m-%d")
    login_events_today = sum(1 for item in activity_source_rows if item["action"] == "login" and item["created_on"] == today_key)
    logout_events_today = sum(1 for item in activity_source_rows if item["action"] == "logout" and item["created_on"] == today_key)
    transactions_today = [item for item in system_transactions if item.created_at and item.created_at.date() == today]
    monthly_category_map = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0"), "count": 0})
    for item in system_transactions:
        if not item.date:
            continue
        category_name = item.category.name if item.category else "Uncategorized"
        key = (item.date.strftime("%b %Y"), category_name)
        monthly_category_map[key][item.type] += Decimal(item.amount or 0)
        monthly_category_map[key]["count"] += 1

    monthly_category_rows = [
        {
            "month": month_label,
            "category": category_name,
            "income": values["income"],
            "expense": values["expense"],
            "count": values["count"],
        }
        for (month_label, category_name), values in monthly_category_map.items()
    ][:30]

    overview_chart_rows = [
        {"label": "Users", "value": total_users, "tone": "gold"},
        {"label": "Transactions", "value": total_transactions, "tone": "blue"},
        {"label": "Budgets", "value": total_budgets, "tone": "green"},
        {"label": "Goals", "value": total_goals, "tone": "red"},
    ]
    overview_max = max([row["value"] for row in overview_chart_rows] + [1])
    for row in overview_chart_rows:
        row["width"] = max(8, int((row["value"] / overview_max) * 100)) if row["value"] else 0

    daily_activity_rows = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        label = day.strftime("%d %b")
        logins = sum(
            1
            for item in activity_source_rows
            if item["action"] == "login" and item["created_on"] == day.strftime("%Y-%m-%d")
        )
        signups = sum(
            1 for user in users
            if user.created_at and user.created_at.date() == day
        )
        daily_activity_rows.append(
            {
                "label": label,
                "logins": logins,
                "signups": signups,
            }
        )
    activity_max = max([max(row["logins"], row["signups"]) for row in daily_activity_rows] + [1])
    for row in daily_activity_rows:
        row["login_width"] = max(8, int((row["logins"] / activity_max) * 100)) if row["logins"] else 0
        row["signup_width"] = max(8, int((row["signups"] / activity_max) * 100)) if row["signups"] else 0

    return render_template(
        "dashboard/admin.html",
        active_page="admin",
        total_users=total_users,
        total_admins=total_admins,
        blocked_users=blocked_users,
        total_transactions=total_transactions,
        total_categories=total_categories,
        total_budgets=total_budgets,
        total_goals=total_goals,
        users=users,
        user_lookup={user.id: user for user in users},
        activity_logs=activity_rows,
        monthly_category_rows=monthly_category_rows,
        selected_user_id=selected_user_id,
        users_created_today=len(users_created_today),
        login_events_today=login_events_today,
        logout_events_today=logout_events_today,
        transactions_today=len(transactions_today),
        overview_chart_rows=overview_chart_rows,
        daily_activity_rows=daily_activity_rows,
    )


@dashboard.route("/admin/users/<int:user_id>/toggle-block", methods=["POST"])
@login_required
@admin_required
def toggle_user_block(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == session.get("email"):
        flash("Admin account cannot be blocked")
        return redirect(url_for("dashboard.admin_dashboard"))

    user.is_active = not bool(user.is_active)
    action_text = "unblocked" if user.is_active else "blocked"
    log_activity(
        "admin_user_status_changed",
        f"Admin {action_text} user {user.email}",
        user_id=session["user_id"],
        user_name=session.get("username"),
        user_email=session.get("email"),
    )
    db.session.commit()
    flash(f"User {action_text} successfully")
    return redirect(url_for("dashboard.admin_dashboard"))


@dashboard.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == session.get("email"):
        flash("Admin account cannot be deleted")
        return redirect(url_for("dashboard.admin_dashboard"))

    user_email = user.email
    log_activity(
        "admin_user_deleted",
        f"Admin deleted user {user_email}",
        user_id=session["user_id"],
        user_name=session.get("username"),
        user_email=session.get("email"),
    )
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully")
    return redirect(url_for("dashboard.admin_dashboard"))


@dashboard.route("/admin/performance")
@login_required
@admin_required
def admin_performance():
    today = date.today()
    active_users = count_active_sessions()
    activity_collection = get_collection("activity_logs")
    total_logs = (
        activity_collection.count_documents({})
        if activity_collection is not None
        else ActivityLog.query.count()
    )
    db_started = perf_counter()
    db.session.query(db.func.count(User.id)).scalar()
    db_response_ms = round((perf_counter() - db_started) * 1000, 2)

    total_users = User.query.count()
    total_transactions = Transaction.query.count()
    last_response_ms = current_app.config.get("LAST_RESPONSE_MS", 0)

    performance_rows = [
        {"label": "Active Logins", "value": active_users, "tone": "green"},
        {"label": "DB Response", "value": db_response_ms, "tone": "blue"},
        {"label": "Last Request", "value": last_response_ms, "tone": "gold"},
        {"label": "Activity Logs", "value": total_logs, "tone": "red"},
    ]
    max_value = max([Decimal(str(row["value"] or 0)) for row in performance_rows] + [Decimal("1")])
    for row in performance_rows:
        value = Decimal(str(row["value"] or 0))
        row["width"] = max(8, int((value / max_value) * 100)) if value else 0

    growth_rows = [
        {"label": "Users", "value": total_users, "tone": "green"},
        {"label": "Transactions", "value": total_transactions, "tone": "blue"},
        {"label": "Logs", "value": total_logs, "tone": "gold"},
    ]
    growth_max = max([row["value"] for row in growth_rows] + [1])
    for row in growth_rows:
        row["width"] = max(8, int((row["value"] / growth_max) * 100)) if row["value"] else 0

    return render_template(
        "dashboard/admin_performance.html",
        active_page="admin",
        performance_rows=performance_rows,
        growth_rows=growth_rows,
        active_users=active_users,
        db_response_ms=db_response_ms,
        last_response_ms=last_response_ms,
        total_logs=total_logs,
    )


@dashboard.route("/admin/performance/active-users")
@login_required
@admin_required
def admin_active_users():
    active_users = count_active_sessions()
    db.session.commit()
    return jsonify({"active_users": active_users})


@dashboard.route("/guide/dismiss", methods=["POST"])
@login_required
def dismiss_guide():
    session["guide_dismissed"] = True
    flash("Guide hidden. You can still use the modules from the sidebar.")
    return redirect(url_for("dashboard.home"))


@dashboard.route("/guide/show", methods=["POST"])
@login_required
def show_guide():
    session["guide_dismissed"] = False
    return redirect(url_for("dashboard.home"))
