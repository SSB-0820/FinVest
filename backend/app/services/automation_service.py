from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from app.models.account_model import Account, ensure_default_account
from app.models.category_model import Category, ensure_default_categories
from app.models.goal_model import Goal
from app.models.recurring_transaction_model import RecurringTransaction
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import UserSettings, get_or_create_user_settings
from app.services.transaction_service import apply_transaction_effect
from extensions.db import db


def ensure_income_category(user_id, name="Salary"):
    category = Category.query.filter_by(user_id=user_id, name=name, type="income").first()
    if category:
        return category
    category = Category(user_id=user_id, name=name, type="income")
    db.session.add(category)
    db.session.flush()
    return category


def _add_months(day, months=1):
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, monthrange(year, month)[1]))


def _next_date(day, frequency):
    if frequency == "daily":
        return day + timedelta(days=1)
    if frequency == "yearly":
        try:
            return day.replace(year=day.year + 1)
        except ValueError:
            return day.replace(year=day.year + 1, day=28)
    return _add_months(day, 1)


def _salary_due(settings, today):
    if not settings.monthly_salary or Decimal(settings.monthly_salary or 0) <= 0:
        return False
    if not settings.monthly_salary_last_added:
        return True
    return (
        settings.monthly_salary_last_added.year,
        settings.monthly_salary_last_added.month,
    ) != (today.year, today.month)


def process_monthly_salary(user_id, today=None):
    today = today or date.today()
    ensure_default_categories(user_id)
    account = ensure_default_account(user_id)
    settings = get_or_create_user_settings(user_id)
    db.session.flush()

    if not _salary_due(settings, today):
        return 0

    category = ensure_income_category(user_id)
    amount = Decimal(settings.monthly_salary or 0)
    transaction = Transaction(
        user_id=user_id,
        account_id=account.id,
        category_id=category.id,
        type="income",
        amount=amount,
        date=today,
        description=f"Automatic monthly income for {today:%B %Y}",
    )
    db.session.add(transaction)
    apply_transaction_effect(account, "income", amount)
    settings.monthly_salary_last_added = today
    return 1


def process_recurring_transactions(user_id, today=None):
    today = today or date.today()
    created = 0
    items = RecurringTransaction.query.filter_by(user_id=user_id, is_active=True).all()

    for item in items:
        while item.next_run_date and item.next_run_date <= today:
            account = Account.query.filter_by(id=item.account_id, user_id=user_id).first()
            category = Category.query.filter_by(id=item.category_id, user_id=user_id).first()
            if not account or not category:
                item.is_active = False
                break

            run_date = item.next_run_date
            transaction = Transaction(
                user_id=user_id,
                account_id=account.id,
                category_id=category.id,
                type=item.type,
                amount=Decimal(item.amount or 0),
                date=run_date,
                description=item.description or f"Automatic {item.frequency} {item.type}",
            )
            db.session.add(transaction)
            apply_transaction_effect(account, item.type, item.amount)
            item.last_run_date = run_date
            item.next_run_date = _next_date(run_date, item.frequency)
            created += 1

    return created


def _goal_contribution_due(goal, today):
    amount = Decimal(goal.monthly_contribution_amount or 0)
    if amount <= 0 or goal.status != "In Progress":
        return False
    if Decimal(goal.current_amount or 0) >= Decimal(goal.target_amount or 0):
        return False
    if not goal.last_contribution_date:
        return True
    return (
        goal.last_contribution_date.year,
        goal.last_contribution_date.month,
    ) != (today.year, today.month)


def process_goal_contributions(user_id, today=None):
    today = today or date.today()
    created = 0
    account = ensure_default_account(user_id)
    goals = Goal.query.filter_by(user_id=user_id).all()
    db.session.flush()

    for goal in goals:
        if not _goal_contribution_due(goal, today):
            continue

        target = Decimal(goal.target_amount or 0)
        current = Decimal(goal.current_amount or 0)
        remaining = max(Decimal("0"), target - current)
        contribution = min(Decimal(goal.monthly_contribution_amount or 0), remaining)
        if contribution <= 0:
            continue
        if Decimal(account.balance or 0) < contribution:
            continue

        goal.current_amount = current + contribution
        goal.last_contribution_date = today
        apply_transaction_effect(account, "expense", contribution)
        if Decimal(goal.current_amount or 0) >= target:
            goal.status = "Completed"
        created += 1

    return created


def run_user_automations(user_id, today=None, commit=True):
    created = process_monthly_salary(user_id, today=today)
    created += process_recurring_transactions(user_id, today=today)
    created += process_goal_contributions(user_id, today=today)
    if commit:
        db.session.commit()
    return created


def run_all_automations(today=None):
    total = 0
    for user in User.query.filter_by(is_active=True).all():
        total += run_user_automations(user.id, today=today, commit=False)
    db.session.commit()
    return total
