from datetime import datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.account_model import ensure_default_account
from app.models.goal_model import Goal
from app.models.user_settings_model import get_or_create_user_settings
from app.services.transaction_service import apply_transaction_effect
from app.utils.activity_logger import log_activity
from app.utils.decorators import login_required
from extensions.db import db

goals = Blueprint("goals", __name__)


@goals.route("/goals")
@login_required
def goal_list():
    settings = get_or_create_user_settings(session["user_id"])
    db.session.commit()

    items = (
        Goal.query.filter_by(user_id=session["user_id"])
        .order_by(Goal.id.desc())
        .all()
    )

    goal_rows = []
    for item in items:
        target = Decimal(item.target_amount or 0)
        current = Decimal(item.current_amount or 0)
        percent = int((current / target) * 100) if target else 0
        goal_rows.append(
            {
                "goal": item,
                "percent": max(0, min(percent, 100)),
                "remaining": max(Decimal("0"), target - current),
            }
        )

    return render_template(
        "dashboard/goals.html",
        active_page="goals",
        goals=goal_rows,
        settings=settings,
    )


@goals.route("/goals", methods=["POST"])
@login_required
def add_goal():
    goal_name = request.form.get("goal_name", "").strip()
    target_amount = Decimal(request.form.get("target_amount", "0") or "0")
    current_amount = Decimal(request.form.get("current_amount", "0") or "0")
    deadline_raw = request.form.get("deadline", "").strip()
    status = request.form.get("status", "In Progress").strip() or "In Progress"

    if not goal_name:
        flash("Goal name is required")
        return redirect(url_for("goals.goal_list"))
    if target_amount <= 0:
        flash("Target amount must be greater than 0")
        return redirect(url_for("goals.goal_list"))
    if current_amount < 0:
        flash("Current amount cannot be negative")
        return redirect(url_for("goals.goal_list"))

    existing = Goal.query.filter(
        Goal.user_id == session["user_id"],
        db.func.lower(Goal.goal_name) == goal_name.lower(),
        Goal.target_amount == target_amount,
    ).first()
    if existing:
        flash("Goal already exists with the same name and amount")
        return redirect(url_for("goals.goal_list"))

    deadline = None
    if deadline_raw:
        deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").date()

    db.session.add(
        Goal(
            user_id=session["user_id"],
            goal_name=goal_name,
            target_amount=target_amount,
            current_amount=current_amount,
            deadline=deadline,
            status=status,
        )
    )
    log_activity("goal_added", f"Added saving goal {goal_name}")
    db.session.commit()
    flash("Goal added successfully")
    return redirect(url_for("goals.goal_list"))


@goals.route("/goals/<int:goal_id>/update", methods=["POST"])
@login_required
def update_goal(goal_id):
    item = Goal.query.filter_by(id=goal_id, user_id=session["user_id"]).first_or_404()
    goal_name = request.form.get("goal_name", "").strip() or item.goal_name
    target_amount = Decimal(request.form.get("target_amount", item.target_amount) or item.target_amount)
    duplicate = Goal.query.filter(
        Goal.user_id == session["user_id"],
        Goal.id != item.id,
        db.func.lower(Goal.goal_name) == goal_name.lower(),
        Goal.target_amount == target_amount,
    ).first()
    if duplicate:
        flash("Goal already exists with the same name and amount")
        return redirect(url_for("goals.goal_list"))
    if target_amount <= 0:
        flash("Target amount must be greater than 0")
        return redirect(url_for("goals.goal_list"))
    if Decimal(request.form.get("current_amount", item.current_amount) or item.current_amount) < 0:
        flash("Current amount cannot be negative")
        return redirect(url_for("goals.goal_list"))

    item.goal_name = goal_name
    item.target_amount = target_amount
    item.current_amount = Decimal(request.form.get("current_amount", item.current_amount) or item.current_amount)
    item.status = request.form.get("status", item.status).strip() or item.status

    deadline_raw = request.form.get("deadline", "").strip()
    item.deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").date() if deadline_raw else None
    if Decimal(item.current_amount or 0) >= Decimal(item.target_amount or 0):
        item.status = "Completed"

    log_activity("goal_updated", f"Updated saving goal {item.goal_name}")
    db.session.commit()
    flash("Goal updated successfully")
    return redirect(url_for("goals.goal_list"))


@goals.route("/goals/<int:goal_id>/add-amount", methods=["POST"])
@login_required
def add_goal_amount(goal_id):
    item = Goal.query.filter_by(id=goal_id, user_id=session["user_id"]).first_or_404()
    amount_to_add = Decimal(request.form.get("amount_to_add", "0") or "0")

    if amount_to_add <= 0:
        flash("Add amount must be greater than 0")
        return redirect(url_for("goals.goal_list"))

    account = ensure_default_account(session["user_id"])
    if Decimal(account.balance or 0) < amount_to_add:
        db.session.rollback()
        flash("Not enough balance in your default account to add this goal amount")
        return redirect(url_for("goals.goal_list"))

    item.current_amount = Decimal(item.current_amount or 0) + amount_to_add
    apply_transaction_effect(account, "expense", amount_to_add)
    if Decimal(item.current_amount or 0) >= Decimal(item.target_amount or 0):
        item.status = "Completed"

    log_activity(
        "goal_progress_added",
        f"Added {amount_to_add:.2f} to goal {item.goal_name}",
    )
    db.session.commit()
    flash("Goal amount updated successfully")
    return redirect(url_for("goals.goal_list"))


@goals.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    item = Goal.query.filter_by(id=goal_id, user_id=session["user_id"]).first_or_404()
    log_activity("goal_deleted", f"Deleted saving goal {item.goal_name}")
    db.session.delete(item)
    db.session.commit()
    flash("Goal deleted successfully")
    return redirect(url_for("goals.goal_list"))
