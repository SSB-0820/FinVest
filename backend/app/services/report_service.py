from collections import defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json

from app.models.transaction_model import Transaction
from extensions.db import db
from extensions.mongo import get_collection


def build_report_summary(
    user_id,
    start_date=None,
    end_date=None,
    category_id=None,
    transaction_type="",
    save_snapshot=False,
):
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
    income_source_totals = defaultdict(Decimal)
    expense_category_totals = defaultdict(Decimal)
    monthly_totals = defaultdict(lambda: {"income": Decimal("0"), "expense": Decimal("0")})
    for item in transactions:
        if item.category:
            category_totals[item.category.name] += Decimal(item.amount or 0)
            if item.type == "expense":
                expense_category_totals[item.category.name] += Decimal(item.amount or 0)
            elif item.type == "income":
                income_source_totals[item.category.name] += Decimal(item.amount or 0)
        if item.date:
            key = item.date.strftime("%Y-%m")
            monthly_totals[key][item.type] += Decimal(item.amount or 0)

    monthly_rows = [
        {
            "label": date(int(label[:4]), int(label[5:]), 1).strftime("%b %Y"),
            "income": values["income"],
            "expense": values["expense"],
            "net": values["income"] - values["expense"],
        }
        for label, values in sorted(monthly_totals.items())
    ]
    average_monthly_spending = Decimal("0")
    expense_months = [row["expense"] for row in monthly_rows if row["expense"] > 0]
    if expense_months:
        average_monthly_spending = sum(expense_months) / Decimal(len(expense_months))

    savings_rate = Decimal("0")
    if total_income:
        savings_rate = ((total_income - total_expense) / total_income) * Decimal("100")

    top_category = None
    if expense_category_totals:
        top_category = max(expense_category_totals.items(), key=lambda row: row[1])

    monthly_max = max(
        [max(row["income"], row["expense"]) for row in monthly_rows] + [Decimal("1")]
    )
    for row in monthly_rows:
        row["income_width"] = int((row["income"] / monthly_max) * 100)
        row["expense_width"] = int((row["expense"] / monthly_max) * 100)

    category_max = max(list(expense_category_totals.values()) + [Decimal("1")])
    category_chart_rows = [
        {
            "name": name,
            "amount": amount,
            "percent": round(float((amount / total_expense) * 100), 1) if total_expense else 0,
            "width": int((amount / category_max) * 100),
        }
        for name, amount in sorted(expense_category_totals.items(), key=lambda row: row[1], reverse=True)
    ]
    category_pie_rows = [
        {"name": row["name"], "amount": float(row["amount"]), "percent": row["percent"]}
        for row in category_chart_rows
    ]

    income_max = max(list(income_source_totals.values()) + [Decimal("1")])
    income_source_rows = [
        {
            "name": name,
            "amount": amount,
            "percent": round(float((amount / total_income) * 100), 1) if total_income else 0,
            "width": int((amount / income_max) * 100),
        }
        for name, amount in sorted(income_source_totals.items(), key=lambda row: row[1], reverse=True)
    ]

    trend_rows = []
    if top_category:
        trend_rows.append(
            {
                "label": "Highest spending category",
                "value": top_category[0],
                "detail": f"{top_category[0]} accounts for {round(float((top_category[1] / total_expense) * 100), 1) if total_expense else 0}% of expenses.",
                "tone": "red",
            }
        )
    if income_source_rows:
        top_income = income_source_rows[0]
        trend_rows.append(
            {
                "label": "Main income source",
                "value": top_income["name"],
                "detail": f"{top_income['name']} contributes {top_income['percent']}% of income.",
                "tone": "green",
            }
        )
    if len(monthly_rows) >= 2:
        previous = monthly_rows[-2]["expense"]
        current = monthly_rows[-1]["expense"]
        if previous:
            change = ((current - previous) / previous) * Decimal("100")
            direction = "increased" if change >= 0 else "decreased"
            trend_rows.append(
                {
                    "label": "Recent spending movement",
                    "value": f"{abs(change):.1f}%",
                    "detail": f"Spending {direction} compared with the previous month.",
                    "tone": "red" if change >= 0 else "green",
                }
            )

    summary = {
        "transactions": transactions,
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
        "category_rows": sorted(category_totals.items(), key=lambda row: row[1], reverse=True),
        "monthly_rows": monthly_rows,
        "category_chart_rows": category_chart_rows,
        "category_pie_rows": category_pie_rows,
        "income_source_rows": income_source_rows,
        "trend_rows": trend_rows,
        "average_monthly_spending": average_monthly_spending,
        "savings_rate": savings_rate,
        "top_category": top_category,
        "transaction_count": len(transactions),
    }

    if save_snapshot:
        snapshot = {
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
            "last_transaction_id": transactions[0].id if transactions else None,
            "trends": trend_rows,
            "category_chart": [
                {"name": row["name"], "amount": float(row["amount"]), "percent": row["percent"]}
                for row in category_chart_rows
            ],
            "income_sources": [
                {"name": row["name"], "amount": float(row["amount"]), "percent": row["percent"]}
                for row in income_source_rows
            ],
        }
        snapshot["fingerprint"] = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        collection = get_collection("report_snapshots")
        if collection is not None:
            existing = collection.find_one(
                {"user_id": user_id, "fingerprint": snapshot["fingerprint"]}
            )
            if existing is None:
                collection.insert_one(snapshot)

    return summary
