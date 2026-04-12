from extensions.db import db


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Enum("Cash", "Bank", "UPI"), nullable=False)
    balance = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(
        db.TIMESTAMP, server_default=db.func.current_timestamp()
    )

    transactions = db.relationship("Transaction", backref="account", lazy=True)


def ensure_default_account(user_id):
    account = Account.query.filter_by(user_id=user_id).first()
    if account:
        return account

    account = Account(
        user_id=user_id,
        account_name="Cash Wallet",
        type="Cash",
        balance=0,
    )
    db.session.add(account)
    return account
