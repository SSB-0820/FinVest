from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.account_model import Account, ensure_default_account
from app.models.category_model import Category, ensure_default_categories
from app.models.transaction_model import Transaction
from app.utils.activity_logger import log_activity
from app.utils.decorators import login_required
from extensions.db import db

transactions = Blueprint("transactions", __name__)


def _load_transaction_support_data(user_id):
    ensure_default_categories(user_id)
    ensure_default_account(user_id)
    db.session.commit()
    accounts = Account.query.filter_by(user_id=user_id).order_by(Account.account_name.asc()).all()
    categories = (
        Category.query.filter_by(user_id=user_id)
        .order_by(Category.type.asc(), Category.name.asc())
        .all()
    )
    return accounts, categories


def _apply_transaction_effect(account, transaction_type, amount, reverse=False):
    signed_amount = Decimal(amount or 0)
    if transaction_type == "expense":
        signed_amount *= Decimal("-1")
    if reverse:
        signed_amount *= Decimal("-1")
    account.balance = Decimal(account.balance or 0) + signed_amount


@transactions.route("/transactions")
@login_required
def transaction_list():
    user_id = session["user_id"]
    accounts, categories_data = _load_transaction_support_data(user_id)

    query = Transaction.query.filter_by(user_id=user_id)
    transaction_type = request.args.get("type", "").strip()
    category_id = request.args.get("category_id", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    min_amount = request.args.get("min_amount", "").strip()
    max_amount = request.args.get("max_amount", "").strip()

    if transaction_type:
        query = query.filter_by(type=transaction_type)
    if category_id:
        query = query.filter_by(category_id=int(category_id))
    if start_date:
        query = query.filter(Transaction.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.filter(Transaction.date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    if min_amount:
        query = query.filter(Transaction.amount >= Decimal(min_amount))
    if max_amount:
        query = query.filter(Transaction.amount <= Decimal(max_amount))

    items = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    return render_template(
        "dashboard/transactions_clean.html",
        active_page="transactions",
        transactions=items,
        accounts=accounts,
        categories=categories_data,
        filters={
            "type": transaction_type,
            "category_id": category_id,
            "start_date": start_date,
            "end_date": end_date,
            "min_amount": min_amount,
            "max_amount": max_amount,
        },
    )


@transactions.route("/transactions", methods=["POST"])
@login_required
def add_transaction():
    user_id = session["user_id"]
    account_id = int(request.form.get("account_id"))
    category_id = int(request.form.get("category_id"))
    transaction_type = request.form.get("type", "expense").strip()
    description = request.form.get("description", "").strip()

    try:
        amount = Decimal(request.form.get("amount", "0"))
    except InvalidOperation:
        flash("Amount must be a valid number")
        return redirect(url_for("transactions.transaction_list"))

    if amount <= 0:
        flash("Amount must be greater than 0")
        return redirect(url_for("transactions.transaction_list"))

    transaction_date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
    category = Category.query.filter_by(id=category_id, user_id=user_id).first()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()

    if not category or not account:
        flash("Please choose a valid account and category")
        return redirect(url_for("transactions.transaction_list"))

    if category.type != transaction_type:
        flash("Category type and transaction type must match")
        return redirect(url_for("transactions.transaction_list"))

    item = Transaction(
        user_id=user_id,
        account_id=account_id,
        category_id=category_id,
        type=transaction_type,
        amount=amount,
        date=transaction_date,
        description=description,
    )
    db.session.add(item)
    _apply_transaction_effect(account, transaction_type, amount)
    log_activity(
        "transaction_added",
        f"Added {transaction_type} of {amount:.2f} in {category.name}",
    )
    db.session.commit()
    flash("Transaction added successfully")
    return redirect(url_for("transactions.transaction_list"))


@transactions.route("/transactions/<int:transaction_id>/edit", methods=["POST"])
@login_required
def edit_transaction(transaction_id):
    user_id = session["user_id"]
    item = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first_or_404()
    category_id = int(request.form.get("category_id"))
    account_id = int(request.form.get("account_id"))
    transaction_type = request.form.get("type", "expense").strip()
    new_amount = Decimal(request.form.get("amount", "0") or "0")
    category = Category.query.filter_by(id=category_id, user_id=user_id).first()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()

    if not category or not account:
        flash("Please choose a valid account and category")
        return redirect(url_for("transactions.transaction_list"))

    if category.type != transaction_type:
        flash("Category type and transaction type must match")
        return redirect(url_for("transactions.transaction_list"))
    if new_amount <= 0:
        flash("Amount must be greater than 0")
        return redirect(url_for("transactions.transaction_list"))

    old_account = Account.query.filter_by(id=item.account_id, user_id=user_id).first()
    if old_account:
        _apply_transaction_effect(old_account, item.type, item.amount, reverse=True)

    item.account_id = account_id
    item.category_id = category_id
    item.type = transaction_type
    item.amount = new_amount
    item.date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
    item.description = request.form.get("description", "").strip()
    _apply_transaction_effect(account, item.type, item.amount)
    log_activity(
        "transaction_updated",
        f"Updated transaction #{item.id} to {item.type} {item.amount:.2f} in {category.name}",
    )
    db.session.commit()
    flash("Transaction updated successfully")
    return redirect(url_for("transactions.transaction_list"))


@transactions.route("/transactions/<int:transaction_id>/delete", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    item = Transaction.query.filter_by(id=transaction_id, user_id=session["user_id"]).first_or_404()
    account = Account.query.filter_by(id=item.account_id, user_id=session["user_id"]).first()
    if account:
        _apply_transaction_effect(account, item.type, item.amount, reverse=True)
    log_activity(
        "transaction_deleted",
        f"Deleted {item.type} transaction of {Decimal(item.amount or 0):.2f}",
    )
    db.session.delete(item)
    db.session.commit()
    flash("Transaction deleted successfully")
    return redirect(url_for("transactions.transaction_list"))
