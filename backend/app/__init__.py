from flask import Flask

from extensions.db import db
from app.routes.auth_routes import auth
from app.routes.dashboard_routes import dashboard


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "finvest_secret_123"
    app.config.from_object("config")

    db.init_app(app)
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)

    return app
