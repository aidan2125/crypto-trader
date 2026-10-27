"""
execution/alpaca_crypto.py

Alpaca PAPER crypto executor. Always paper (hard-coded, ignores ALPACA_MODE).
Uses ALPACA_API_KEY / ALPACA_SECRET_KEY from .env.

- Long only: BUY signal opens, SELL signal closes (Alpaca has no crypto shorting)
- Orders: market, notional (USD), time_in_force=GTC
- Sizing: risk ALPACA_CRYPTO_RISK_PCT (1%) of equity to the stop, capped at
  ALPACA_CRYPTO_MAX_POS_PCT (5%) of equity per position
- SL/TP are software-managed (check_alpaca_crypto_exits), stored in
  data/alpaca_crypto_positions.json
"""
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, GetAssetsRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass, AssetStatus
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logging.warning("[alpaca-crypto] alpaca-py not installed. Run: pip install alpaca-py")

from execution.alpaca_trader import _load_json, _save_json

POSITIONS_FILE = "data/alpaca_crypto_positions.json"
RISK_PCT       = float(os.getenv("ALPACA_CRYPTO_RISK_PCT", "0.01"))
MAX_POS_PCT    = float(os.getenv("ALPACA_CRYPTO_MAX_POS_PCT", "0.05"))
MIN_NOTIONAL   = 10.0

_client = None
_tradable = None
_reported = False


def _order_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTC/USD' (Alpaca quotes crypto in USD)."""
    return symbol.split("/")[0] + "/USD"


def _pos_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSD' (how Alpaca names the open position)."""
    return symbol.split("/")[0] + "USD"


def _get_client():
    global _client
    if _client is not None:
        return _client
    key = os.getenv("ALPACA_API_KEY")
    sec = os.getenv("ALPACA_SECRET_KEY")
    if not ALPACA_AVAILABLE or not key or not sec:
        logging.error("[alpaca-crypto] alpaca-py missing or ALPACA_API_KEY/SECRET not set")
        return None
    _client = TradingClient(api_key=key, secret_key=sec, paper=True)
    return _client


def _tradable_set() -> set:
    global _tradable
    if _tradable is not None:
        return _tradable
    client = _get_client()
    if client is None:
        return set()
    try:
        assets = client.get_all_assets(
            GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
        )
        _tradable = {a.symbol.replace("/", "") for a in assets if a.tradable}
        return _tradable
    except Exception as e:
        logging.error(f"[alpaca-crypto] could not load Alpaca crypto asset list: {e}")
        return set()   # not cached, so it retries next cycle


def alpaca_supported(coins: list) -> list:
    """Filter a list of Binance-style symbols down to what Alpaca can trade."""
    global _reported
    t = _tradable_set()
    ok = [c for c in coins if _pos_symbol(c) in t]
    if t and not _reported:
        skipped = [c for c in coins if c not in ok]
        if skipped:
            print(f"  [alpaca-crypto] not available on Alpaca, skipping: {', '.join(skipped)}")
            logging.info(f"[alpaca-crypto] not on Alpaca, skipped: {skipped}")
        _reported = True
    return ok


def _result(success, action, message, quantity=0, size_usd=None,
            stop_loss=None, take_profit=None, pnl=None, exit_reason=None) -> dict:
    return {"success": success, "action": action, "message": message,
            "quantity": quantity, "size_usd": size_usd, "stop_loss": stop_loss,
            "take_profit": take_profit, "pnl": pnl, "exit_reason": exit_reason}


def _age_seconds(iso: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except Exception:
        return 1e9


def _close(client, symbol: str, price: float, positions: dict, reason: str) -> dict:
    pos = positions[symbol]
    try:
        client.close_position(_pos_symbol(symbol))
    except Exception as e:
        msg = str(e).lower()
        if "does not exist" in msg or "not found" in msg:
            logging.warning(f"[alpaca-crypto] {symbol}: already closed on Alpaca, dropping local record")
        else:
            logging.error(f"[alpaca-crypto] close failed for {symbol}: {e}")
            return _result(False, "SELL", f"[alpaca-crypto] close failed for {symbol}: {e}")

    entry    = pos.get("entry_price") or price
    notional = pos.get("notional", 0)
    pnl      = (price - entry) / entry * notional if entry else 0.0
    del positions[symbol]
    _save_json(POSITIONS_FILE, positions)
    text = f"[alpaca-crypto] SELL {symbol} @ {price:.6g} | est PnL ${pnl:+.2f} | {reason}"
    logging.info(text)
    return _result(True, "SELL", text, quantity=pos.get("est_qty", 0), size_usd=notional,
                   pnl=pnl, exit_reason=reason)


def execute_alpaca_crypto_trade(symbol, signal, price, atr=None,
                                stop_loss=None, take_profit=None) -> dict:
    """symbol is Binance-style ('BTC/USDT'). Same dict shape as execute_paper_trade."""
    if signal == 0:
        return _result(False, "HOLD", "hold")

    client = _get_client()
    if client is None:
        return _result(False, "NONE", "[alpaca-crypto] no Alpaca client (check keys / alpaca-py)")
    if _pos_symbol(symbol) not in _tradable_set():
        return _result(False, "NONE", f"[alpaca-crypto] {symbol} not available on Alpaca")

    positions = _load_json(POSITIONS_FILE, {})

    # ── BUY ──
    if signal == 1:
        if symbol in positions:
            return _result(False, "BUY", f"[alpaca-crypto] already holding {symbol}")

        try:
            equity = float(client.get_account().equity)
        except Exception as e:
            logging.error(f"[alpaca-crypto] could not read account: {e}")
            return _result(False, "BUY", f"[alpaca-crypto] could not read account: {e}")

        if stop_loss is not None and take_profit is not None and stop_loss < price:
            sl, tp = float(stop_loss), float(take_profit)
        elif atr:
            sl, tp = price - atr * 2.0, price + atr * 3.0
        else:
            sl, tp = price * 0.97, price * 1.06

        sl_dist = price - sl
        cap = equity * MAX_POS_PCT
        if sl_dist > 0:
            notional = equity * RISK_PCT * price / sl_dist
        else:
            notional = equity * 0.02
        notional = round(min(max(notional, MIN_NOTIONAL), cap), 2)

        try:
            req = MarketOrderRequest(
                symbol=_order_symbol(symbol),
                notional=notional,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
            )
            order = client.submit_order(order_data=req)
        except Exception as e:
            logging.error(f"[alpaca-crypto] BUY failed {symbol}: {e}")
            return _result(False, "BUY", f"[alpaca-crypto] BUY failed {symbol}: {e}")

        est_qty = round(notional / price, 8) if price else 0
        positions[symbol] = {
            "entry_price": price,
            "notional":    notional,
            "est_qty":     est_qty,
            "stop_loss":   round(sl, 8),
            "take_profit": round(tp, 8),
            "order_id":    str(order.id),
            "entry_time":  datetime.now(timezone.utc).isoformat(),
        }
        _save_json(POSITIONS_FILE, positions)
        text = (f"[alpaca-crypto] BUY {symbol} ${notional:.2f} @ ~{price:.6g} | "
                f"SL {sl:.6g} | TP {tp:.6g} | PAPER")
        logging.info(text)
        return _result(True, "BUY", text, quantity=est_qty, size_usd=notional,
                       stop_loss=sl, take_profit=tp)

    # ── SELL (close only, no shorting on Alpaca crypto) ──
    if signal == -1:
        if symbol not in positions:
            return _result(False, "SELL", f"[alpaca-crypto] no Alpaca position in {symbol}")
        return _close(client, symbol, price, positions, "SIGNAL")

    return _result(False, "NONE", "no action")


def check_alpaca_crypto_exits(alert_fn=None) -> None:
    """Software SL/TP for Alpaca crypto positions. Call once per cycle."""
    positions = _load_json(POSITIONS_FILE, {})
    if not positions:
        return
    client = _get_client()
    if client is None:
        return

    from data.market_data import fetch_ohlcv

    try:
        live = {p.symbol.replace("/", "") for p in client.get_all_positions()}
    except Exception as e:
        logging.error(f"[alpaca-crypto] could not list Alpaca positions: {e}")
        live = None

    for symbol, pos in list(positions.items()):
        try:
            # Closed outside the bot (e.g. from the dashboard)? Drop our record.
            # Skip if just opened, in case the fill hasn't shown up yet.
            if (live is not None and _pos_symbol(symbol) not in live
                    and _age_seconds(pos.get("entry_time", "")) > 120):
                del positions[symbol]
                _save_json(POSITIONS_FILE, positions)
                logging.info(f"[alpaca-crypto] {symbol}: no longer on Alpaca, record removed")
                continue

            df = fetch_ohlcv(symbol=symbol, limit=1)
            if df is None or df.is_empty():
                logging.error(f"[alpaca-crypto] {symbol}: no price, SL/TP not checked this cycle")
                continue
            price = float(df.tail(1)["close"][0])
            sl, tp = pos.get("stop_loss"), pos.get("take_profit")

            reason = None
            if sl and price <= sl:
                reason = "STOP_LOSS"
            elif tp and price >= tp:
                reason = "TAKE_PROFIT"
            if reason is None:
                continue

            print(f"\n[AUTO EXIT] {symbol} {reason} @ {price:.6g} (Alpaca paper)")
            res = _close(client, symbol, price, positions, reason)
            if alert_fn and res.get("success"):
                try:
                    alert_fn(res["message"], symbol)
                except Exception as e:
                    logging.error(f"[alpaca-crypto] alert failed: {e}")
        except Exception as e:
            logging.error(f"[alpaca-crypto] exit check failed for {symbol}: {e}")


def summarize_alpaca_crypto() -> None:
    client = _get_client()
    positions = _load_json(POSITIONS_FILE, {})
    print("\n" + "-" * 60)
    print(" ALPACA PAPER CRYPTO ".center(60))
    print("-" * 60)
    if client is not None:
        try:
            acct = client.get_account()
            print(f"  Equity: ${float(acct.equity):,.2f}   Cash: ${float(acct.cash):,.2f}")
        except Exception as e:
            print(f"  (could not read account: {e})")
    print(f"  Open bot-managed positions: {len(positions)}")
    for sym, p in positions.items():
        print(f"    {sym}: ${p.get('notional', 0):.2f} | SL {p.get('stop_loss')} | TP {p.get('take_profit')}")
    print("-" * 60 + "\n")
