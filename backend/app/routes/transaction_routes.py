import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.account_model import Account, ensure_default_account
from app.models.category_model import Category, ensure_default_categories
from app.models.transaction_model import Transaction
from app.services.transaction_service import apply_transaction_effect
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


def _clean_import_row(row):
    return {
        (key or "").strip().lower(): (value or "").strip()
        for key, value in row.items()
    }


def _find_or_create_import_category(user_id, name, transaction_type):
    category = Category.query.filter_by(
        user_id=user_id, name=name, type=transaction_type
    ).first()
    if category:
        return category

    category = Category(user_id=user_id, name=name, type=transaction_type)
    db.session.add(category)
    db.session.flush()
    return category


def _find_import_account(user_id, account_name):
    if account_name:
        account = Account.query.filter_by(
            user_id=user_id, account_name=account_name
        ).first()
        if account:
            return account
    account = ensure_default_account(user_id)
    db.session.flush()
    return account


def _import_transaction_exists(user_id, account_id, category_id, transaction_type, amount, transaction_date, description):
    return Transaction.query.filter_by(
        user_id=user_id,
        account_id=account_id,
        category_id=category_id,
        type=transaction_type,
        amount=amount,
        date=transaction_date,
        description=description,
    ).first() is not None


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
    apply_transaction_effect(account, transaction_type, amount)
    log_activity(
        "transaction_added",
        f"Added {transaction_type} of {amount:.2f} in {category.name}",
    )
    db.session.commit()
    flash("Transaction added successfully")
    return redirect(url_for("transactions.transaction_list"))


@transactions.route("/transactions/import/csv", methods=["POST"])
@login_required
def import_transactions_csv():
    user_id = session["user_id"]
    upload = request.files.get("transaction_csv")
    if not upload or not upload.filename:
        flash("Choose a CSV file to import")
        return redirect(url_for("transactions.transaction_list"))

    try:
        stream = io.StringIO(upload.stream.read().decode("utf-8-sig"), newline=None)
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            flash("CSV file is empty")
            return redirect(url_for("transactions.transaction_list"))

        required_headers = {"date", "type", "category", "amount"}
        available_headers = {(header or "").strip().lower() for header in reader.fieldnames}
        missing_headers = required_headers - available_headers
        if missing_headers:
            flash(f"CSV is missing required columns: {', '.join(sorted(missing_headers))}")
            return redirect(url_for("transactions.transaction_list"))

        imported_count = 0
        skipped_count = 0
        error_rows = []

        for row_number, raw_row in enumerate(reader, start=2):
            row = _clean_import_row(raw_row)
            transaction_type = row.get("type", "").lower()
            category_name = row.get("category", "")
            description = row.get("description", "")

            if transaction_type not in {"income", "expense"} or not category_name:
                error_rows.append(str(row_number))
                continue

            try:
                amount = Decimal(row.get("amount", "0"))
                transaction_date = datetime.strptime(row.get("date", ""), "%Y-%m-%d").date()
            except (InvalidOperation, ValueError):
                error_rows.append(str(row_number))
                continue

            if amount <= 0:
                error_rows.append(str(row_number))
                continue

            category = _find_or_create_import_category(user_id, category_name, transaction_type)
            account = _find_import_account(user_id, row.get("account", ""))

            if _import_transaction_exists(
                user_id,
                account.id,
                category.id,
                transaction_type,
                amount,
                transaction_date,
                description,
            ):
                skipped_count += 1
                continue

            item = Transaction(
                user_id=user_id,
                account_id=account.id,
                category_id=category.id,
                type=transaction_type,
                amount=amount,
                date=transaction_date,
                description=description,
            )
            db.session.add(item)
            apply_transaction_effect(account, transaction_type, amount)
            imported_count += 1

        log_activity(
            "transactions_imported",
            f"Imported {imported_count} transaction(s), skipped {skipped_count} duplicate(s)",
        )
        db.session.commit()

        message = f"Imported {imported_count} transaction(s)"
        if skipped_count:
            message += f", skipped {skipped_count} duplicate(s)"
        if error_rows:
            message += f". Rows with errors: {', '.join(error_rows[:8])}"
            if len(error_rows) > 8:
                message += "..."
        flash(message)
    except UnicodeDecodeError:
        db.session.rollback()
        flash("CSV must be saved as UTF-8 text")
    except Exception:
        db.session.rollback()
        flash("Could not import CSV. Please check the file format and try again")

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
        apply_transaction_effect(old_account, item.type, item.amount, reverse=True)

    item.account_id = account_id
    item.category_id = category_id
    item.type = transaction_type
    item.amount = new_amount
    item.date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
    item.description = request.form.get("description", "").strip()
    apply_transaction_effect(account, item.type, item.amount)
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
        apply_transaction_effect(account, item.type, item.amount, reverse=True)
    log_activity(
        "transaction_deleted",
        f"Deleted {item.type} transaction of {Decimal(item.amount or 0):.2f}",
    )
    db.session.delete(item)
    db.session.commit()
    flash("Transaction deleted successfully")
    return redirect(url_for("transactions.transaction_list"))
