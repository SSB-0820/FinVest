from extensions.db import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    reference_key = db.Column(db.String(120))
    is_read = db.Column(db.Boolean, nullable=False, server_default=db.text("0"))
    created_at = db.Column(
        db.TIMESTAMP, server_default=db.func.current_timestamp()
    )
