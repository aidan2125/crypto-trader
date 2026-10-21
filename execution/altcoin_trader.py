"""
AltcoinTrader live execution module.

Endpoints, field names, headers, and the request-signing scheme below are
all taken from AltcoinTrader's own OpenAPI spec — nothing here is guessed
anymore. One thing still needs YOUR verification, not mine:

  COIN_TICKER_MAP below is a guess based on common exchange symbols, not
  pulled from AltcoinTrader's actual market list. Confirm each coin your
  strategy trades (especially less-common ones like DOT) is really listed
  there before trading it live — an unlisted ticker should 400/404
  cleanly rather than do anything silently wrong, but check anyway.

Also worth knowing going in: these docs show no bracket/stop-loss/
take-profit order type. Your bot's ATR-based SL/TP currently only closes
positions by having run_for_symbol / check_all_positions_for_exits call
execute_*_trade again with an exit signal — for AltcoinTrader that means
check_altcointrader_positions_for_exits() (still a TODO stub below) needs
to poll price and fire a sell via this same module when SL/TP is hit,
same as the crypto paper-trading path already does. There's no exchange-
side safety net between bot polls.

Mirrors the interface of execution/alpaca_trader.py so it can be dropped
into main.py the same way stocks are:

    from execution.altcointrader_trader import (
        execute_altcointrader_trade,
        summarize_altcointrader_trades,
        check_altcointrader_positions_for_exits,
    )

────────────────────────────────────────────────────────────────────────────
BEFORE THIS TOUCHES REAL MONEY:

1. Make sure the machine's clock is accurate (NTP synced). Signatures
   are timestamp-bound to a ±30 second window server-side — clock drift
   means every request fails with API_KEYS.TIMESTAMP_SKEW, not a silent
   wrong signature.

2. Generate an API key with the "trade" permission only — no withdrawal
   permission. /easybuy explicitly requires "trade" permission per the
   docs. If AltcoinTrader supports IP whitelisting for API keys, turn it
   on and lock it to the box this bot runs from.

3. Confirm COIN_TICKER_MAP entries against AltcoinTrader's real market
   list (see above).

4. Leave DRY_RUN=True and run a full cycle first. Read the printed
   "[DRY RUN]" lines and confirm side/amount/ticker look right before
   ever setting DRY_RUN=False. Once DRY_RUN=False, also try one real
   get_balances() call by hand first — confirms auth works before any
   order-placing code path runs.

5. Only after a clean dry run: set DRY_RUN=False AND set
   ALTCOINTRADER_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK in your .env.
   Both are required — either alone will not place a real order.
   This is deliberate friction, not a bug.
────────────────────────────────────────────────────────────────────────────
"""

import hashlib
import hmac
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config — pull from .env, same pattern as your other modules
# ─────────────────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("ALTCOINTRADER_API_KEY", "")
API_SECRET = os.getenv("ALTCOINTRADER_API_SECRET", "")

BASE_URL = "https://api.altcointrader.co.za"

# Safety rails — deliberately conservative defaults for a first live run.
DRY_RUN = os.getenv("ALTCOINTRADER_DRY_RUN", "true").lower() != "false"
LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THE_RISK"
LIVE_CONFIRMED = os.getenv("ALTCOINTRADER_LIVE_CONFIRM", "") == LIVE_CONFIRM_PHRASE

# Hard ZAR cap per trade, independent of your risk-% position sizing.
# Docs specify a 5 quote-unit minimum spend on market/easybuy orders, so
# keep this comfortably above that. This exists so a sizing bug can't
# turn into a large order while you're still trusting this code with
# small amounts.
MAX_ZAR_PER_TRADE = float(os.getenv("ALTCOINTRADER_MAX_ZAR_PER_TRADE", "250"))

# TODO: verify each of these against AltcoinTrader's own market/ticker
# list before trading it — this mapping is a guess based on common
# symbols, not confirmed against their API.
COIN_TICKER_MAP = {
    "BTC/USDT": "BTC",
    "ETH/USDT": "ETH",
    "XRP/USDT": "XRP",
    "LTC/USDT": "LTC",
    "ADA/USDT": "ADA",
    "DOT/USDT": "DOT",  # TODO: confirm DOT is actually listed — not all
                         # altcoins on Binance are available on AltcoinTrader
}

# Local record of what this module itself bought, keyed by coin, so a
# later sell knows what quantity to pass to /easybuy. This is NOT a
# substitute for checking real balance once a balance endpoint is wired
# up (see module docstring TODO #2) — it's a stopgap so sells don't fail
# outright in the meantime.
_POSITIONS_FILE = Path("data/altcointrader_positions.json")


def _load_positions() -> dict:
    if _POSITIONS_FILE.exists():
        try:
            return json.loads(_POSITIONS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_positions(positions: dict) -> None:
    """
    Atomic write: build the new content in a temp file in the same
    directory, then os.replace() it over the real file. os.replace is
    atomic on POSIX and Windows, so a crash or kill mid-write can never
    leave positions.json half-written or truncated — the file is either
    the old complete version or the new complete version, never neither.
    Same directory matters: atomic rename only holds within one filesystem.
    """
    _POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=_POSITIONS_FILE.parent,
        prefix=_POSITIONS_FILE.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(positions, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # make sure bytes hit disk before the rename
        os.replace(tmp_path, _POSITIONS_FILE)
    except BaseException:
        # Clean up the temp file on any failure so it doesn't linger.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Signing — headers confirmed by the docs; canonical string still TODO
# ─────────────────────────────────────────────────────────────────────────────
def _sign_request(method: str, path: str, body: str = "") -> dict:
    """
    Confirmed signing scheme from AltcoinTrader's OpenAPI spec:

        payload   = f"{timestamp}\\n{METHOD}\\n{path}\\n{body}"
        signature = HMAC-SHA256(secret, payload), lowercase hex

    timestamp is Unix seconds (not milliseconds) and must be within
    ±30 seconds of server time — if your machine's clock drifts, every
    request will 401 with API_KEYS.TIMESTAMP_SKEW. For GET/DELETE, body
    is an empty string. `path` is the request path only, no query string,
    no host (e.g. "/orders", "/orders/order-001", "/balances").
    """
    timestamp = str(int(time.time()))  # seconds, per spec
    payload = f"{timestamp}\n{method.upper()}\n{path}\n{body}"
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-API-KEY": API_KEY,
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": signature,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, body: str = "", params: Optional[dict] = None) -> dict:
    url = f"{BASE_URL}{path}"
    headers = _sign_request(method, path, body)
    resp = requests.request(method, url, headers=headers, data=body or None, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Read-only calls — safe to run and test before any order placement.
# Test get_balances() first once _sign_request is filled in: a working
# GET here confirms your signing scheme before anything that spends
# money runs, and 401 vs a real response is an easy, cheap signal.
# ─────────────────────────────────────────────────────────────────────────────
def get_balances() -> dict:
    """Returns {currency: {"available": float, "reserved": float, "total": float}}."""
    data = _request("GET", "/balances")
    return {
        row["currency"]: {
            "available": float(row.get("available", 0)),
            "reserved": float(row.get("reserved", 0)),
            "total": float(row.get("total", 0)),
        }
        for row in data
    }


def get_available_zar() -> float:
    return get_balances().get("ZAR", {}).get("available", 0.0)


def get_open_orders(market: Optional[str] = None) -> list:
    params = {"market": market} if market else None
    return _request("GET", "/orders/open", params=params)


def get_order(order_id: str) -> dict:
    return _request("GET", f"/orders/{order_id}")


def cancel_order(order_id: str) -> dict:
    return _request("DELETE", f"/orders/{order_id}")


def get_trade_history(market: Optional[str] = None, limit: int = 50) -> list:
    params = {"limit": limit}
    if market:
        params["market"] = market
    return _request("GET", "/trades", params=params)


# ─────────────────────────────────────────────────────────────────────────────
# Order placement — via /easybuy: one synchronous call, returns the fill
# directly, takes a plain ticker rather than a market pair.
# ─────────────────────────────────────────────────────────────────────────────
def _place_easybuy_order(ticker: str, side: str, amount: str) -> dict:
    """
    side: "buy" or "sell"
    amount: for buy, ZAR (quote) to spend as a decimal string; for sell,
            coin (base) quantity to sell as a decimal string. These are
            NOT interchangeable — see docs. Docs specify a 5 quote-unit
            minimum spend.
    """
    client_order_id = str(uuid.uuid4())
    body = json.dumps({
        "side": side,
        "ticker": ticker,
        "amount": amount,
        "client_order_id": client_order_id,
    })

    if DRY_RUN or not LIVE_CONFIRMED:
        reason = "DRY_RUN=True" if DRY_RUN else "ALTCOINTRADER_LIVE_CONFIRM not set"
        logging.info(f"[DRY RUN] Would {side.upper()} {ticker} amount={amount} ({reason})")
        print(f"  [DRY RUN] {side.upper()} {ticker}  amount={amount}  ({reason} — no real order sent)")
        return {"dry_run": True, "ticker": ticker, "side": side, "amount": amount}

    return _request("POST", "/easybuy", body=body)


# ─────────────────────────────────────────────────────────────────────────────
# Public interface — same shape as execute_stock_trade() in alpaca_trader.py
# so main.py's run_for_symbol() can call this unmodified.
# ─────────────────────────────────────────────────────────────────────────────
def execute_altcointrader_trade(
    coin: str,
    signal: int,
    price: float,                        # USDT-feed price, i.e. what the strategy saw
    currency: str = "ZAR",
    atr: Optional[float] = None,
    risk_config: Optional[dict] = None,
    stop_loss: Optional[float] = None,   # USDT-feed terms, same as the strategy's
    take_profit: Optional[float] = None,
    exit_reason: Optional[str] = None,
) -> dict:
    if signal == 0:
        return {"message": "No action (flat signal)", "quantity": 0}

    ticker = COIN_TICKER_MAP.get(coin)
    if ticker is None:
        msg = f"No AltcoinTrader ticker mapping for {coin} — refusing to trade it"
        logging.error(msg)
        return {"message": msg, "quantity": 0}

    positions = _load_positions()

    if signal == 1:
        if coin in positions:
            return {"message": f"{coin}: live position already open — skipping buy", "quantity": 0}

        # Never open a live position without a stop.
        if stop_loss is None and atr:
            stop_loss = price - atr * (risk_config or {}).get("atr_multiplier_sl", 2.0)
        if stop_loss is None or stop_loss >= price:
            msg = f"{coin}: no valid stop-loss available — refusing live entry"
            logging.error(msg)
            return {"message": msg, "quantity": 0}

        zar_amount = MAX_ZAR_PER_TRADE
        pct_size = (risk_config or {}).get("max_loss_per_trade_pct")
        if pct_size:
            try:
                zar_amount = min(MAX_ZAR_PER_TRADE, get_available_zar() * pct_size)
            except Exception as e:
                logging.warning(f"Balance check failed, using MAX_ZAR_PER_TRADE: {e}")

        if zar_amount < 5:
            msg = f"{coin}: order size R{zar_amount:.2f} is below the R5 minimum — skipping"
            logging.warning(msg)
            return {"message": msg, "quantity": 0}

        result = _place_easybuy_order(ticker, "buy", f"{zar_amount:.2f}")
        if result.get("dry_run"):
            return {"message": f"[DRY RUN] BUY {ticker} for R{zar_amount:.2f}", "quantity": 0}

        filled = result.get("result", {})
        filled_qty = float(filled.get("filled_qty", 0) or 0)
        if filled_qty <= 0:
            msg = f"{coin}: BUY sent but no fill parsed — CHECK ACCOUNT BY HAND. raw={result}"
            logging.critical(msg)
            return {"message": msg, "quantity": 0, "exit_reason": "UNTRACKED_FILL", "raw": result}

        positions[coin] = {
            "currency": "ZAR",
            "quantity": filled_qty,
            "cost_zar": float(filled.get("filled_quote_qty") or 0) or zar_amount,
            "entry_price_zar": float(filled.get("avg_price") or 0) or None,
            "entry_price_usdt": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_positions(positions)
        return {"message": f"BUY {ticker} for R{zar_amount:.2f}", "quantity": filled_qty,
                "size_zar": zar_amount, "stop_loss": stop_loss, "take_profit": take_profit,
                "pnl": None, "exit_reason": None, "raw": result}

    # signal == -1: exit
    pos = positions.get(coin)
    if not pos or pos.get("quantity", 0) <= 0:
        msg = f"{coin}: sell requested but no tracked live position — skipping"
        logging.warning(msg)
        return {"message": msg, "quantity": 0}

    qty = pos["quantity"]
    try:  # sell what we actually hold if fees ate into the tracked amount
        qty = min(qty, get_balances().get(ticker, {}).get("available", qty))
    except Exception as e:
        logging.warning(f"{coin}: balance check failed before sell, using tracked qty: {e}")
    if qty <= 0:
        return {"message": f"{coin}: no available {ticker} balance to sell — CHECK ACCOUNT", "quantity": 0}

    result = _place_easybuy_order(ticker, "sell", f"{qty:.8f}")
    if result.get("dry_run"):
        return {"message": f"[DRY RUN] SELL {ticker} qty={qty:.8f}", "quantity": 0}

    filled = result.get("result", {})
    if float(filled.get("filled_qty", 0) or 0) <= 0:
        msg = f"{coin}: SELL sent but no fill parsed — position KEPT, CHECK ACCOUNT. raw={result}"
        logging.critical(msg)
        return {"message": msg, "quantity": 0, "raw": result}

    net = float(filled.get("net_amount", 0) or 0)
    cost = pos.get("cost_zar")
    pnl = (net - cost * qty / pos["quantity"]) if (net and cost) else None
    positions.pop(coin, None)
    _save_positions(positions)
    return {"message": f"SELL {ticker} qty={qty:.8f}", "quantity": qty,
            "size_zar": net or None, "pnl": pnl, "exit_reason": exit_reason, "raw": result}


def summarize_altcointrader_trades() -> None:
    print("  [AltcoinTrader] Trade summary not yet implemented — TODO")


def check_altcointrader_positions_for_exits(fetch_fn) -> list:
    """Compares each live position to its SL/TP using the same USDT feed the
    strategy uses, and fires a sell on a hit. Returns events for the caller
    to alert/log. Exceptions are collected, not swallowed, so one coin's
    failure can't block another coin's stop, and the caller can still
    escalate fatal errors."""
    events = []
    for coin, pos in list(_load_positions().items()):
        try:
            df = fetch_fn(symbol=coin, limit=1)
            if df is None or df.is_empty():
                events.append({"coin": coin, "kind": "NO_PRICE"})
                continue
            price = float(df["close"][0])
            sl, tp = pos.get("stop_loss"), pos.get("take_profit")
            reason = "SL" if (sl and price <= sl) else "TP" if (tp and price >= tp) else None
            if reason:
                result = execute_altcointrader_trade(coin, -1, price, "ZAR", exit_reason=reason)
                events.append({"coin": coin, "kind": reason, "price": price, "result": result})
        except Exception as e:
            events.append({"coin": coin, "kind": "ERROR", "exc": e})
    return events
