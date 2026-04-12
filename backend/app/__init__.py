from flask import Flask

from extensions.db import db
from app.routes.auth_routes import auth
from app.routes.budget_routes import budgets
from app.routes.category_routes import categories
from app.routes.dashboard_routes import dashboard
from app.routes.goal_routes import goals
from app.routes.transaction_routes import transactions

# Import models so SQLAlchemy sees all tables before create_all runs.
from app.models.account_model import Account
from app.models.budget_model import Budget
from app.models.category_model import Category
from app.models.goal_model import Goal
from app.models.transaction_model import Transaction
from app.models.user_model import User
from app.models.user_settings_model import UserSettings


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "finvest_secret_123"
    app.config.from_object("config")

    db.init_app(app)
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(budgets)
    app.register_blueprint(goals)
    app.register_blueprint(categories)
    app.register_blueprint(transactions)

    return app
