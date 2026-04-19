from flask import Flask, session

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
from app.models.activity_log_model import ActivityLog
from app.models.budget_model import Budget
from app.models.category_model import Category
from app.models.goal_model import Goal
from app.models.notification_model import Notification
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import UserSettings
from app.services.notification_service import unread_notification_count


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

    @app.context_processor
    def inject_layout_data():
        count = 0
        if session.get("user_id"):
            try:
                count = unread_notification_count(session["user_id"])
            except Exception:
                count = 0
        return {"unread_notification_count": count}

    return app
