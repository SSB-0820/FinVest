
from decimal import Decimal


def apply_transaction_effect(account, transaction_type, amount, reverse=False):
    signed_amount = Decimal(amount or 0)
    if transaction_type == "expense":
        signed_amount *= Decimal("-1")
    if reverse:
        signed_amount *= Decimal("-1")
    account.balance = Decimal(account.balance or 0) + signed_amount
