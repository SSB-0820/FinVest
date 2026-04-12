from extensions.db import db


DEFAULT_CATEGORIES = [
    ("Salary", "income"),
    ("Freelance", "income"),
    ("Bonus", "income"),
    ("Food", "expense"),
    ("Rent", "expense"),
    ("Clothes", "expense"),
    ("Electric Bills", "expense"),
    ("Transport", "expense"),
    ("Shopping", "expense"),
    ("Health", "expense"),
]


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Enum("income", "expense"), nullable=False)

    transactions = db.relationship("Transaction", backref="category", lazy=True)


def ensure_default_categories(user_id):
    existing_count = Category.query.filter_by(user_id=user_id).count()
    if existing_count:
        return

    for name, category_type in DEFAULT_CATEGORIES:
        db.session.add(Category(user_id=user_id, name=name, type=category_type))
