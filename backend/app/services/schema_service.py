from sqlalchemy import inspect, text

from extensions.db import db


_schema_checked = False


def ensure_automation_schema():
    global _schema_checked
    if _schema_checked:
        return

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "security_answers" not in columns:
            db.session.execute(
                text("ALTER TABLE users ADD COLUMN security_answers TEXT NULL")
            )
    if "user_settings" in tables:
        columns = {column["name"] for column in inspector.get_columns("user_settings")}
        if "monthly_salary_last_added" not in columns:
            db.session.execute(
                text("ALTER TABLE user_settings ADD COLUMN monthly_salary_last_added DATE NULL")
            )
        if "language" not in columns:
            db.session.execute(
                text("ALTER TABLE user_settings ADD COLUMN language VARCHAR(10) DEFAULT 'en'")
            )

    if "recurring_transactions" not in tables or "active_sessions" not in tables:
        db.create_all()

    db.session.commit()
    _schema_checked = True
