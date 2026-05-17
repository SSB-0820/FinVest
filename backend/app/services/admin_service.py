from werkzeug.security import generate_password_hash

from app.models.user_model import User
from app.utils.decorators import ADMIN_EMAIL
from extensions.db import db


def seed_default_admin():
    existing = User.query.filter_by(email=ADMIN_EMAIL).first()
    if existing:
        if existing.role != "admin":
            existing.role = "admin"
        return existing

    admin = User(
        name="Admin",
        email=ADMIN_EMAIL,
        role="admin",
        password_hash=generate_password_hash("admin@123"),
    )
    db.session.add(admin)
    db.session.commit()
    return admin
