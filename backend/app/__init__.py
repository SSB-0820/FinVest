from time import perf_counter
from uuid import uuid4

from flask import Flask, g, session

from extensions.db import db
from extensions.mongo import init_mongo
from app.routes.auth_routes import auth
from app.routes.budget_routes import budgets
from app.routes.category_routes import categories
from app.routes.dashboard_routes import dashboard
from app.routes.goal_routes import goals
from app.routes.notification_routes import notifications
from app.routes.report_routes import reports
from app.routes.transaction_routes import transactions

# Import models so SQLAlchemy sees all tables before create_all runs.
from app.models.account_model import Account
from app.models.active_session_model import ActiveSession
from app.models.activity_log_model import ActivityLog
from app.models.budget_model import Budget
from app.models.category_model import Category
from app.models.goal_model import Goal
from app.models.notification_model import Notification
from app.models.recurring_transaction_model import RecurringTransaction
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import UserSettings
from app.services.active_session_service import touch_active_session
from app.services.automation_service import run_user_automations
from app.services.currency_service import EXCHANGE_RATES_INR, convert_from_inr, currency_symbol
from app.services.i18n_service import LANGUAGES, normalize_language
from app.services.notification_service import unread_notification_count
from app.services.schema_service import ensure_automation_schema


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "finvest_secret_123"
    app.config.from_object("config")

    db.init_app(app)
    init_mongo(app)
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(budgets)
    app.register_blueprint(goals)
    app.register_blueprint(categories)
    app.register_blueprint(notifications)
    app.register_blueprint(reports)
    app.register_blueprint(transactions)

    @app.before_request
    def run_due_finance_jobs():
        g.request_started_at = perf_counter()
        try:
            ensure_automation_schema()
            if session.get("user_id"):
                if not session.get("session_token"):
                    session["session_token"] = uuid4().hex
                touch_active_session(session.get("user_id"), session.get("session_token"))
                run_user_automations(session["user_id"])
                db.session.commit()
        except Exception:
            db.session.rollback()

    @app.after_request
    def capture_response_time(response):
        started_at = getattr(g, "request_started_at", None)
        if started_at is not None:
            app.config["LAST_RESPONSE_MS"] = round((perf_counter() - started_at) * 1000, 2)
        return response

    @app.context_processor
    def inject_layout_data():
        count = 0
        settings = None
        currency = "INR"
        language = "en"
        if session.get("user_id"):
            try:
                count = unread_notification_count(session["user_id"])
                settings = UserSettings.query.filter_by(user_id=session["user_id"]).first()
                if settings:
                    currency = settings.currency or "INR"
                    language = normalize_language(settings.language or settings.locale)
            except Exception:
                count = 0
        return {
            "unread_notification_count": count,
            "display_currency": currency,
            "display_currency_symbol": currency_symbol(currency),
            "display_currency_rates": EXCHANGE_RATES_INR,
            "display_language": language,
            "available_languages": LANGUAGES,
        }

    @app.template_filter("money")
    def money_filter(amount):
        currency = "INR"
        if session.get("user_id"):
            settings = UserSettings.query.filter_by(user_id=session["user_id"]).first()
            if settings:
                currency = settings.currency or "INR"
        return f"{currency_symbol(currency)} {convert_from_inr(amount, currency):.2f}"

    return app
