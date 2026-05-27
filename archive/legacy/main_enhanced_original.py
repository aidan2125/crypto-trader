#!/usr/bin/env python3
"""
Enhanced Crypto Trading Bot
Dynamic ATR-based Risk Management + Multi-Channel Alerts
SECURITY HARDENED VERSION
"""

import logging
import os
import time
import json
import argparse
from datetime import datetime, timezone
import threading
from typing import Optional, Dict, Any

import polars as pl

from data.multi_coin_list import COIN_CURRENCY
from data.market_data import fetch_ohlcv
from strategies.enhanced_signals_refactored import enhanced_strategy
from reports.plot_signals import plot_signals
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message
from data.last_signal_store import load_last_signals, save_last_signals
from execution.enhanced_paper_trader import (
    execute_paper_trade, 
    summarize_paper_trades,
    load_json,
    POSITIONS_FILE
)

# Import BacktestPro
from run_backtest_simple import BacktestPro

# Supabase integration
try:
    from database.supabase_db import get_active_preset, insert_backtest_result
except ImportError:
    get_active_preset = None
    insert_backtest_result = None
    logging.warning("Supabase integration not available")

# Risk config
from risk.dynamic_risk import load_enhanced_risk_config as load_config

# ═══════════════════════════════════════════════════════════════════
# SECURITY: ENVIRONMENT VARIABLE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

# Load sensitive credentials from environment variables with fallback
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")

# Validate required environment variables on startup
def validate_environment_variables() -> bool:
    """
    Validate that all required environment variables are set.
    Returns True if all required vars are present, False otherwise.
    """
    missing_vars = []
    
    if not TELEGRAM_TOKEN:
        missing_vars.append("TELEGRAM_BOT_TOKEN")
    
    if not ALLOWED_USER_ID:
        missing_vars.append("TELEGRAM_ALLOWED_USER_ID")
    
    if missing_vars:
        logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        print(f"\nERROR: Missing environment variables:")
        print(f"   {', '.join(missing_vars)}")
        print(f"\nPlease set them in your environment or .env file:")
        print(f"   export TELEGRAM_BOT_TOKEN='your_token_here'")
        print(f"   export TELEGRAM_ALLOWED_USER_ID='your_user_id_here'\n")
        return False
    
    # Validate ALLOWED_USER_ID is numeric
    try:
        int(ALLOWED_USER_ID)
    except (ValueError, TypeError):
        logging.error(f"TELEGRAM_ALLOWED_USER_ID must be numeric, got: {ALLOWED_USER_ID}")
        print(f"\nERROR: TELEGRAM_ALLOWED_USER_ID must be a numeric ID")
        return False
    
    return True


# ═══════════════════════════════════════════════════════════════════
# DIRECTORY SETUP
# ═══════════════════════════════════════════════════════════════════

# Create required directories with proper permissions
def setup_directories():
    """Create required directories with appropriate permissions."""
    directories = ["logs", "reports", "data/signals"]
    
    for directory in directories:
        try:
            os.makedirs(directory, mode=0o750, exist_ok=True)
            logging.debug(f"Directory ready: {directory}")
        except Exception as e:
            logging.error(f"Failed to create directory {directory}: {e}")
            raise


# ═══════════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

def setup_logging():
    """Configure secure logging with rotation and proper permissions."""
    log_file = "logs/bot.log"
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", mode=0o750, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Also log to console for monitoring
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console.setFormatter(formatter)
    logging.getLogger("").addHandler(console)
    
    # Set file permissions
    try:
        if os.path.exists(log_file):
            os.chmod(log_file, 0o640)
    except Exception as e:
        logging.warning(f"Could not set log file permissions: {e}")


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

DEFAULT_CURRENCY = "USD"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


# ═══════════════════════════════════════════════════════════════════
# ALERT FUNCTIONS WITH ENHANCED ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════

def send_all_alerts(message: str, coin: str = "") -> Dict[str, bool]:
    """
    Send alerts through all configured channels with retry logic.
    
    Args:
        message: Alert message to send
        coin: Coin symbol for logging
        
    Returns:
        Dictionary of channel success statuses
    """
    results = {"telegram": False, "email": False, "discord": False}
    
    # Sanitize message to prevent injection attacks
    sanitized_message = message.replace("<", "&lt;").replace(">", "&gt;")
    
    # Discord
    for attempt in range(MAX_RETRIES):
        try:
            if send_discord_message(sanitized_message):
                results["discord"] = True
                logging.info(f"Discord alert sent: {coin}")
                break
        except Exception as e:
            logging.error(f"Discord attempt {attempt + 1}/{MAX_RETRIES} failed ({coin}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    # Telegram
    for attempt in range(MAX_RETRIES):
        try:
            send_telegram_message(sanitized_message)
            results["telegram"] = True
            logging.info(f"Telegram alert sent: {coin}")
            break
        except Exception as e:
            logging.error(f"Telegram attempt {attempt + 1}/{MAX_RETRIES} failed ({coin}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    # Email
    for attempt in range(MAX_RETRIES):
        try:
            subject = f"{coin} Signal" if coin else "Bot Alert"
            send_email(subject=subject, body=sanitized_message)
            results["email"] = True
            logging.info(f"Email alert sent: {coin}")
            break
        except Exception as e:
            logging.error(f"Email attempt {attempt + 1}/{MAX_RETRIES} failed ({coin}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    return results


# ═══════════════════════════════════════════════════════════════════
# COIN PROCESSING WITH ENHANCED ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════

def run_for_coin(coin: str) -> None:
    """
    Process trading signals for a single coin with comprehensive error handling.
    
    Args:
        coin: Trading pair symbol (e.g., 'BTC/USDT')
    """
    try:
        currency = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)
        
        # Fetch market data
        df = fetch_ohlcv(symbol=coin)
        if df is None or df.is_empty():
            logging.warning(f"{coin}: No data available")
            return
        
        # Apply trading strategy
        df = enhanced_strategy(df, mode="strict")
        if "signal" not in df.columns:
            logging.warning(f"{coin}: No signal generated")
            return
        
        # Generate and save chart
        try:
            safe_filename = coin.replace('/', '_')
            plot_signals(df, filename=f"reports/{safe_filename}_signals.png")
        except Exception as e:
            logging.warning(f"{coin}: Chart generation failed: {e}")
        
        # Extract latest signal data safely
        last_row = df.tail(1)
        
        current_signal = int(last_row["signal"][0]) if "signal" in last_row.columns else 0
        price = float(last_row["close"][0]) if "close" in last_row.columns else 0.0
        
        atr = None
        if "atr" in last_row.columns and last_row["atr"][0] is not None:
            atr = float(last_row["atr"][0])
        
        signal_quality = None
        if "signal_quality" in last_row.columns and last_row["signal_quality"][0] is not None:
            signal_quality = float(last_row["signal_quality"][0])
        
        # Validate signal
        if current_signal not in [-1, 0, 1]:
            logging.warning(f"{coin}: Invalid signal value {current_signal}")
            return
        
        # Check for signal changes
        last_signals = load_last_signals()
        previous_signal = last_signals.get(coin)
        
        if current_signal != previous_signal:
            # Execute paper trade
            trade_result = execute_paper_trade(
                coin=coin,
                signal=current_signal,
                price=price,
                currency=currency,
                atr=atr
            )
            
            # Prepare alert message
            signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}
            signal_name = signal_names.get(current_signal, str(current_signal))
            
            message_parts = [
                f"**SIGNAL CHANGE**",
                f"Coin: {coin}",
                f"Signal: {signal_name}",
                f"Price: ${price:.2f} {currency}",
                f"Previous: {signal_names.get(previous_signal, 'None')}"
            ]
            
            if atr is not None:
                message_parts.append(f"ATR: ${atr:.2f}")
            
            if signal_quality is not None:
                message_parts.append(f"Quality: {signal_quality:.0f}/100")
            
            message_parts.append(f"\nTrade: {trade_result or 'No action'}")
            message = "\n".join(message_parts)
            
            # Send alerts
            alert_results = send_all_alerts(message, coin)
            alerts_sent = ", ".join(k for k, v in alert_results.items() if v)
            
            # Update signal history
            last_signals[coin] = current_signal
            save_last_signals(last_signals)
            
            # Log the change
            log_msg = f"{coin}: {previous_signal} → {current_signal}"
            if signal_quality is not None:
                log_msg += f" | Quality: {signal_quality:.0f}"
            log_msg += f" | Alerts: {alerts_sent}"
            
            logging.info(log_msg)
            print(f"\n{message}\nAlerts: {alerts_sent}\n")
        else:
            logging.debug(f"{coin}: No change (signal {current_signal})")
    
    except Exception as e:
        logging.error(f"{coin} processing error: {e}", exc_info=True)
        print(f"ERROR processing {coin}: {e}")


# ═══════════════════════════════════════════════════════════════════
# POSITION MONITORING
# ═══════════════════════════════════════════════════════════════════

def check_all_positions_for_exits() -> None:
    """
    Monitor all open positions for stop-loss and take-profit triggers.
    Automatically exits positions when thresholds are hit.
    """
    try:
        positions = load_json(POSITIONS_FILE, {})
        
        if not positions:
            logging.debug("No open positions to monitor")
            return
        
        logging.info(f"Monitoring {len(positions)} open positions")
        
        for coin, position in list(positions.items()):
            try:
                # Fetch current price
                df = fetch_ohlcv(symbol=coin, limit=1)
                if df is None or df.is_empty():
                    logging.warning(f"Could not fetch price for {coin}")
                    continue
                
                current_price = float(df["close"][0])
                sl = position.get("stop_loss")
                tp = position.get("take_profit")
                currency = position.get("currency", DEFAULT_CURRENCY)
                
                # Check stop-loss
                if sl and current_price <= sl:
                    logging.info(f"{coin}: Stop Loss triggered at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Stop Loss hit at ${current_price:.2f}!")
                    
                    exit_result = execute_paper_trade(
                        coin, 
                        -1, 
                        current_price, 
                        currency, 
                        override_risk=True
                    )
                    
                    # Send alert
                    message = (
                        f"**STOP LOSS TRIGGERED**\n"
                        f"Coin: {coin}\n"
                        f"Exit Price: ${current_price:.2f}\n"
                        f"Stop Loss: ${sl:.2f}\n"
                        f"Result: {exit_result}"
                    )
                    send_all_alerts(message, coin)
                
                # Check take-profit
                elif tp and current_price >= tp:
                    logging.info(f"{coin}: Take Profit triggered at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Take Profit hit at ${current_price:.2f}!")
                    
                    exit_result = execute_paper_trade(
                        coin, 
                        -1, 
                        current_price, 
                        currency, 
                        override_risk=True
                    )
                    
                    # Send alert
                    message = (
                        f"**TAKE PROFIT TRIGGERED**\n"
                        f"Coin: {coin}\n"
                        f"Exit Price: ${current_price:.2f}\n"
                        f"Take Profit: ${tp:.2f}\n"
                        f"Result: {exit_result}"
                    )
                    send_all_alerts(message, coin)
            
            except Exception as e:
                logging.error(f"Error checking position {coin}: {e}", exc_info=True)
    
    except Exception as e:
        logging.error(f"Error in check_all_positions_for_exits: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════
# STARTUP BACKTEST
# ═══════════════════════════════════════════════════════════════════

def run_startup_backtest_check() -> Optional[Dict[str, Any]]:
    """
    Run a backtest on startup to validate strategy performance.
    
    Returns:
        Backtest results dictionary or None if failed
    """
    print("\n" + "=" * 80)
    print(" STARTUP BACKTEST HEALTH CHECK ".center(80))
    print("=" * 80 + "\n")
    
    try:
        risk_config = None
        
        # Try to load from Supabase first
        if get_active_preset:
            try:
                supabase_preset = get_active_preset("moderate")
                if supabase_preset:
                    risk_config = supabase_preset
                    print("Loaded 'moderate' preset from Supabase")
            except Exception as e:
                logging.warning(f"Supabase preset failed: {e}")
                print(f"Supabase preset failed: {e}")
        
        # Fallback to local config
        if risk_config is None:
            risk_config = load_config()
            print("Using local config fallback for backtest")
        
        if risk_config is None:
            print("No risk config available - using defaults")
            risk_config = {}
        
        # Backtest parameters
        symbol = "BTC/USDT"
        timeframe = "1h"
        limit = 3000
        
        print(f"Fetching {symbol} {timeframe} data (last {limit} candles)...")
        df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
        
        if df is None or df.is_empty():
            logging.warning("No data available for backtest")
            print("No data available for backtest")
            return None
        
        print(f"Loaded {df.height} candles")
        
        # Apply strategy
        df = enhanced_strategy(df, mode="strict")
        print("Strategy signals generated")
        
        # Run backtest
        print("Running backtest simulation...")
        backtester = BacktestPro(initial_balance=10000, risk_config=risk_config)
        backtester.run(df, symbol=symbol, strategy_name="Enhanced Strategy")
        
        # Calculate metrics
        df_trades = pl.DataFrame(backtester.trades) if backtester.trades else pl.DataFrame()
        
        if df_trades.height > 0:
            total_pnl = df_trades["pnl"].sum()
            roi = (backtester.balance / backtester.initial_balance - 1)
            win_rate = df_trades.filter(pl.col("pnl") > 0).height / df_trades.height
            
            gross_profit = df_trades.filter(pl.col("pnl") > 0)["pnl"].sum()
            gross_loss = abs(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
            
            equity_curve = pl.Series([backtester.initial_balance] + backtester.equity)
            max_dd = (equity_curve / equity_curve.cum_max() - 1).min()
            avg_pnl = df_trades["pnl"].mean()
        else:
            total_pnl = roi = win_rate = profit_factor = max_dd = avg_pnl = 0.0
        
        print(f"\n{'-' * 80}")
        print(f"BACKTEST RESULTS:")
        print(f"  Total Trades: {len(backtester.trades)}")
        print(f"  Win Rate: {win_rate*100:.1f}%")
        print(f"  ROI: {roi*100:.2f}%")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Max Drawdown: {max_dd*100:.2f}%")
        print(f"{'-' * 80}\n")
        
        # Save to Supabase if available
        if insert_backtest_result:
            print("Saving backtest result to Supabase...")
            
            try:
                result = {
                    "preset_id": int(2),
                    "coin_id": int(1),
                    "run_time": datetime.now(timezone.utc).isoformat(),
                    "timeframe": str(timeframe),
                    "num_candles": int(df.height),
                    "num_trades": int(len(backtester.trades)),
                    "win_rate": float(win_rate),
                    "profit_factor": float(profit_factor),
                    "roi": float(roi),
                    "max_drawdown": float(max_dd),
                    "avg_pnl": float(avg_pnl),
                    "passed": int(roi > 0)
                }
                
                success = insert_backtest_result(result)
                if success:
                    print("Backtest result saved to Supabase")
                else:
                    print("Failed to save backtest result")
            
            except Exception as e:
                logging.error(f"Startup backtest save failed: {e}", exc_info=True)
                print(f"Backtest save failed: {e}")
        
        return {
            "roi": roi,
            "win_rate": win_rate,
            "num_trades": len(backtester.trades)
        }
    
    except Exception as e:
        logging.error(f"Backtest health check failed: {e}", exc_info=True)
        print(f"Backtest health check failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# MAIN TRADING LOOP
# ═══════════════════════════════════════════════════════════════════

def main(continuous: bool = False, interval: int = 300) -> None:
    """
    Main trading bot loop.
    
    Args:
        continuous: If True, runs continuously. If False, runs once and exits.
        interval: Sleep interval between runs (seconds)
    """
    # Run startup backtest
    backtest_results = run_startup_backtest_check()
    
    if backtest_results and backtest_results.get("roi", 0) < 0:
        logging.warning("Startup backtest showed negative ROI - strategy may need adjustment")
        print("WARNING: Startup backtest showed negative ROI")
    
    run_count = 0
    
    # Load risk configuration
    supabase_config = None
    if get_active_preset:
        try:
            supabase_config = get_active_preset("moderate")
        except Exception as e:
            logging.warning(f"Failed to load Supabase config: {e}")
    
    config = supabase_config if supabase_config else load_config()
    
    if not config:
        logging.warning("No risk config loaded - using defaults")
        config = {}
    
    print("\n" + "=" * 80)
    print(" TRADING BOT STARTING ".center(80))
    print("=" * 80)
    print(f"\nRisk Configuration:")
    print(f"  Max Positions: {config.get('max_positions', 5)}")
    print(f"  Risk per Trade: {config.get('risk_per_trade', 0.02)*100:.1f}%")
    print(f"  Max Loss per Trade: {config.get('max_loss_per_trade_pct', 0.02)*100:.1f}%")
    print(f"  ATR Stop Loss: {config.get('atr_multiplier_sl', 2.0)}x")
    print(f"  ATR Take Profit: {config.get('atr_multiplier_tp', 3.0)}x")
    print(f"\nMode: {'CONTINUOUS' if continuous else 'SINGLE RUN'}")
    if continuous:
        print(f"Interval: {interval} seconds")
    print("=" * 80 + "\n")
    
    # Main loop
    while True:
        run_count += 1
        run_start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"RUN #{run_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(70))
        print(f"{'='*70}\n")
        
        # Process each coin
        coins_processed = 0
        coins_failed = 0
        
        for coin in COIN_CURRENCY:
            print(f"Processing {coin}...")
            try:
                run_for_coin(coin)
                coins_processed += 1
                time.sleep(1)  # Rate limiting
            except Exception as e:
                logging.error(f"Failed to process {coin}: {e}", exc_info=True)
                print(f"Failed to process {coin}: {e}")
                coins_failed += 1
        
        # Check positions for exits
        print("\nChecking open positions for exits...")
        try:
            check_all_positions_for_exits()
        except Exception as e:
            logging.error(f"Position check failed: {e}", exc_info=True)
            print(f"Position check failed: {e}")
        
        # Summary
        print(f"\n{'='*70}")
        print(f"RUN SUMMARY:")
        print(f"  Coins Processed: {coins_processed}/{len(COIN_CURRENCY)}")
        if coins_failed > 0:
            print(f"  Coins Failed: {coins_failed}")
        print(f"  Run Duration: {time.time() - run_start_time:.1f}s")
        
        try:
            summarize_paper_trades()
        except Exception as e:
            logging.error(f"Failed to generate trade summary: {e}")
        
        print(f"{'='*70}\n")
        
        # Exit if single run mode
        if not continuous:
            print("Single run completed. Exiting.")
            break
        
        # Sleep until next run
        print(f"Next run in {interval} seconds...")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\nBot stopped by user. Exiting gracefully...")
            logging.info("Bot stopped by user")
            break


# ═══════════════════════════════════════════════════════════════════
# TELEGRAM BOT CONTROL (BACKGROUND THREAD)
# ═══════════════════════════════════════════════════════════════════

def run_telegram_bot() -> None:
    """
    Run Telegram bot in a separate thread for remote control.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID environment variables.
    """
    if not TELEGRAM_TOKEN or not ALLOWED_USER_ID:
        logging.warning("Telegram bot not started: missing environment variables")
        return
    
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes
        
        async def tg_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle /status command"""
            if update.effective_user.id != int(ALLOWED_USER_ID):
                logging.warning(f"Unauthorized Telegram access attempt from {update.effective_user.id}")
                return
            
            try:
                positions = load_json(POSITIONS_FILE, {})
                num_positions = len(positions)
                
                # Calculate total portfolio value
                total_value = 0.0
                for coin, pos in positions.items():
                    try:
                        df = fetch_ohlcv(symbol=coin, limit=1)
                        if df and not df.is_empty():
                            current_price = float(df["close"][0])
                            total_value += pos.get("quantity", 0) * current_price
                    except Exception:
                        pass
                
                msg = (
                    f"Bot Status\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Open Positions: {num_positions}\n"
                    f"Portfolio Value: ${total_value:.2f}\n"
                )
            except Exception as e:
                msg = f"Error fetching status: {e}"
            
            await update.message.reply_text(msg)
        
        async def tg_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle /positions command"""
            if update.effective_user.id != int(ALLOWED_USER_ID):
                logging.warning(f"Unauthorized Telegram access attempt from {update.effective_user.id}")
                return
            
            try:
                positions = load_json(POSITIONS_FILE, {})
                
                if not positions:
                    msg = "No open positions"
                else:
                    msg = "Open Positions:\n\n"
                    for coin, pos in positions.items():
                        msg += (
                            f"{coin}\n"
                            f"  Qty: {pos.get('quantity', 0):.6f}\n"
                            f"  Entry: ${pos.get('entry_price', 0):.2f}\n"
                            f"  SL: ${pos.get('stop_loss', 0):.2f}\n"
                            f"  TP: ${pos.get('take_profit', 0):.2f}\n\n"
                        )
            except Exception as e:
                msg = f"Error fetching positions: {e}"
            
            await update.message.reply_text(msg)
        
        async def tg_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle /help command"""
            if update.effective_user.id != int(ALLOWED_USER_ID):
                logging.warning(f"Unauthorized Telegram access attempt from {update.effective_user.id}")
                return
            
            msg = (
                "Available Commands:\n\n"
                "/status - Show bot status\n"
                "/positions - List open positions\n"
                "/help - Show this message\n"
            )
            await update.message.reply_text(msg)
        
        # Build and run application
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        app.add_handler(CommandHandler("status", tg_status))
        app.add_handler(CommandHandler("positions", tg_positions))
        app.add_handler(CommandHandler("help", tg_help))
        
        logging.info("Telegram bot started successfully")
        print("Telegram bot started (authorized user only)")
        
        app.run_polling(drop_pending_updates=True)
    
    except Exception as e:
        logging.error(f"Telegram bot failed to start: {e}", exc_info=True)
        print(f"Telegram bot failed to start: {e}")


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Enhanced Crypto Trading Bot with Security Features"
    )
    parser.add_argument(
        "--once", 
        action="store_true", 
        help="Run once and exit (default: continuous)"
    )
    parser.add_argument(
        "--interval", 
        type=int, 
        default=300, 
        help="Sleep interval between runs in seconds (default: 300)"
    )
    parser.add_argument(
        "--telegram", 
        action="store_true", 
        help="Start Telegram control bot in background"
    )
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="Skip environment variable validation (not recommended)"
    )
    
    args = parser.parse_args()
    
    # Setup
    setup_directories()
    setup_logging()
    
    logging.info("=" * 70)
    logging.info("ENHANCED CRYPTO TRADING BOT STARTING")
    logging.info("=" * 70)
    
    # Validate environment variables (unless skipped or telegram not requested)
    if args.telegram and not args.skip_env_check:
        if not validate_environment_variables():
            print("\nTelegram bot requires environment variables.")
            print("Set them or use --skip-env-check to continue without Telegram.\n")
            exit(1)
    
    # Start Telegram bot if requested
    if args.telegram:
        telegram_thread = threading.Thread(
            target=run_telegram_bot,
            daemon=True,
            name="TelegramBot"
        )
        telegram_thread.start()
        logging.info("Telegram bot thread started")
    
    # Run main trading loop
    try:
        main(continuous=not args.once, interval=args.interval)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user (Ctrl+C)")
        print("\n\nGraceful shutdown complete.")
    except Exception as e:
        logging.critical(f"Fatal error in main loop: {e}", exc_info=True)
        print(f"\nFATAL ERROR: {e}")
        exit(1)
    finally:
        logging.info("Bot shutdown complete")
