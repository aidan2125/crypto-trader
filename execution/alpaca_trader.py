"""
execution/alpaca_trader.py

Alpaca broker executor for stocks.
Mirrors the interface of enhanced_paper_trader.py so main_enhanced.py
can call execute_stock_trade() the same way it calls execute_paper_trade().

Starts in PAPER mode by default (safe).
Switch to live by changing ALPACA_MODE in your .env to "live"
and updating the base URL — your bot code doesn't change at all.

─────────────────────────────────────────────────────────────────────────────
.env keys to add (same pattern as your existing exchange keys):

    ALPACA_API_KEY=your_api_key_here        # ← paste from alpaca.markets dashboard
    ALPACA_SECRET_KEY=your_secret_key_here  # ← paste from alpaca.markets dashboard
    ALPACA_MODE=paper                       # ← keep as "paper" until you're confident

─────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Alpaca SDK ────────────────────────────────────────────────────────────────
# Install: pip install alpaca-py
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    from alpaca.data.historical import StockHistoricalDataClient
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logging.warning("[alpaca_trader] alpaca-py not installed. Run: pip install alpaca-py")

# ── Config from .env ──────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# PUT YOUR ALPACA KEYS IN .env — see header above
# These lines read them automatically; you do NOT paste keys here.
# ─────────────────────────────────────────────────────────────────────────────
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")      # ← key goes in .env
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")   # ← secret goes in .env
ALPACA_MODE       = os.getenv("ALPACA_MODE", "paper")     # "paper" or "live"

IS_PAPER = ALPACA_MODE.lower() != "live"

# ── Local trade log (mirrors your existing JSON pattern) ──────────────────────
STOCK_TRADES_FILE    = "data/stock_trades.json"
STOCK_POSITIONS_FILE = "data/stock_positions.json"
STOCK_BALANCE_FILE   = "data/stock_balance.json"

INITIAL_PAPER_BALANCE = 100_000.0   # Alpaca paper account default


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — same load_json / save_json pattern as enhanced_paper_trader.py.
# save_json is now atomic (os.replace), matching the fix already landed in
# enhanced_paper_trader.py — same crash-mid-write corruption risk applied
# here to stock_positions.json / stock_balance.json.
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: str, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: str, data) -> None:
    """
    Atomic write — same pattern as enhanced_paper_trader.py's save_json():
    temp file in the same directory, fsync, then os.replace(). A crash or
    kill mid-write can never leave stock_positions.json / stock_balance.json
    half-written.
    """
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=dir_name,
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Alpaca client — initialised once, reused
# ─────────────────────────────────────────────────────────────────────────────

def _get_client() -> "TradingClient | None":
    if not ALPACA_AVAILABLE:
        return None
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        logging.error(
            "[alpaca_trader] ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env"
        )
        return None
    try:
        return TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=IS_PAPER,           # True → paper endpoint, False → live endpoint
        )
    except Exception as e:
        logging.error(f"[alpaca_trader] Failed to create TradingClient: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Core executor — called from main_enhanced.py run_for_stock()
# Mirrors execute_paper_trade() signature as closely as possible
# ─────────────────────────────────────────────────────────────────────────────

def execute_stock_trade(
    ticker: str,
    signal: int,
    price: float,
    currency: str = "USD",
    atr: float | None = None,
    risk_config: dict | None = None,
    override_risk: bool = False,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """
    Execute a stock trade via Alpaca (paper or live).

    Args:
        ticker:      Stock ticker e.g. "TQQQ"
        signal:      1 = BUY, -1 = SELL/close, 0 = HOLD (no action)
        price:       Current price (used for position sizing)
        currency:    Always "USD" for stocks
        atr:         ATR value, used for position sizing and as the fallback
                     SL/TP source when the strategy doesn't supply its own.
        risk_config: Dict from load_config() — uses max_loss_per_trade_pct etc.
        override_risk: If True, force-close regardless of signal (used by SL/TP checker)
        stop_loss / take_profit: optional, absolute price levels from the
            strategy's own signal row — same contract as execute_paper_trade()
            in enhanced_paper_trader.py. When provided, these are used
            directly instead of being recomputed here from atr_sl_mult/
            atr_tp_mult, so a stock entry is opened at the same levels the
            strategy's R:R/quality check actually validated. Falls back to
            the atr-based calc below only if the strategy didn't supply them
            (mirrors the crypto reconciliation fix — see enhanced_paper_trader.py).

    Returns:
        Result dict — same shape execute_paper_trade() returns.
    """
    if signal == 0 and not override_risk:
        return None

    client = _get_client()
    positions = _load_json(STOCK_POSITIONS_FILE, {})
    balance_data = _load_json(STOCK_BALANCE_FILE, {"balance": INITIAL_PAPER_BALANCE})
    balance = balance_data.get("balance", INITIAL_PAPER_BALANCE)

    rc = risk_config or {}
    risk_pct       = rc.get("risk_per_trade", rc.get("max_loss_per_trade_pct", 0.02))
    atr_sl_mult    = rc.get("atr_multiplier_sl", 2.0)
    atr_tp_mult    = rc.get("atr_multiplier_tp", 3.0)
    max_positions  = rc.get("max_positions", 5)

    # ── BUY ──────────────────────────────────────────────────────────────────
    if signal == 1:
        if ticker in positions:
            msg = f"[SKIP] Already holding {ticker}"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        if len(positions) >= max_positions:
            msg = f"[SKIP] Max positions ({max_positions}) reached"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        # --- Determine stop-loss for position sizing ---
        # Prefer the strategy's own stop_loss (already validated by the
        # strategy's R:R/quality checks). Fall back to an ATR-derived
        # estimate only if the strategy didn't supply one. Same precedence
        # as execute_paper_trade() in enhanced_paper_trader.py.
        if stop_loss is not None:
            approx_sl_distance = abs(price - stop_loss)
        elif atr and atr > 0:
            approx_sl_distance = atr * atr_sl_mult
        else:
            approx_sl_distance = None

        # Position sizing — risk-based when we have a stop distance, else flat %
        if approx_sl_distance and approx_sl_distance > 0:
            risk_dollars = balance * risk_pct
            shares       = max(1, int(risk_dollars / approx_sl_distance))
        else:
            # Fallback: flat 2% of balance
            shares = max(1, int((balance * risk_pct) / price))

        cost = shares * price
        if cost > balance:
            shares = max(1, int(balance * 0.95 / price))   # Use 95% of balance max
            cost   = shares * price

        # --- Final SL/TP to store on the position ---
        # Strategy-provided levels are used as-is (fixed absolute prices,
        # matching execute_paper_trade()'s contract). Fallback path keeps
        # the old atr_sl_mult/atr_tp_mult behavior.
        if stop_loss is not None and take_profit is not None:
            sl, tp = stop_loss, take_profit
        elif atr:
            sl = price - atr * atr_sl_mult
            tp = price + atr * atr_tp_mult
        else:
            sl = price * 0.97
            tp = price * 1.06

        # Place order via Alpaca
        order_result, was_simulated = _place_order(
            client=client,
            ticker=ticker,
            side=OrderSide.BUY if ALPACA_AVAILABLE else "buy",
            qty=shares,
            ticker_label=ticker,
        )

        if order_result:
            # Record position locally (same pattern as your POSITIONS_FILE)
            positions[ticker] = {
                "entry_price":  price,
                "shares":       shares,
                "cost":         cost,
                "stop_loss":    round(sl, 4),
                "take_profit":  round(tp, 4),
                "currency":     currency,
                "entry_time":   datetime.now(timezone.utc).isoformat(),
                "atr_at_entry": atr,
                "order_id":     order_result,
                "simulated":    was_simulated,
            }
            balance -= cost
            balance_data["balance"] = balance
            _save_json(STOCK_POSITIONS_FILE, positions)
            _save_json(STOCK_BALANCE_FILE, balance_data)

            sim_tag = " [SIMULATED FILL — NOT A REAL ORDER]" if was_simulated else ""
            result = (
                f"BUY {shares} × {ticker} @ ${price:.2f} | "
                f"SL: ${sl:.2f} | TP: ${tp:.2f} | "
                f"Cost: ${cost:.2f} | Mode: {'PAPER' if IS_PAPER else 'LIVE'}{sim_tag}"
            )
            logging.info(f"[alpaca_trader] {result}")
            _log_trade(ticker, "BUY", shares, price, sl, tp, cost, simulated=was_simulated)
            return {"success": True, "action": "BUY", "message": result, "quantity": shares,
                    "size_usd": cost, "stop_loss": sl, "take_profit": tp,
                    "pnl": None, "exit_reason": None}
        else:
            msg = f"[ERROR] Order failed for {ticker} BUY"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": sl, "take_profit": tp,
                    "pnl": None, "exit_reason": None}

    # ── SELL / Close ──────────────────────────────────────────────────────────
    elif signal == -1 or override_risk:
        if ticker not in positions:
            msg = f"[SKIP] No position in {ticker} to close"
            return {"success": False, "action": "SELL", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        position = positions[ticker]
        shares       = position.get("shares", 1)
        entry_price  = position.get("entry_price", price)
        cost         = position.get("cost", 0)
        proceeds     = shares * price
        pnl          = proceeds - cost
        pnl_pct      = (pnl / cost * 100) if cost > 0 else 0

        order_result, was_simulated = _place_order(
            client=client,
            ticker=ticker,
            side=OrderSide.SELL if ALPACA_AVAILABLE else "sell",
            qty=shares,
            ticker_label=ticker,
        )

        if order_result:
            del positions[ticker]
            balance += proceeds
            balance_data["balance"] = balance
            _save_json(STOCK_POSITIONS_FILE, positions)
            _save_json(STOCK_BALANCE_FILE, balance_data)

            sim_tag = " [SIMULATED FILL — NOT A REAL ORDER]" if was_simulated else ""
            result = (
                f"SELL {shares} × {ticker} @ ${price:.2f} | "
                f"PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%) | "
                f"Balance: ${balance:.2f} | Mode: {'PAPER' if IS_PAPER else 'LIVE'}{sim_tag}"
            )
            logging.info(f"[alpaca_trader] {result}")
            _log_trade(ticker, "SELL", shares, price, pnl=pnl, simulated=was_simulated)
            return {"success": True, "action": "SELL", "message": result, "quantity": shares,
                    "size_usd": cost, "stop_loss": None, "take_profit": None, "pnl": pnl,
                    "exit_reason": "MANUAL"}
        else:
            msg = f"[ERROR] Order failed for {ticker} SELL"
            return {"success": False, "action": "SELL", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Alpaca order placement
# ─────────────────────────────────────────────────────────────────────────────

def _place_order(client, ticker: str, side, qty: int, ticker_label: str) -> tuple[str | None, bool]:
    """
    Submit a market order to Alpaca.

    Returns (order_id, was_simulated):
        - Real fill:      (order_id_string, False)
        - Simulated fill: (fake_id_string, True)  — alpaca-py missing, or
          no/invalid API keys, so nothing was actually sent to a broker.
        - Failure:        (None, False)

    Previously this silently returned a fake order ID on the same success
    path as a real fill, with no signal anywhere downstream (position record,
    trade log, alert message) that the "trade" never touched a real broker.
    A wrong/missing .env key could look identical to a working live bot in
    every log and Telegram message. Now the simulated case is logged at
    WARNING (not INFO) and the fake/real distinction is threaded through to
    the caller, the stored position, and the trade log — every place a
    person or downstream code could form a mistaken belief about what
    actually executed.
    """
    if not ALPACA_AVAILABLE or client is None:
        fake_id = f"SIM-{ticker_label}-{int(time.time())}"
        reason = "alpaca-py not installed" if not ALPACA_AVAILABLE else "no valid Alpaca client (check .env keys)"
        logging.warning(
            f"[alpaca_trader] SIMULATED ORDER — {reason}. "
            f"No real order was placed. fake_id={fake_id} ({side} {qty} {ticker})"
        )
        print(f"  [SIMULATED — NOT A REAL ORDER] {side} {qty} {ticker} ({reason})")
        return fake_id, True

    try:
        order_data = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,   # DAY order — expires at market close
        )
        order = client.submit_order(order_data=order_data)
        logging.info(f"[alpaca_trader] Order submitted: {order.id} | {side} {qty} {ticker}")
        return str(order.id), False
    except Exception as e:
        logging.error(f"[alpaca_trader] Order failed ({ticker} {side}): {e}")
        return None, False


# ─────────────────────────────────────────────────────────────────────────────
# Trade log — mirrors summarize_paper_trades() pattern
# ─────────────────────────────────────────────────────────────────────────────

def _log_trade(
    ticker: str,
    action: str,
    shares: int,
    price: float,
    stop_loss: float = 0,
    take_profit: float = 0,
    cost: float = 0,
    pnl: float = 0,
    simulated: bool = False,
) -> None:
    trades = _load_json(STOCK_TRADES_FILE, [])
    trades.append({
        "ticker":      ticker,
        "action":      action,
        "shares":      shares,
        "price":       price,
        "stop_loss":   stop_loss,
        "take_profit": take_profit,
        "cost":        cost,
        "pnl":         pnl,
        "mode":        "paper" if IS_PAPER else "live",
        "simulated":   simulated,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    })
    _save_json(STOCK_TRADES_FILE, trades)


def summarize_stock_trades() -> None:
    """Print a P&L summary — mirrors summarize_paper_trades()."""
    trades = _load_json(STOCK_TRADES_FILE, [])
    sells  = [t for t in trades if t["action"] == "SELL"]

    balance_data = _load_json(STOCK_BALANCE_FILE, {"balance": INITIAL_PAPER_BALANCE})
    balance      = balance_data.get("balance", INITIAL_PAPER_BALANCE)
    positions    = _load_json(STOCK_POSITIONS_FILE, {})

    any_simulated = any(p.get("simulated") for p in positions.values()) or \
                    any(t.get("simulated") for t in trades)

    print("\n" + "─" * 60)
    print(" STOCK PORTFOLIO SUMMARY ".center(60))
    print("─" * 60)
    print(f"  Mode:          {'PAPER' if IS_PAPER else '⚠ LIVE'}")
    if any_simulated:
        print("  ⚠ Some trades below are SIMULATED — no real Alpaca order was placed")
        print("    (check ALPACA_API_KEY / ALPACA_SECRET_KEY in .env and that alpaca-py is installed)")
    print(f"  Cash balance:  ${balance:,.2f}")
    print(f"  Open positions:{len(positions)}")

    if positions:
        print("\n  Open Positions:")
        for ticker, pos in positions.items():
            entry = pos.get("entry_price", 0)
            shares = pos.get("shares", 0)
            sl   = pos.get("stop_loss", 0)
            tp   = pos.get("take_profit", 0)
            sim_tag = "  [SIMULATED]" if pos.get("simulated") else ""
            print(f"    {ticker}: {shares} shares @ ${entry:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f}{sim_tag}")

    if sells:
        total_pnl = sum(t.get("pnl", 0) for t in sells)
        wins  = sum(1 for t in sells if t.get("pnl", 0) > 0)
        losses = len(sells) - wins
        win_rate = (wins / len(sells) * 100) if sells else 0
        print(f"\n  Closed trades: {len(sells)}")
        print(f"  Win rate:      {win_rate:.1f}%  ({wins}W / {losses}L)")
        print(f"  Total P&L:     ${total_pnl:+,.2f}")
    else:
        print("\n  No closed trades yet.")

    print("─" * 60 + "\n")


def check_stock_positions_for_exits(fetch_fn) -> None:
    """
    Check open stock positions against current prices for SL/TP hits.
    Pass in fetch_stock_ohlcv as fetch_fn.
    Mirrors check_all_positions_for_exits() in main_enhanced.py.
    """
    positions = _load_json(STOCK_POSITIONS_FILE, {})
    if not positions:
        return

    from risk.dynamic_risk import load_enhanced_risk_config as load_config
    rc = load_config() or {}

    for ticker, position in list(positions.items()):
        try:
            df = fetch_fn(symbol=ticker, timeframe="5m", limit=1)
            if df is None or df.is_empty():
                continue

            current_price = float(df["close"][0])
            sl = position.get("stop_loss")
            tp = position.get("take_profit")
            currency = position.get("currency", "USD")

            if sl and current_price <= sl:
                logging.info(f"[alpaca_trader] {ticker}: Stop Loss hit @ ${current_price:.2f}")
                print(f"\n[AUTO EXIT] {ticker} Stop Loss hit @ ${current_price:.2f}")
                execute_stock_trade(ticker, -1, current_price, currency, override_risk=True)

            elif tp and current_price >= tp:
                logging.info(f"[alpaca_trader] {ticker}: Take Profit hit @ ${current_price:.2f}")
                print(f"\n[AUTO EXIT] {ticker} Take Profit hit @ ${current_price:.2f}")
                execute_stock_trade(ticker, -1, current_price, currency, override_risk=True)

        except Exception as e:
            logging.error(f"[alpaca_trader] Position check failed for {ticker}: {e}")