from extensions.db import db


class RecurringTransaction(db.Model):
    __tablename__ = "recurring_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id = db.Column(
        db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(db.Enum("income", "expense"), nullable=False, default="expense")
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(255))
    frequency = db.Column(db.Enum("daily", "monthly", "yearly"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    next_run_date = db.Column(db.Date, nullable=False)
    last_run_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.text("1"))
    created_at = db.Column(
        db.TIMESTAMP, server_default=db.func.current_timestamp()
    )

    account = db.relationship("Account", backref="recurring_transactions", lazy=True)
    category = db.relationship("Category", backref="recurring_transactions", lazy=True)
