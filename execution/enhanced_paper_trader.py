# execution/enhanced_paper_trader.py

import json
import os
import csv
from datetime import datetime
from utils.currencies import SUPPORTED_CURRENCIES

# === Dynamic Risk Management Only ===
try:
    from risk.dynamic_risk import (
        load_enhanced_risk_config as load_config,
        save_enhanced_risk_config as save_config,
        calculate_dynamic_sl_tp,
        calculate_position_size_with_risk as calc_position_size,
        calculate_fees_and_slippage,
        check_max_positions,
        ENHANCED_RISK_CONFIG
    )
except ImportError as e:
    print(f"Risk module import error: {e}")
    raise

# File paths
BALANCE_FILE = "data/paper_balance.json"
POSITIONS_FILE = "data/positions.json"
TRADES_LOG = "logs/paper_trades.log"
SUMMARY_FILE = "data/paper_summary.json"
CSV_FILE = "logs/paper_trades.csv"

# Default balances
DEFAULT_BALANCES = {
    "USD": {"cash": 1000.0},
    "ZAR": {"cash": 18500.0}  # ~1000 USD
}

# ZAR to USD rate
ZAR_TO_USD_RATE = 1 / 18.5

# Ensure dirs
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)


# ------------------- Utils -------------------
def load_json(file_path, default=None):
    if not os.path.exists(file_path):
        return default if default is not None else {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default if default is not None else {}


def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)


def log_trade(message):
    with open(TRADES_LOG, "a") as f:
        f.write(f"{datetime.utcnow().isoformat()} | {message}\n")


def log_trade_csv(timestamp, action, coin, price, size, pnl, currency):
    header_needed = not os.path.exists(CSV_FILE)
    try:
        with open(CSV_FILE, "a", newline='') as f:
            writer = csv.writer(f)
            if header_needed:
                writer.writerow(["timestamp", "action", "coin", "price", "size", "pnl", "currency"])
            writer.writerow([timestamp, action, coin, f"{price:.2f}", f"{size:.2f}", f"{pnl:.2f}", currency])
    except Exception as e:
        print(f"CSV log failed: {e}")


# ------------------- Summary -------------------
def update_summary(coin, pnl, trade_type="MANUAL"):
    summary = load_json(SUMMARY_FILE, default={})
    s = summary.setdefault(coin, {})
    s.setdefault("trades", 0)
    s.setdefault("total_pnl", 0.0)
    s.setdefault("wins", 0)
    s.setdefault("losses", 0)
    s.setdefault("breakeven", 0)
    s.setdefault("exit_types", {})

    s["trades"] += 1
    s["total_pnl"] += pnl

    if pnl > 0.01:
        s["wins"] += 1
    elif pnl < -0.01:
        s["losses"] += 1
    else:
        s["breakeven"] += 1

    s["exit_types"][trade_type] = s["exit_types"].get(trade_type, 0) + 1
    summary[coin] = s

    # Global stats
    total_pnl = sum(v.get("total_pnl", 0) for v in summary.values() if isinstance(v, dict))
    total_wins = sum(v.get("wins", 0) for v in summary.values() if isinstance(v, dict))
    total_losses = sum(v.get("losses", 0) for v in summary.values() if isinstance(v, dict))
    total_trades = total_wins + total_losses

    summary["total_pnl"] = round(total_pnl, 2)
    summary["total_wins"] = total_wins
    summary["total_losses"] = total_losses
    summary["win_rate"] = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0.0

    save_json(SUMMARY_FILE, summary)
    return summary


# ------------------- Execute Trade -------------------
def execute_paper_trade(coin, signal, price, currency="USD", trade_size=None, override_risk=False, atr=None):
    config = load_config()
    balances = load_json(BALANCE_FILE, DEFAULT_BALANCES.copy())
    positions = load_json(POSITIONS_FILE, {})
    timestamp = datetime.utcnow().isoformat()

    if currency not in balances:
        balances[currency] = {"cash": 0.0}
    account = balances[currency]
    position = positions.get(coin)

    # --- AUTO EXIT ---
    if position and signal != -1:
        sl = position.get("stop_loss")
        tp = position.get("take_profit")
        if sl is not None and price <= sl:
            return execute_paper_trade(coin, -1, price, currency, override_risk=True)
        if tp is not None and price >= tp:
            return execute_paper_trade(coin, -1, price, currency, override_risk=True)

    # --- BUY ---
    if signal == 1:
        if position:
            return f"{coin} ALREADY IN POSITION @ ${position.get('entry_price', 0.0):.2f}"

        if not override_risk:
            can_open, current, max_pos = check_max_positions(len(positions), config)
            if not can_open:
                return f"MAX POSITIONS: {current}/{max_pos}"

        if atr is None or atr <= 0:
            return "ERROR: ATR required (>0)"

        approx_sl, _ = calculate_dynamic_sl_tp(price, atr, "BUY", config)
        calc_size = calc_position_size(account["cash"], price, approx_sl, config)

        calc_size = trade_size or calc_size
        if calc_size <= 0:
            return "SIZE TOO SMALL"

        fees_info = calculate_fees_and_slippage(calc_size, config)
        total_cost = calc_size + fees_info["total_cost"]
        if account["cash"] < total_cost:
            return f"INSUFFICIENT FUNDS: need ${total_cost:.2f}"

        effective_price = price * (1 + config.get("slippage_pct", 0.0005))
        sl, tp = calculate_dynamic_sl_tp(effective_price, atr, "BUY", config)

        account["cash"] -= total_cost
        positions[coin] = {
            "entry_price": effective_price,
            "original_price": price,
            "entry_time": timestamp,
            "currency": currency,
            "trade_size": calc_size,
            "fees_paid": fees_info["total_cost"],
            "peak_price": effective_price,
            "stop_loss": sl,
            "take_profit": tp
        }

        save_json(POSITIONS_FILE, positions)
        save_json(BALANCE_FILE, balances)
        log_trade(f"BUY {coin} @ {effective_price:.2f} | ${calc_size:.2f}")
        log_trade_csv(timestamp, "BUY", coin, effective_price, calc_size, 0.0, currency)

        return f"BUY {coin} @ ${effective_price:.2f}\nSize: ${calc_size:.2f}\nSL: ${sl:.2f} | TP: ${tp:.2f}"

    # --- SELL ---
    if signal == -1:
        if not position:
            return f"{coin} NO POSITION"

        entry = position["entry_price"]
        size = position["trade_size"]
        fees_in = position.get("fees_paid", 0.0)
        pos_curr = position["currency"]

        fees_info = calculate_fees_and_slippage(size, config)
        effective_price = price * (1 - config.get("slippage_pct", 0.0005))
        fees_out = fees_info["total_cost"]

        num_coins = size / entry
        gross_pnl = (effective_price - entry) * num_coins
        net_pnl = gross_pnl - fees_out - fees_in
        proceeds = size + gross_pnl - fees_out

        balances[pos_curr]["cash"] += proceeds

        exit_type = "MANUAL"
        sl = position.get("stop_loss")
        tp = position.get("take_profit")
        if sl is not None and effective_price <= sl:
            exit_type = "STOP_LOSS"
        elif tp is not None and effective_price >= tp:
            exit_type = "TAKE_PROFIT"

        update_summary(coin, net_pnl, exit_type)
        log_trade(f"SELL {coin} @ {effective_price:.2f} | PnL {net_pnl:+.2f}")
        log_trade_csv(timestamp, "SELL", coin, effective_price, size, net_pnl, pos_curr)

        del positions[coin]
        save_json(POSITIONS_FILE, positions)
        save_json(BALANCE_FILE, balances)

        return f"SELL {coin} @ ${effective_price:.2f}\nPnL: {net_pnl:+.2f} {pos_curr}\nExit: {exit_type}"

    # --- HOLD ---
    if position:
        unreal = (price - position["entry_price"]) * (position["trade_size"] / position["entry_price"])
        pct = unreal / position["trade_size"] * 100
        return f"HOLD {coin}\nUnreal: {unreal:+.2f} ({pct:+.1f}%)"

    return f"{coin} NO POSITION"


# ------------------- Summary Display -------------------
def summarize_paper_trades():
    positions = load_json(POSITIONS_FILE, {})
    balances = load_json(BALANCE_FILE, DEFAULT_BALANCES.copy())
    summary = load_json(SUMMARY_FILE, {})
    config = load_config()

    print("\n" + "="*60)
    print("PAPER TRADING SUMMARY".center(60))
    print("="*60)

    usd_cash = 0.0
    for curr in SUPPORTED_CURRENCIES:
        cash = balances.get(curr, {}).get("cash", 0.0)
        if curr == "USD":
            usd_cash += cash
        elif curr == "ZAR":
            usd_cash += cash * ZAR_TO_USD_RATE

    exposure = sum(p.get("trade_size", 0.0) for p in positions.values())
    total = usd_cash + exposure
    exp_pct = exposure / total * 100 if total > 0 else 0

    print("\nCash Balances:")
    for curr in SUPPORTED_CURRENCIES:
        cash = balances.get(curr, {}).get("cash", 0.0)
        sym = "$" if curr == "USD" else "R"
        print(f"  {curr}: {sym}{cash:,.2f}")

    print(f"\nTotal Cash (USD equiv): ${usd_cash:,.2f}")
    print(f"Exposure: ${exposure:,.2f} ({exp_pct:.1f}%)")
    print(f"Open Positions: {len(positions)} / {config.get('max_positions', 5)}")

    if positions:
        print("\nOpen Positions:")
        for coin, pos in positions.items():
            entry = pos.get("entry_price", 0.0)
            size = pos.get("trade_size", 0.0)
            print(f"  {coin} @ ${entry:.2f} | Size: ${size:.2f}")

            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            if sl is not None and tp is not None:
                print(f"    SL: ${sl:.2f} | TP: ${tp:.2f}")
            else:
                print("    SL: N/A | TP: N/A  (legacy position - no dynamic risk)")

    if "total_pnl" in summary:
        total_trades = summary["total_wins"] + summary["total_losses"]
        print(f"\nPerformance:")
        print(f"  Total PnL: {summary['total_pnl']:+.2f} USD")
        if total_trades > 0:
            print(f"  Win Rate: {summary['win_rate']:.1f}% ({summary['total_wins']}/{total_trades} trades)")
        else:
            print("  Win Rate: No closed trades yet")

    print("="*60 + "\n")


# ------------------- Reset -------------------
def reset_paper_trading():
    save_json(BALANCE_FILE, DEFAULT_BALANCES.copy())
    save_json(POSITIONS_FILE, {})
    save_json(SUMMARY_FILE, {})
    save_config(ENHANCED_RISK_CONFIG.copy())

    with open(TRADES_LOG, "w") as f:
        f.write(f"{datetime.utcnow().isoformat()} | PAPER TRADING RESET\n")

    print("Paper trading reset complete!")
    print(f"  USD: ${DEFAULT_BALANCES['USD']['cash']:,.2f}")
    print(f"  ZAR: R{DEFAULT_BALANCES['ZAR']['cash']:,.2f}")