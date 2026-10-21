# execution/enhanced_paper_trader.py

import json
import os
import tempfile
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
    from risk.daily_pnl import get_daily_realized_pnl
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
    "USD": {"cash": 54.05},
    "ZAR": {"cash": 0.0}
}

# ZAR to USD rate
ZAR_TO_USD_RATE = 1 / 18.5

# Ensure dirs
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)


def _to_usd(amount, currency):
    """Convert a native-currency amount to its USD equivalent."""
    if currency == "ZAR":
        return amount * ZAR_TO_USD_RATE
    return amount  # USD (or an unrecognized currency, treated as already-USD)


def _calculate_total_equity_usd(balances, positions):
    """
    Total account equity, normalized to USD, used for the daily-loss
    circuit breaker checks.

    Previously this was `account["cash"] + sum(p["trade_size"] for p in
    positions)`: only the CURRENT TRADE's currency cash bucket (ignoring
    every other currency's cash entirely), plus a raw sum of trade_size
    across positions with no regard for which currency each position was
    opened in. Since positions can be ZAR (XRP/ADA/DOT per coin_currency.py)
    or USD (BTC/ETH/LTC), that raw sum was mixing ~18.5x-different units
    together as if they were equal — e.g. a R500 ZAR position and a $500
    USD position added up to "1000" of nothing meaningful. That broken
    figure then fed directly into the max_daily_loss_pct_account /
    max_daily_loss_pct_coin circuit breaker, so it could trip far too
    early or far too late depending on which currency happened to be
    involved.

    This version converts every cash balance (across all currencies in
    `balances`) and every open position's trade_size (using that
    position's own stored "currency" field, set at entry) to USD before
    summing, giving one consistent basis.
    """
    cash_usd = sum(_to_usd(bal.get("cash", 0.0), curr) for curr, bal in balances.items())
    exposure_usd = sum(
        _to_usd(p.get("trade_size", 0.0), p.get("currency", "USD"))
        for p in positions.values()
    )
    return cash_usd + exposure_usd


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
    """
    Atomic write: build the new content in a temp file in the same
    directory as file_path, fsync it, then os.replace() it over the
    real path. os.replace is atomic on POSIX and Windows, so a crash
    or kill mid-write can never leave the file half-written — it's
    either the old complete version or the new complete version, never
    a corrupted mix of both. This is shared by POSITIONS_FILE,
    BALANCE_FILE, and SUMMARY_FILE, so all three get the fix.

    Same directory matters: atomic rename only holds within one
    filesystem, which is why the temp file is created next to the
    target rather than in a system temp dir.
    """
    dir_name = os.path.dirname(file_path) or "."
    os.makedirs(dir_name, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=dir_name,
        prefix=os.path.basename(file_path) + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())  # make sure bytes hit disk before the rename
        os.replace(tmp_path, file_path)
    except BaseException:
        # Clean up the temp file on any failure so it doesn't linger.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


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
def execute_paper_trade(
    coin, signal, price, currency="USD", trade_size=None, override_risk=False,
    atr=None, stop_loss=None, take_profit=None,
):
    """
    stop_loss / take_profit: optional, absolute price levels from the
    strategy's own signal row (enhanced_strategy()'s "stop_loss"/
    "take_profit" columns). When provided, these are used directly —
    they're the exact levels the strategy's R:R check and quality score
    were evaluated against when the signal fired, and they are NOT
    adjusted for entry slippage. Shifting them by the slippage delta
    would silently change the trade's real reward:risk versus what the
    strategy validated.

    If not provided (e.g. no strategy SL/TP available, or an asset type
    that hasn't been wired up to pass them yet), falls back to the old
    behavior: SL/TP computed here from `atr` via calculate_dynamic_sl_tp(),
    using this module's own ATR multipliers (config['atr_multiplier_sl']/
    ['atr_multiplier_tp']) rather than the strategy's. Previously this
    fallback path was the ONLY path — the strategy's own stop_loss/
    take_profit columns were computed and quality-checked but never
    actually used to open the position, so paper trades were opened at a
    different (tighter, 2x/3x ATR default) stop distance than the one the
    signal was validated against (3x/4.5x ATR in strict mode). Passing the
    strategy's own levels through closes that mismatch.
    """
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
            msg = f"{coin} ALREADY IN POSITION @ ${position.get('entry_price', 0.0):.2f}"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        equity = _calculate_total_equity_usd(balances, positions)
        daily_pnl_account = get_daily_realized_pnl()
        daily_pnl_coin = get_daily_realized_pnl(symbol=coin)
        max_account_loss = equity * config.get("max_daily_loss_pct_account", 0.03)
        max_coin_loss = equity * config.get("max_daily_loss_pct_coin", 0.02)

        if daily_pnl_account < 0 and abs(daily_pnl_account) >= max_account_loss:
            msg = f"ACCOUNT DAILY LOSS LIMIT HIT: {daily_pnl_account:+.2f} (limit: -{max_account_loss:.2f}) - all new entries blocked"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        if daily_pnl_coin < 0 and abs(daily_pnl_coin) >= max_coin_loss:
            msg = f"{coin} DAILY LOSS LIMIT HIT: {daily_pnl_coin:+.2f} (limit: -{max_coin_loss:.2f}) - entries for {coin} blocked"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        if not override_risk:
            can_open, current, max_pos = check_max_positions(len(positions), config)
            if not can_open:
                msg = f"MAX POSITIONS: {current}/{max_pos}"
                return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                        "size_usd": None, "stop_loss": None, "take_profit": None,
                        "pnl": None, "exit_reason": None}

        # --- Determine stop-loss for position sizing ---
        # Prefer the strategy's own stop_loss (absolute price level, already
        # validated by the strategy's R:R/quality checks). Fall back to an
        # ATR-derived estimate only if the strategy didn't supply one.
        if stop_loss is not None:
            approx_sl = stop_loss
        elif atr is not None and atr > 0:
            approx_sl, _ = calculate_dynamic_sl_tp(price, atr, "BUY", config)
        else:
            return {"success": False, "action": "BUY", "message": "ERROR: stop_loss or ATR required",
                    "quantity": 0, "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        calc_size = calc_position_size(account["cash"], price, approx_sl, config.get("max_loss_per_trade_pct", 0.02))

        calc_size = trade_size or calc_size
        if calc_size <= 0:
            return {"success": False, "action": "BUY", "message": "SIZE TOO SMALL",
                    "quantity": 0, "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        fees_info = calculate_fees_and_slippage(calc_size, config)
        total_cost = calc_size + fees_info["total_cost"]
        if account["cash"] < total_cost:
            msg = f"INSUFFICIENT FUNDS: need ${total_cost:.2f}"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        effective_price = price * (1 + config.get("slippage_pct", 0.0005))

        # --- Final SL/TP to store on the position ---
        # Strategy-provided levels are used as-is (fixed absolute prices,
        # not shifted by slippage — see docstring). Fallback path keeps the
        # old behavior of deriving SL/TP from the slippage-adjusted entry.
        if stop_loss is not None and take_profit is not None:
            sl, tp = stop_loss, take_profit
        else:
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

        msg = f"BUY {coin} @ ${effective_price:.2f}\nSize: ${calc_size:.2f}\nSL: ${sl:.2f} | TP: ${tp:.2f}"
        return {"success": True, "action": "BUY", "message": msg,
                "quantity": calc_size / effective_price, "size_usd": calc_size,
                "stop_loss": sl, "take_profit": tp, "pnl": None, "exit_reason": None}

    # --- SELL ---
    if signal == -1:
        if not position:
            return {"success": False, "action": "SELL", "message": f"{coin} NO POSITION",
                    "quantity": 0, "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

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

        msg = f"SELL {coin} @ ${effective_price:.2f}\nPnL: {net_pnl:+.2f} {pos_curr}\nExit: {exit_type}"
        return {"success": True, "action": "SELL", "message": msg, "quantity": num_coins,
                "size_usd": size, "stop_loss": sl, "take_profit": tp, "pnl": net_pnl,
                "exit_reason": exit_type}

    # --- HOLD ---
    if position:
        unreal = (price - position["entry_price"]) * (position["trade_size"] / position["entry_price"])
        pct = unreal / position["trade_size"] * 100
        msg = f"HOLD {coin}\nUnreal: {unreal:+.2f} ({pct:+.1f}%)"
        return {"success": True, "action": "HOLD", "message": msg, "quantity": 0,
                "size_usd": None, "stop_loss": position.get("stop_loss"),
                "take_profit": position.get("take_profit"), "pnl": unreal, "exit_reason": None}

    return {"success": False, "action": None, "message": f"{coin} NO POSITION", "quantity": 0,
            "size_usd": None, "stop_loss": None, "take_profit": None, "pnl": None,
            "exit_reason": None}


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