from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.models.transaction_model import Transaction
from extensions.db import db
from extensions.mongo import insert_document


def build_report_summary(user_id, start_date=None, end_date=None, category_id=None, transaction_type=""):
    query = Transaction.query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if transaction_type:
        query = query.filter_by(type=transaction_type)

    transactions = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    total_income = sum(Decimal(item.amount or 0) for item in transactions if item.type == "income")
    total_expense = sum(Decimal(item.amount or 0) for item in transactions if item.type == "expense")

    category_totals = defaultdict(Decimal)
    monthly_totals = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0")})
    for item in transactions:
        if item.category:
            category_totals[item.category.name] += Decimal(item.amount or 0)
        if item.date:
            key = item.date.strftime("%b %Y")
            monthly_totals[key][item.type] += Decimal(item.amount or 0)

    summary = {
        "transactions": transactions,
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
        "category_rows": sorted(category_totals.items(), key=lambda row: row[1], reverse=True),
        "monthly_rows": [
            {"label": label, "income": values["income"], "expense": values["expense"]}
            for label, values in monthly_totals.items()
        ],
    }

    insert_document(
        "report_snapshots",
        {
            "user_id": user_id,
            "created_on": date.today().isoformat(),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "category_id": category_id,
            "transaction_type": transaction_type,
            "total_income": float(total_income),
            "total_expense": float(total_expense),
            "net": float(summary["net"]),
            "transaction_count": len(transactions),
        },
    )

    return summary
