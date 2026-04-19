from datetime import date
from decimal import Decimal

from app.models.budget_model import Budget
from app.models.goal_model import Goal
from app.models.notification_model import Notification
from app.models.transaction_model import Transaction
from extensions.db import db


def create_notification(user_id, title, message, notification_type, reference_key):
    existing = Notification.query.filter_by(
        user_id=user_id,
        notification_type=notification_type,
        reference_key=reference_key,
        message=message,
    ).first()
    if existing:
        return existing

    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        reference_key=reference_key,
    )
    db.session.add(notification)
    return notification


def sync_notifications(user_id):
    today = date.today()

    welcome_key = f"welcome-{user_id}"
    create_notification(
        user_id,
        "Welcome to FinVest",
        "Use the dashboard, budgets, goals, and reports to manage your finances.",
        "welcome",
        welcome_key,
    )

    budgets = Budget.query.filter_by(user_id=user_id, month=today.month, year=today.year).all()
    for budget in budgets:
        spent = Decimal("0")
        expenses = (
            Transaction.query.filter_by(user_id=user_id, category_id=budget.category_id, type="expense")
            .filter(db.extract("month", Transaction.date) == today.month)
            .filter(db.extract("year", Transaction.date) == today.year)
            .all()
        )
        for item in expenses:
            spent += Decimal(item.amount or 0)

        limit_amount = Decimal(budget.limit_amount or 0)
        if not limit_amount:
            continue
        percent = int((spent / limit_amount) * 100)
        if percent >= 100:
            create_notification(
                user_id,
                "Budget Exceeded",
                f"{budget.category.name} crossed 100% of this month's budget.",
                "budget",
                f"budget-{budget.id}-100",
            )
        elif percent >= 80:
            create_notification(
                user_id,
                "Budget Alert",
                f"{budget.category.name} reached {percent}% of this month's budget.",
                "budget",
                f"budget-{budget.id}-80",
            )

    goals = Goal.query.filter_by(user_id=user_id).all()
    for goal in goals:
        if goal.deadline:
            days_left = (goal.deadline - today).days
            if 0 <= days_left <= 7:
                create_notification(
                    user_id,
                    "Goal Deadline Near",
                    f"{goal.goal_name} is due in {days_left} day(s).",
                    "goal",
                    f"goal-{goal.id}-deadline",
                )

    db.session.commit()


def unread_notification_count(user_id):
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()
