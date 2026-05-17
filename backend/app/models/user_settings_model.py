from extensions.db import db


class UserSettings(db.Model):
    __tablename__ = "user_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    currency = db.Column(db.String(10), default="INR")
    locale = db.Column(db.String(20), default="en-IN")
    language = db.Column(db.String(10), default="en")
    month_start_day = db.Column(db.Integer, default=1)
    monthly_salary = db.Column(db.Numeric(12, 2), default=0)
    monthly_salary_last_added = db.Column(db.Date)


def get_or_create_user_settings(user_id):
    settings = UserSettings.query.filter_by(user_id=user_id).first()
    if settings:
        return settings

    settings = UserSettings(user_id=user_id)
    db.session.add(settings)
    return settings
