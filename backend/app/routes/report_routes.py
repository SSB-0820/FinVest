import csv
import io
import json
from datetime import datetime

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from app.models.account_model import Account
from app.models.activity_log_model import ActivityLog
from app.models.category_model import Category
from app.models.goal_model import Goal
from app.models.recurring_transaction_model import RecurringTransaction
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import UserSettings, get_or_create_user_settings
from app.services.notification_service import sync_notifications
from app.services.report_service import build_report_summary
from app.utils.activity_logger import log_activity
from app.utils.decorators import login_required
from extensions.db import db
from extensions.mongo import get_collection

reports = Blueprint("reports", __name__)


@reports.route("/reports")
@login_required
def report_list():
    user_id = session["user_id"]
    settings = get_or_create_user_settings(user_id)
    db.session.commit()

    start_raw = request.args.get("start_date", "").strip()
    end_raw = request.args.get("end_date", "").strip()
    category_id = request.args.get("category_id", "").strip()
    transaction_type = request.args.get("type", "").strip()

    start_date = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else None
    end_date = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else None
    category_filter = int(category_id) if category_id else None

    summary = build_report_summary(
        user_id,
        start_date=start_date,
        end_date=end_date,
        category_id=category_filter,
        transaction_type=transaction_type,
        save_snapshot=True,
    )
    categories = Category.query.filter_by(user_id=user_id).order_by(Category.name.asc()).all()
    report_snapshots = []
    collection = get_collection("report_snapshots")
    if collection is not None:
        report_snapshots = list(collection.find({"user_id": user_id}).sort("created_on", -1).limit(10))

    sync_notifications(user_id)

    return render_template(
        "dashboard/reports.html",
        active_page="reports",
        settings=settings,
        categories=categories,
        filters={
            "start_date": start_raw,
            "end_date": end_raw,
            "category_id": category_id,
            "type": transaction_type,
        },
        report_snapshots=report_snapshots,
        **summary,
    )


@reports.route("/reports/export/csv")
@login_required
def export_transactions_csv():
    user_id = session["user_id"]
    summary = build_report_summary(user_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["FinVest Analytics Summary"])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Income", f"{summary['total_income']:.2f}"])
    writer.writerow(["Total Expense", f"{summary['total_expense']:.2f}"])
    writer.writerow(["Net", f"{summary['net']:.2f}"])
    writer.writerow(["Average Monthly Spending", f"{summary['average_monthly_spending']:.2f}"])
    writer.writerow(["Savings Rate", f"{summary['savings_rate']:.2f}%"])
    writer.writerow(["Transaction Count", summary["transaction_count"]])
    if summary["top_category"]:
        writer.writerow(["Highest Expense Category", summary["top_category"][0]])
    writer.writerow([])
    writer.writerow(["Spending and Income Trends"])
    writer.writerow(["Trend", "Value", "Detail"])
    for item in summary["trend_rows"]:
        writer.writerow([item["label"], item["value"], item["detail"]])
    writer.writerow([])
    writer.writerow(["Income Source Chart Data"])
    writer.writerow(["Source", "Amount", "Percent"])
    for item in summary["income_source_rows"]:
        writer.writerow([item["name"], f"{item['amount']:.2f}", item["percent"]])
    writer.writerow([])
    writer.writerow(["Monthly Chart Data"])
    writer.writerow(["Month", "Income", "Expense", "Net"])
    for item in summary["monthly_rows"]:
        writer.writerow([item["label"], f"{item['income']:.2f}", f"{item['expense']:.2f}", f"{item['net']:.2f}"])
    writer.writerow([])
    writer.writerow(["Category Chart Data"])
    writer.writerow(["Category", "Amount", "Percent"])
    for item in summary["category_chart_rows"]:
        writer.writerow([item["name"], f"{item['amount']:.2f}", item["percent"]])
    writer.writerow([])
    writer.writerow(["Transactions"])
    writer.writerow(["Date", "Type", "Category", "Account", "Amount", "Description"])
    for item in summary["transactions"]:
        writer.writerow(
            [
                item.date.isoformat() if item.date else "",
                item.type,
                item.category.name if item.category else "",
                item.account.account_name if item.account else "",
                f"{item.amount:.2f}",
                item.description or "",
            ]
        )
    log_activity("transactions_exported", "Exported transactions to CSV")
    db.session.commit()
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=finvest-transactions.csv"},
    )


@reports.route("/reports/backup/json")
@login_required
def backup_user_data():
    user_id = session["user_id"]
    user = User.query.get_or_404(user_id)
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    accounts = Account.query.filter_by(user_id=user_id).all()
    categories = Category.query.filter_by(user_id=user_id).all()
    goals = Goal.query.filter_by(user_id=user_id).all()
    recurring = RecurringTransaction.query.filter_by(user_id=user_id).all()
    summary = build_report_summary(user_id)
    notifications = get_collection("activity_logs")

    payload = {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "settings": {
            "currency": settings.currency if settings else "INR",
            "locale": settings.locale if settings else "en-IN",
            "month_start_day": settings.month_start_day if settings else 1,
            "monthly_salary": float(settings.monthly_salary or 0) if settings else 0,
        },
        "accounts": [
            {
                "account_name": item.account_name,
                "type": item.type,
                "balance": float(item.balance or 0),
            }
            for item in accounts
        ],
        "categories": [
            {"name": item.name, "type": item.type}
            for item in categories
        ],
        "goals": [
            {
                "goal_name": item.goal_name,
                "target_amount": float(item.target_amount or 0),
                "current_amount": float(item.current_amount or 0),
                "monthly_contribution_amount": float(item.monthly_contribution_amount or 0),
                "last_contribution_date": item.last_contribution_date.isoformat() if item.last_contribution_date else None,
                "deadline": item.deadline.isoformat() if item.deadline else None,
                "status": item.status,
            }
            for item in goals
        ],
        "transactions": [
            {
                "date": item.date.isoformat() if item.date else None,
                "type": item.type,
                "category": item.category.name if item.category else "",
                "account": item.account.account_name if item.account else "",
                "amount": float(item.amount or 0),
                "description": item.description or "",
            }
            for item in Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).all()
        ],
        "recurring_transactions": [
            {
                "account": item.account.account_name if item.account else "",
                "category": item.category.name if item.category else "",
                "type": item.type,
                "amount": float(item.amount or 0),
                "frequency": item.frequency,
                "description": item.description or "",
                "start_date": item.start_date.isoformat() if item.start_date else None,
                "next_run_date": item.next_run_date.isoformat() if item.next_run_date else None,
                "is_active": bool(item.is_active),
            }
            for item in recurring
        ],
        "analytics": {
            "total_income": float(summary["total_income"]),
            "total_expense": float(summary["total_expense"]),
            "net": float(summary["net"]),
            "average_monthly_spending": float(summary["average_monthly_spending"]),
            "savings_rate": float(summary["savings_rate"]),
            "transaction_count": summary["transaction_count"],
            "top_category": summary["top_category"][0] if summary["top_category"] else None,
            "monthly_chart": [
                {
                    "label": item["label"],
                    "income": float(item["income"]),
                    "expense": float(item["expense"]),
                    "net": float(item["net"]),
                }
                for item in summary["monthly_rows"]
            ],
            "category_chart": [
                {
                    "name": item["name"],
                    "amount": float(item["amount"]),
                    "percent": item["percent"],
                }
                for item in summary["category_chart_rows"]
            ],
            "income_source_chart": [
                {
                    "name": item["name"],
                    "amount": float(item["amount"]),
                    "percent": item["percent"],
                }
                for item in summary["income_source_rows"]
            ],
            "trends": summary["trend_rows"],
        },
        "mongo_logs_available": notifications is not None,
    }

    log_activity("backup_downloaded", "Downloaded JSON backup")
    db.session.commit()
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=finvest-backup.json"},
    )
