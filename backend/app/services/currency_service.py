EXCHANGE_RATES_INR = {
    "INR": 1.0,
    "USD": 1 / 92.70,
    "EUR": 1 / 106.88,
    "GBP": 1 / 125.92,
}

CURRENCY_SYMBOLS = {
    "INR": "Rs.",
    "USD": "$",
    "EUR": "EUR",
    "GBP": "GBP",
}


def convert_from_inr(amount, currency):
    return float(amount or 0) * EXCHANGE_RATES_INR.get(currency or "INR", 1.0)


def currency_symbol(currency):
    return CURRENCY_SYMBOLS.get(currency or "INR", currency or "INR")
