import json
import os
from datetime import datetime
from utils.currency import convert

BALANCE_FILE = "data/paper_balance.json"
POSITIONS_FILE = "data/positions.json"
TRADES_LOG = "logs/paper_trades.log"

def load_balance():
    if not os.path.exists(BALANCE_FILE):
        # Initialize with default balances
        balances = {
            "USD": {"cash": 1000},
            "ZAR": {"cash": 18500}
        }
        save_balance(balances)
        return balances

    with open(BALANCE_FILE, "r") as f:
        return json.load(f)


def save_balance(balances):
    with open(BALANCE_FILE, "w") as f:
        json.dump(balances, f, indent=4)


def load_positions():
    if not os.path.exists(POSITIONS_FILE):
        return {}
    with open(POSITIONS_FILE, "r") as f:
        return json.load(f)


def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=4)


def log_trade(message):
    timestamp = datetime.utcnow().isoformat()
    with open(TRADES_LOG, "a") as f:
        f.write(f"{timestamp} | {message}\n")


def execute_paper_trade(coin, signal, price, currency="USD", trade_size=100):
    """
    Executes a paper trade.
    
    signal: 1 = BUY, -1 = SELL, 0 = HOLD
    """
    balances = load_balance()
    positions = load_positions()

    # Ensure currency exists in balances
    if currency not in balances:
        balances[currency] = {"cash": 0}

    account = balances[currency]
    position = positions.get(coin)
    timestamp = datetime.utcnow().isoformat()

    # BUY
    if signal == 1 and position is None:
        if account["cash"] < trade_size:
            return f"{coin} NOT ENOUGH {currency} BALANCE"

        account["cash"] -= trade_size
        positions[coin] = {
            "entry_price": price,
            "entry_time": timestamp,
            "currency": currency,
            "trade_size": trade_size
        }

        save_positions(positions)
        save_balance(balances)
        log_trade(f"BUY | {coin} | {price} | {trade_size} {currency}")
        return f"{coin} PAPER BUY @ {price} ({currency})"

    # SELL
    if signal == -1 and position is not None:
        entry_price = position["entry_price"]
        trade_size = position["trade_size"]
        currency = position["currency"]

        pnl = (price - entry_price) * (trade_size / entry_price)
        balances[currency]["cash"] += trade_size + pnl

        log_trade(f"SELL | {coin} | {price} | PnL: {pnl:.2f} {currency}")

        del positions[coin]

        save_positions(positions)
        save_balance(balances)
        return f"{coin} PAPER SELL @ {price} | PnL: {pnl:.2f} {currency}"

    return None



