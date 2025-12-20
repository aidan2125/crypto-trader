# utils/currency.py

SUPPORTED_CURRENCIES = ["USD", "ZAR"]

# Static FX rate for now (safe & deterministic)
USD_TO_ZAR = 18.50

def convert(amount, from_currency, to_currency):
    if from_currency == to_currency:
        return amount

    if from_currency == "USD" and to_currency == "ZAR":
        return amount * USD_TO_ZAR

    if from_currency == "ZAR" and to_currency == "USD":
        return amount / USD_TO_ZAR

    raise ValueError(f"Unsupported conversion {from_currency} → {to_currency}")
