from datetime import datetime
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.goal_model import Goal
from app.models.user_settings_model import get_or_create_user_settings
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
    db.session.commit()
    flash("Goal added successfully")
    return redirect(url_for("goals.goal_list"))


@goals.route("/goals/<int:goal_id>/update", methods=["POST"])
@login_required
def update_goal(goal_id):
    item = Goal.query.filter_by(id=goal_id, user_id=session["user_id"]).first_or_404()
    item.goal_name = request.form.get("goal_name", "").strip() or item.goal_name
    item.target_amount = Decimal(request.form.get("target_amount", item.target_amount) or item.target_amount)
    item.current_amount = Decimal(request.form.get("current_amount", item.current_amount) or item.current_amount)
    item.status = request.form.get("status", item.status).strip() or item.status

    deadline_raw = request.form.get("deadline", "").strip()
    item.deadline = datetime.strptime(deadline_raw, "%Y-%m-%d").date() if deadline_raw else None

    db.session.commit()
    flash("Goal updated successfully")
    return redirect(url_for("goals.goal_list"))


@goals.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    item = Goal.query.filter_by(id=goal_id, user_id=session["user_id"]).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Goal deleted successfully")
    return redirect(url_for("goals.goal_list"))
