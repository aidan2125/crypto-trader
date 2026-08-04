#!/usr/bin/env python3
"""
Enhanced Crypto Trading Bot
Dynamic ATR-based Risk Management + Multi-Channel Alerts + SQLite Trade Logger

TRADING_MODE options:
  "crypto" — crypto only (24/7)
  "stocks" — stocks only via Alpaca
  "dual"   — both, running in parallel (crypto 24/7, stocks during market hours)
"""

import logging
import os
import time
import time as _time
import argparse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    pl = None
    POLARS_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()
# ─────────────────────────────────────────────────────────────────────────────
# TRADING MODE — change this or pass --mode on the CLI
# ─────────────────────────────────────────────────────────────────────────────
TRADING_MODE = "dual"   # "crypto" | "stocks" | "dual"

COOLDOWN_SECONDS = 3600  # 1 hour cooldown after a stop-loss hit

# ─────────────────────────────────────────────────────────────────────────────
# Crypto imports
# ─────────────────────────────────────────────────────────────────────────────
from data.multi_coin_list import COIN_CURRENCY
from data.market_data import fetch_ohlcv
from strategies.enhanced_signals_refactored import enhanced_strategy
from strategies.adaptive_mode import choose_strategy_mode
from reports.plot_signals import plot_signals
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message
from data.last_signal_store import load_last_signals, save_last_signals
from execution.enhanced_paper_trader import execute_paper_trade, summarize_paper_trades
from backtest.run_backtest_simple import BacktestPro
from risk.dynamic_risk import load_enhanced_risk_config as load_config

# ─────────────────────────────────────────────────────────────────────────────
# SQLite Trade Logger
# ─────────────────────────────────────────────────────────────────────────────
from database.trade_logger import TradeLogger
_trade_logger = TradeLogger()   # opens / creates data/trades.db on first run

# ─────────────────────────────────────────────────────────────────────────────
# Stock imports — only loaded when TRADING_MODE includes stocks
# ─────────────────────────────────────────────────────────────────────────────
if TRADING_MODE in ("stocks", "dual"):
    from config.stock_watchlist import STOCK_WATCHLIST, STOCK_CURRENCY
    from data.market_data import fetch_stock_ohlcv
    from execution.alpaca_trader import (
        execute_stock_trade,
        summarize_stock_trades,
        check_stock_positions_for_exits,
    )
    from utils.market_hours import is_market_open, time_until_open

# ─────────────────────────────────────────────────────────────────────────────
# Directories & logging
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DEFAULT_CURRENCY = "USD"


# ─────────────────────────────────────────────────────────────────────────────
# Fix #2 — Cooldown tracking, wrapped instead of a bare module-level dict.
# Same in-memory behaviour as before (still lost on restart — that's a
# separate, deliberate future step: persist to disk if/when you want a
# restart to remember an active cooldown). For now this just gives every
# call site one interface instead of three places poking a raw dict.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CooldownTracker:
    cooldown_seconds: int
    _last_stop: dict = field(default_factory=dict)

    def is_active(self, key: str) -> tuple[bool, int]:
        """Returns (active, minutes_remaining)."""
        last_stop = self._last_stop.get(key, 0)
        remaining = self.cooldown_seconds - (_time.time() - last_stop)
        if remaining <= 0:
            return False, 0
        return True, int(remaining // 60)

    def start(self, key: str) -> None:
        self._last_stop[key] = _time.time()


_cooldown = CooldownTracker(COOLDOWN_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# Fix #3 — Exception handling that distinguishes "this symbol had a bad
# cycle, log it and move on" from "something is actually broken and hiding
# this would be worse than crashing." We don't have your exact ccxt/Alpaca
# exception classes in front of us, so this works off the error message
# rather than exception types — safer than guessing at import paths that
# might not match your installed library versions. Extend FATAL_MARKERS
# as you hit real cases.
# ─────────────────────────────────────────────────────────────────────────────
FATAL_ERROR_MARKERS = (
    "authenticat",       # authentication / authenticated
    "unauthorized",
    "invalid api key",
    "invalid api-key",
    "permission denied",
    "403",
    "401",
    "database disk image is malformed",
    "disk i/o error",
    "no space left on device",
)


def _is_fatal(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in FATAL_ERROR_MARKERS)


def _handle_symbol_error(exc: Exception, label: str) -> None:
    """Log-and-continue for ordinary errors; re-raise for the fatal set
    so the run loop / systemd sees it instead of silently retrying forever."""
    if _is_fatal(exc):
        logging.critical(f"{label}: FATAL error, stopping bot: {exc}")
        print(f"FATAL {label}: {exc} — bot is stopping, this needs attention")
        raise exc
    logging.error(f"{label}: {exc}")
    print(f"ERROR {label}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Shared alert helper
# ─────────────────────────────────────────────────────────────────────────────

def send_all_alerts(message: str, coin: str = "") -> dict:
    results = {"telegram": False, "email": False, "discord": False}

    try:
        if send_discord_message(message):
            results["discord"] = True
            logging.info(f"Discord alert sent: {coin}")
    except Exception as e:
        logging.error(f"Discord failed ({coin}): {e}")

    try:
        send_telegram_message(message)
        results["telegram"] = True
        logging.info(f"Telegram alert sent: {coin}")
    except Exception as e:
        logging.error(f"Telegram failed ({coin}): {e}")

    try:
        subject = f"{coin} Signal" if coin else "Bot Alert"
        send_email(subject=subject, body=message)
        results["email"] = True
        logging.info(f"Email alert sent: {coin}")
    except Exception as e:
        logging.error(f"Email failed ({coin}): {e}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Fix #1 — Unified core. run_for_coin() and run_for_stock() were ~110 lines
# each, identical except for: data source, cooldown key, execute call,
# asset_type string, field label ("Coin"/"Ticker"), alert title, and
# whether a signal plot gets written. Everything else — cooldown check,
# trade execution, SQLite logging (trade + signal), alert building,
# last-signal persistence — was byte-for-byte the same logic duplicated
# twice. This collapses it to one function; run_for_coin/run_for_stock
# below become thin adapters that just supply the asset-specific bits.
# ─────────────────────────────────────────────────────────────────────────────

def run_for_symbol(
    symbol: str,
    *,
    asset_type: str,                       # "crypto" | "stock"
    fetch_fn: Callable[[], object],         # zero-arg callable -> df
    currency: str,
    execute_fn: Callable[[str, int, float, str, Optional[float]], dict],
    cooldown_key: str,
    field_label: str,                      # "Coin" or "Ticker"
    signal_title: str,                      # "SIGNAL CHANGE" / "STOCK SIGNAL CHANGE"
    log_prefix: str = "",                  # "" for crypto, "[stocks] " for stocks
    do_plot: bool = False,
    strategy_mode: str = "strict",
) -> None:
    try:
        df = fetch_fn()
        if df is None or df.is_empty():
            logging.warning(f"{log_prefix}{symbol}: No data")
            return

        df = enhanced_strategy(df, mode=strategy_mode)

        if "signal" not in df.columns:
            logging.warning(f"{log_prefix}{symbol}: No signal generated")
            return

        if do_plot:
            try:
                plot_signals(df, filename=f"{symbol.replace('/', '_')}_signals.png")
            except Exception as e:
                logging.error(f"{symbol}: Plot error: {e}")

        last_row       = df.tail(1)
        current_signal = int(last_row["signal"][0])   if "signal" in last_row.columns else 0
        price          = float(last_row["close"][0])  if "close"  in last_row.columns else 0.0

        atr = None
        if "atr" in last_row.columns and last_row["atr"][0] is not None:
            atr = float(last_row["atr"][0])

        signal_quality = None
        if "signal_quality" in last_row.columns and last_row["signal_quality"][0] is not None:
            signal_quality = float(last_row["signal_quality"][0])

        if current_signal not in (-1, 0, 1):
            logging.warning(f"{log_prefix}{symbol}: Invalid signal {current_signal}")
            return

        # ── Cooldown check ────────────────────────────────────────────────────
        if current_signal in (1, -1):
            active, mins_left = _cooldown.is_active(cooldown_key)
            if active:
                logging.info(f"{log_prefix}{symbol}: Skipping signal — cooldown active ({mins_left}m left)")
                print(f"  [{symbol}] Cooldown active — {mins_left}m remaining, skipping signal")
                return

        last_signals    = load_last_signals()
        previous_signal = last_signals.get(cooldown_key)

        trade_result = None
        if current_signal != previous_signal:
            trade_result = execute_fn(symbol, current_signal, price, currency, atr)

            # ── Stop-loss cooldown ────────────────────────────────────────────
            _exit_reason = trade_result.get("exit_reason") if isinstance(trade_result, dict) else None
            if _exit_reason == "STOP_LOSS" or (trade_result and not isinstance(trade_result, dict) and "STOP_LOSS" in str(trade_result)):
                _cooldown.start(cooldown_key)
                logging.info(f"{log_prefix}{symbol}: Stop-loss hit — cooldown started ({COOLDOWN_SECONDS//60}m)")
                print(f"  [{symbol}] Stop-loss hit — cooldown started ({COOLDOWN_SECONDS//60}m)")

            # ── Log trade to SQLite ───────────────────────────────────────────
            # STOPGAP: trade_result is currently a plain string in most real
            # paths (execute_paper_trade / execute_stock_trade return
            # f-strings, not dicts). Calling .get() on a string crashed this
            # function before reaching save_last_signals — confirmed live via
            # "'str' object has no attribute 'get'" in logs/bot.log.
            # Real fix: make execute_paper_trade/execute_stock_trade always
            # return a dict. Tracked separately.
            if isinstance(trade_result, dict):
                _direction = "LONG"  if current_signal == 1  else \
                             "SHORT" if current_signal == -1 else "FLAT"
                _action    = "ENTRY" if current_signal in (1, -1) else "EXIT"
                _trade_logger.log_trade(
                    symbol         = symbol,
                    action         = _action,
                    direction      = _direction,
                    price          = price,
                    quantity       = trade_result.get("quantity", 0),
                    asset_type     = asset_type,
                    position_size  = trade_result.get("size_usd"),
                    stop_loss      = trade_result.get("stop_loss"),
                    take_profit    = trade_result.get("take_profit"),
                    pnl            = trade_result.get("pnl"),
                    exit_reason    = trade_result.get("exit_reason"),
                    atr            = atr,
                    signal_quality = signal_quality,
                    strategy_mode  = strategy_mode,
                )
            elif trade_result:
                # String result — still get it into trades.db, just without
                # the structured numeric fields we can't pull out of a string.
                _direction = "LONG"  if current_signal == 1  else \
                             "SHORT" if current_signal == -1 else "FLAT"
                _action    = "ENTRY" if current_signal in (1, -1) else "EXIT"
                logging.info(f"{log_prefix}{symbol}: trade_result was a string, not a dict — logging message only")
                _trade_logger.log_trade(
                    symbol         = symbol,
                    action         = _action,
                    direction      = _direction,
                    price          = price,
                    quantity       = 0,
                    asset_type     = asset_type,
                    exit_reason    = str(trade_result)[:200],
                    atr            = atr,
                    signal_quality = signal_quality,
                    strategy_mode  = strategy_mode,
                )

        # ── Log signal every cycle to SQLite ─────────────────────────────────
        _trade_logger.log_signal(
            symbol         = symbol,
            new_signal     = current_signal,
            prev_signal    = previous_signal,
            price          = price,
            asset_type     = asset_type,
            atr            = atr,
            signal_quality = signal_quality,
            strategy_mode  = strategy_mode,
            acted_on       = trade_result is not None,
        )

        if current_signal != previous_signal:
            # ── Build & send alert ────────────────────────────────────────────
            signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}
            signal_name  = signal_names.get(current_signal, str(current_signal))

            message_parts = [
                f"**{signal_title}**",
                f"{(field_label + ':').ljust(10)}{symbol}",
                f"Signal:   {signal_name}",
                f"Price:    ${price:.2f} {currency}",
                f"Previous: {signal_names.get(previous_signal, 'None')}",
            ]
            if atr is not None:
                message_parts.append(f"ATR:      ${atr:.2f}")
            if signal_quality is not None:
                message_parts.append(f"Quality:  {signal_quality:.0f}/100")
            if isinstance(trade_result, dict):
                _trade_display = trade_result.get("message", "No action")
            else:
                _trade_display = trade_result or "No action"
            message_parts.append(f"\nTrade: {_trade_display}")

            message      = "\n".join(message_parts)
            alert_results = send_all_alerts(message, symbol)
            alerts_sent  = ", ".join(k for k, v in alert_results.items() if v)

            last_signals[cooldown_key] = current_signal
            save_last_signals(last_signals)

            log_msg = f"{log_prefix}{symbol}: {previous_signal} → {current_signal}"
            if signal_quality is not None:
                log_msg += f" | Quality: {signal_quality:.0f}"
            log_msg += f" | Alerts: {alerts_sent}"
            logging.info(log_msg)
            print(f"\n{message}\nAlerts: {alerts_sent}\n")

        else:
            logging.info(f"{log_prefix}{symbol}: No change (signal {current_signal})")

    except Exception as e:
        _handle_symbol_error(e, f"{log_prefix}{symbol}")


# ─────────────────────────────────────────────────────────────────────────────
# Thin adapters — asset-specific wiring only. All shared logic now lives in
# run_for_symbol() above, so a bugfix there (like today's circuit breaker)
# only needs to happen once.
# ─────────────────────────────────────────────────────────────────────────────

def run_for_coin(coin: str) -> None:
    currency  = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)
    timeframe = "4h" if any(x in coin for x in ["BTC", "ETH"]) else "1h"

    def _execute(symbol, signal, price, currency, atr):
        return execute_paper_trade(coin=symbol, signal=signal, price=price, currency=currency, atr=atr)

    run_for_symbol(
        coin,
        asset_type   = "crypto",
        fetch_fn     = lambda: fetch_ohlcv(symbol=coin, timeframe=timeframe),
        currency     = currency,
        execute_fn   = _execute,
        cooldown_key = coin,
        field_label  = "Coin",
        signal_title = "SIGNAL CHANGE",
        log_prefix   = "",
        do_plot      = True,
    )


def run_for_stock(ticker: str, risk_config: dict | None = None) -> None:
    currency = STOCK_CURRENCY.get(ticker, "USD")

    def _execute(symbol, signal, price, currency, atr):
        return execute_stock_trade(
            ticker=symbol, signal=signal, price=price, currency=currency,
            atr=atr, risk_config=risk_config,
        )

    run_for_symbol(
        ticker,
        asset_type   = "stock",
        fetch_fn     = lambda: fetch_stock_ohlcv(symbol=ticker, timeframe="1h", limit=500),
        currency     = currency,
        execute_fn   = _execute,
        cooldown_key = f"STOCK:{ticker}",
        field_label  = "Ticker",
        signal_title = "STOCK SIGNAL CHANGE",
        log_prefix   = "[stocks] ",
        do_plot      = False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CRYPTO position exit checker
# ─────────────────────────────────────────────────────────────────────────────

def check_all_positions_for_exits():
    try:
        from execution.enhanced_paper_trader import load_json, POSITIONS_FILE
        positions = load_json(POSITIONS_FILE, {})
        if not positions:
            return

        for coin, position in list(positions.items()):
            try:
                df = fetch_ohlcv(symbol=coin, limit=1)
                if df is None or df.is_empty():
                    continue

                current_price = float(df["close"][0])
                sl            = position.get("stop_loss")
                tp            = position.get("take_profit")
                currency      = position.get("currency", DEFAULT_CURRENCY)

                if sl and current_price <= sl:
                    logging.info(f"{coin}: Stop Loss hit at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Stop Loss hit!")
                    result = execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    _cooldown.start(coin)

                    # STOPGAP: same string-vs-dict guard as run_for_symbol.
                    if isinstance(result, dict):
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",   # exiting a long position
                            price       = current_price,
                            quantity    = result.get("quantity", 0),
                            asset_type  = "crypto",
                            pnl         = result.get("pnl"),
                            exit_reason = "SL",
                        )
                    elif result:
                        logging.info(f"{coin}: SL exit result was a string, not a dict — logging message only")
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = 0,
                            asset_type  = "crypto",
                            exit_reason = f"SL: {str(result)[:190]}",
                        )

                elif tp and current_price >= tp:
                    logging.info(f"{coin}: Take Profit hit at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Take Profit hit!")
                    result = execute_paper_trade(coin, -1, current_price, currency, override_risk=True)

                    # STOPGAP: same string-vs-dict guard as run_for_symbol.
                    if isinstance(result, dict):
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = result.get("quantity", 0),
                            asset_type  = "crypto",
                            pnl         = result.get("pnl"),
                            exit_reason = "TP",
                        )
                    elif result:
                        logging.info(f"{coin}: TP exit result was a string, not a dict — logging message only")
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = 0,
                            asset_type  = "crypto",
                            exit_reason = f"TP: {str(result)[:190]}",
                        )

            except Exception as e:
                _handle_symbol_error(e, f"position check {coin}")

    except Exception as e:
        logging.error(f"Error in check_all_positions_for_exits: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Startup backtest (no Supabase)
# ─────────────────────────────────────────────────────────────────────────────

def run_startup_backtest_check():
    print("\n" + "═" * 80)
    print(" STARTUP BACKTEST HEALTH CHECK ".center(80))
    print("═" * 80 + "\n")

    try:
        config = load_config()
        if config is None:
            print("No risk config found → using defaults")
            config = {}

        symbol    = "BTC/USDT"
        timeframe = "4h"
        limit     = 3000

        print(f"Fetching {symbol} {timeframe} data ({limit} candles)...")
        df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

        if df is None or df.is_empty():
            print("→ No data for backtest — skipping")
            return

        # Step 1: indicator pass so ATR exists before mode selection
        df_indicator_pass = enhanced_strategy(df.clone(), mode="strict")

        # Step 2: choose mode using the frame that already has ATR
        selected_mode = choose_strategy_mode(symbol, df_indicator_pass, requested_mode="auto")
        print(f"Selected strategy mode: {selected_mode}")

        # Step 3: final strategy pass with the resolved mode
        df = enhanced_strategy(df.clone(), mode=selected_mode)

        print("Running backtest simulation...")
        backtester = BacktestPro(initial_balance=10000, risk_config=config)
        backtester.run(df, symbol=symbol, strategy_name=f"Enhanced Strategy [{selected_mode}]")

        # Print summary to console — no external DB needed
        if not POLARS_AVAILABLE:
            print("→ polars not available on this platform — skipping backtest health check")
            return

        df_trades    = pl.DataFrame(backtester.trades) if backtester.trades else pl.DataFrame()
        total_trades = df_trades.height
        if total_trades > 0:
            roi        = (backtester.balance / backtester.initial_balance - 1) * 100
            win_rate   = df_trades.filter(pl.col("pnl") > 0).height / total_trades * 100
            gross_profit = df_trades.filter(pl.col("pnl") > 0)["pnl"].sum()
            gross_loss   = abs(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum())
            pf           = gross_profit / gross_loss if gross_loss > 0 else 0.0
            print(
                f"\nStartup Backtest Result:\n"
                f"  Trades:         {total_trades}\n"
                f"  Win Rate:       {win_rate:.1f}%\n"
                f"  Profit Factor:  {pf:.2f}\n"
                f"  ROI:            {roi:+.1f}%\n"
                f"  Final Balance:  ${backtester.balance:,.2f}\n"
            )
        else:
            print("→ Backtest produced no trades")

    except Exception as e:
        print(f"Backtest health check failed: {e}")
        import traceback
        traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

def main(continuous: bool = False, interval: int = 300):
    run_startup_backtest_check()

    # ── Start DB run session ──────────────────────────────────────────────────
    _trade_logger.start_run(mode=TRADING_MODE)

    run_count = 0
    config    = load_config() or {}

    print("\nRisk Config:")
    print(f"  Max Positions:  {config.get('max_positions', 5)}")
    print(f"  Max Risk/Trade: {config.get('max_loss_per_trade_pct', 0.02)*100:.1f}%")
    print(f"  ATR SL: {config.get('atr_multiplier_sl', 2.0)}× | TP: {config.get('atr_multiplier_tp', 3.0)}×")

    while True:
        run_count += 1

        # ── Heartbeat — Telegram bot reads this for /status ───────────────────
        _trade_logger.write_heartbeat(loop_count=run_count)

        print(f"\n{'='*70}")
        print(f"RUN #{run_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | MODE: {TRADING_MODE.upper()}".center(70))
        print(f"{'='*70}\n")

        # ── Pause check — honours /pause from Telegram bot ────────────────────
        from pathlib import Path
        import json as _json
        pause_file = Path("data/pause_state.json")
        if pause_file.exists():
            try:
                with open(pause_file) as _f:
                    _ps = _json.load(_f)
                if _ps.get("paused"):
                    print("  [PAUSED] Trading paused via Telegram — skipping this cycle")
                    logging.info(f"Run #{run_count} skipped — bot is paused")
                    if not continuous:
                        break
                    print(f"  Next check in {interval} seconds...")
                    time.sleep(interval)
                    continue
            except Exception:
                pass

        # ── CRYPTO LOOP ───────────────────────────────────────────────────────
        if TRADING_MODE in ("crypto", "dual"):
            print("── CRYPTO ──────────────────────────────────────────────────")
            for coin in COIN_CURRENCY:
                print(f"→ {coin}")
                run_for_coin(coin)
                time.sleep(1)

            print("\n→ Checking crypto positions for exits...")
            check_all_positions_for_exits()

            print(f"\n{'='*70}")
            summarize_paper_trades()
            print(f"{'='*70}\n")

        # ── STOCK LOOP ────────────────────────────────────────────────────────
        if TRADING_MODE in ("stocks", "dual"):
            print("── STOCKS ──────────────────────────────────────────────────")

            if is_market_open():
                print("  Market is OPEN — running stock signals\n")
                for ticker in STOCK_WATCHLIST:
                    print(f"→ {ticker}")
                    run_for_stock(ticker, risk_config=config)
                    time.sleep(1)

                print("\n→ Checking stock positions for exits...")
                check_stock_positions_for_exits(fetch_stock_ohlcv)

                print(f"\n{'='*70}")
                summarize_stock_trades()
                print(f"{'='*70}\n")

            else:
                secs  = time_until_open()
                hours = secs // 3600
                mins  = (secs % 3600) // 60
                print(f"  Market is CLOSED — next open in {hours}h {mins}m")
                print("  Skipping stock signals\n")

        if not continuous:
            break

        print(f"Next run in {interval} seconds...")
        time.sleep(interval)

    # ── Clean shutdown ────────────────────────────────────────────────────────
    _trade_logger.end_run(run_count=run_count)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced Crypto/Stock Trading Bot")
    parser.add_argument("--once",     action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds (default: 300)")
    parser.add_argument(
        "--mode",
        choices=["crypto", "stocks", "dual"],
        default=None,
        help="Override TRADING_MODE",
    )
    args = parser.parse_args()

    if args.mode:
        TRADING_MODE = args.mode

    main(continuous=not args.once, interval=args.interval)