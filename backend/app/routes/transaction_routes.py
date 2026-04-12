from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.account_model import Account, ensure_default_account
from app.models.category_model import Category, ensure_default_categories
from app.models.transaction_model import Transaction
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

    if transaction_type:
        query = query.filter_by(type=transaction_type)
    if category_id:
        query = query.filter_by(category_id=int(category_id))
    if start_date:
        query = query.filter(Transaction.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.filter(Transaction.date <= datetime.strptime(end_date, "%Y-%m-%d").date())

    items = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    return render_template(
        "dashboard/transactions.html",
        active_page="transactions",
        transactions=items,
        accounts=accounts,
        categories=categories_data,
        filters={
            "type": transaction_type,
            "category_id": category_id,
            "start_date": start_date,
            "end_date": end_date,
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

    transaction_date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
    category = Category.query.filter_by(id=category_id, user_id=user_id).first()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()

    if not category or not account:
        flash("Please choose a valid account and category")
        return redirect(url_for("transactions.transaction_list"))

    if category.type != transaction_type:
        flash("Category type and transaction type must match")
        return redirect(url_for("transactions.transaction_list"))

    db.session.add(
        Transaction(
            user_id=user_id,
            account_id=account_id,
            category_id=category_id,
            type=transaction_type,
            amount=amount,
            date=transaction_date,
            description=description,
        )
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
    category = Category.query.filter_by(id=category_id, user_id=user_id).first()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()

    if not category or not account:
        flash("Please choose a valid account and category")
        return redirect(url_for("transactions.transaction_list"))

    if category.type != transaction_type:
        flash("Category type and transaction type must match")
        return redirect(url_for("transactions.transaction_list"))

    item.account_id = account_id
    item.category_id = category_id
    item.type = transaction_type
    item.amount = Decimal(request.form.get("amount", "0") or "0")
    item.date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
    item.description = request.form.get("description", "").strip()
    db.session.commit()
    flash("Transaction updated successfully")
    return redirect(url_for("transactions.transaction_list"))


@transactions.route("/transactions/<int:transaction_id>/delete", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    item = Transaction.query.filter_by(id=transaction_id, user_id=session["user_id"]).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Transaction deleted successfully")
    return redirect(url_for("transactions.transaction_list"))
