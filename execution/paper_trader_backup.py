import json
import os
from datetime import datetime
from utils.currency import SUPPORTED_CURRENCIES
import json
from execution.paper_trader import load_json, BALANCE_FILE, POSITIONS_FILE

# File paths
BALANCE_FILE = "data/paper_balance.json"
POSITIONS_FILE = "data/positions.json"
TRADES_LOG = "logs/paper_trades.log"
SUMMARY_FILE = "data/paper_summary.json"

# Default balances if files do not exist
DEFAULT_BALANCES = {
    "USD": {"cash": 1000},
    "ZAR": {"cash": 18500}
}

# Ensure directories exist
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ------------------- Utility functions -------------------

def load_json(file_path, default=None):
    """Load JSON file with error handling."""
    if not os.path.exists(file_path):
        return default if default is not None else {}
    with open(file_path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default if default is not None else {}

def save_json(file_path, data):
    """Save data to JSON file with proper formatting."""
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

def log_trade(message):
    """Log trade activity with timestamp."""
    timestamp = datetime.utcnow().isoformat()
    with open(TRADES_LOG, "a") as f:
        f.write(f"{timestamp} | {message}\n")

# ------------------- Paper trade functions -------------------

def update_summary(coin, pnl):
    """
    Updates paper trading summary for the coin and total PnL.
    
    Args:
        coin: Trading pair symbol (e.g., 'BTC/USDT')
        pnl: Profit/loss from the trade
        
    Returns:
        Updated summary dictionary
    """
    summary = load_json(SUMMARY_FILE, default={})

    # Get or initialize coin summary
    coin_summary = summary.get(coin, {})
    coin_summary.setdefault("trades", 0)
    coin_summary.setdefault("total_pnl", 0.0)

    coin_summary["trades"] += 1
    coin_summary["total_pnl"] += pnl
    summary[coin] = coin_summary

    # Calculate total PnL across all coins
    total = 0.0
    for v in summary.values():
        if isinstance(v, dict) and "total_pnl" in v:
            total += v["total_pnl"]
    summary["total_pnl"] = total

    save_json(SUMMARY_FILE, summary)
    return summary

def execute_paper_trade(coin, signal, price, currency="USD", trade_size=100):
    """
    Executes a paper trade based on signal.
    
    Args:
        coin: Trading pair symbol (e.g., 'BTC/USDT')
        signal: 1 = BUY, -1 = SELL, 0 = HOLD
        price: Current price of the asset
        currency: Currency to use (default: USD)
        trade_size: Amount to trade in currency units (default: 100)
        
    Returns:
        String describing the trade result (never returns None)
    """
    balances = load_json(BALANCE_FILE, default=DEFAULT_BALANCES.copy())
    positions = load_json(POSITIONS_FILE, default={})

    # Ensure currency account exists
    if currency not in balances:
        balances[currency] = {"cash": 0}

    account = balances[currency]
    position = positions.get(coin)
    timestamp = datetime.utcnow().isoformat()

    # --- BUY LOGIC ---
    if signal == 1:
        # Check if already in position
        if position is not None:
            return f"{coin} ALREADY IN POSITION (entry: {position['entry_price']:.2f})"
        
        # Check if sufficient balance
        if account["cash"] < trade_size:
            return f"{coin} NOT ENOUGH {currency} BALANCE (have: {account['cash']:.2f}, need: {trade_size})"

        # Execute buy
        account["cash"] -= trade_size
        positions[coin] = {
            "entry_price": price,
            "entry_time": timestamp,
            "currency": currency,
            "trade_size": trade_size
        }

        save_json(POSITIONS_FILE, positions)
        save_json(BALANCE_FILE, balances)
        log_trade(f"BUY | {coin} | {price} | {trade_size} {currency}")
        return f"{coin} PAPER BUY @ {price:.2f} ({currency})"

    # --- SELL LOGIC ---
    if signal == -1:
        # Check if position exists
        if position is None:
            return f"{coin} NO POSITION TO SELL"
        
        # Get position details
        entry_price = position["entry_price"]
        trade_size = position["trade_size"]
        position_currency = position["currency"]

        # Calculate PnL
        num_coins = trade_size / entry_price
        pnl = (price - entry_price) * num_coins
        
        # Update balance
        balances[position_currency]["cash"] += trade_size + pnl

        # Update summary and logs
        update_summary(coin, pnl)
        log_trade(f"SELL | {coin} | {price} | PnL: {pnl:.2f} {position_currency}")

        # Close position
        del positions[coin]
        save_json(POSITIONS_FILE, positions)
        save_json(BALANCE_FILE, balances)

        return f"{coin} PAPER SELL @ {price:.2f} | PnL: {pnl:.2f} {position_currency}"

    # --- HOLD LOGIC (signal == 0) ---
    if position is not None:
        entry = position['entry_price']
        unrealized_pnl = (price - entry) * (position['trade_size'] / entry)
        return f"{coin} HOLDING POSITION (entry: {entry:.2f}, unrealized PnL: {unrealized_pnl:.2f})"
    return f"{coin} HOLD - NO POSITION"

def summarize_paper_trades():
    """
    Prints a human-readable summary of balances, positions, and trade history.
    """
    positions = load_json(POSITIONS_FILE, default={})
    balances = load_json(BALANCE_FILE, default=DEFAULT_BALANCES.copy())
    summary = load_json(SUMMARY_FILE, default={})

    print("\n" + "="*50)
    print("PAPER TRADING SUMMARY".center(50))
    print("="*50)
    
    # Cash Balances
    print("\nCash Balances:")
    for currency in SUPPORTED_CURRENCIES:
        cash = balances.get(currency, {}).get("cash", 0)
        print(f"   {currency}: ${cash:,.2f}" if currency == "USD" else f"   {currency}: R{cash:,.2f}")

    # Open Positions
    if positions:
        print("\nOpen Positions:")
        for coin, pos in positions.items():
            entry_price = pos["entry_price"]
            trade_size = pos["trade_size"]
            currency = pos["currency"]
            entry_time = pos.get("entry_time", "Unknown")
            print(f"   {coin}")
            print(f"      Entry: {entry_price:.2f} | Size: {trade_size} {currency}")
            print(f"      Time: {entry_time}")
    else:
        print("\nOpen Positions: None")

    # Trade Summary
    if summary:
        print("\nTrade Summary:")
        for coin, data in summary.items():
            if coin == "total_pnl":
                continue
            if isinstance(data, dict) and "trades" in data and "total_pnl" in data:
                trades = data["trades"]
                total_pnl = data["total_pnl"]
                pnl_sign = "+" if total_pnl >= 0 else ""
                print(f"   {coin}: {trades} trade(s), PnL: {pnl_sign}${total_pnl:.2f}")
        
        total_pnl = summary.get('total_pnl', 0.0)
        total_sign = "+" if total_pnl >= 0 else ""
        print(f"\n   TOTAL PnL: {total_sign}${total_pnl:.2f}")
    else:
        print("\nTrade Summary: No trades yet")
    
    print("="*50 + "\n")

def reset_paper_trading():
    """
    Resets all paper trading data to default state.
    Use this to start fresh.
    """
    # Reset balances
    save_json(BALANCE_FILE, DEFAULT_BALANCES.copy())
    
    # Clear positions
    save_json(POSITIONS_FILE, {})
    
    # Clear summary
    save_json(SUMMARY_FILE, {})
    
    # Clear log file
    if os.path.exists(TRADES_LOG):
        with open(TRADES_LOG, "w") as f:
            f.write(f"{datetime.utcnow().isoformat()} | Paper trading reset\n")
    
    print("Paper trading account reset to default state!")
    print(f"   USD: ${DEFAULT_BALANCES['USD']['cash']}")
    print(f"   ZAR: R{DEFAULT_BALANCES['ZAR']['cash']}")