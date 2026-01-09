"""
Enhanced Crypto Trading Bot
Dynamic ATR-based Risk Management + Multi-Channel Alerts
"""

import logging
import os
import time
import json
import argparse
from datetime import datetime

from data.multi_coin_list import COIN_CURRENCY
from data.market_data import fetch_ohlcv
from strategies.enhanced_signals import enhanced_strategy
from reports.plot_signals import plot_signals
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message
from data.last_signal_store import load_last_signals, save_last_signals
from execution.enhanced_paper_trader import execute_paper_trade, summarize_paper_trades

# New: load active preset from Supabase (optional)
from database.supabase_db import get_active_preset

# CORRECT IMPORT — file is risk/dynamic_risk.py
from risk.dynamic_risk import load_enhanced_risk_config as load_config

# Ensure directories
os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# Logging
logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DEFAULT_CURRENCY = "USD"


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


def run_for_coin(coin: str):
    try:
        currency = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)
        df = fetch_ohlcv(symbol=coin)
        if df is None or df.empty:
            logging.warning(f"{coin}: No data")
            return

        df = enhanced_strategy(df)
        if "signal" not in df.columns:
            logging.warning(f"{coin}: No signal generated")
            return

        # Plot
        try:
            plot_signals(df, filename=f"{coin.replace('/', '_')}_signals.png")
        except Exception as e:
            logging.error(f"{coin}: Plot error: {e}")

        current_signal = int(df["signal"].iloc[-1])
        price = float(df["close"].iloc[-1])
        
        # FIXED: Extract ATR from strategy output
        atr = None
        if "atr" in df.columns and not df["atr"].isna().iloc[-1]:
            atr = float(df["atr"].iloc[-1])
        
        # Get signal quality if available
        signal_quality = None
        if "signal_quality" in df.columns and not df["signal_quality"].isna().iloc[-1]:
            signal_quality = float(df["signal_quality"].iloc[-1])

        if current_signal not in [-1, 0, 1]:
            logging.warning(f"{coin}: Invalid signal {current_signal}")
            return

        last_signals = load_last_signals()
        previous_signal = last_signals.get(coin)

        if current_signal != previous_signal:
            # FIXED: Pass ATR to paper trader
            trade_result = execute_paper_trade(
                coin=coin,
                signal=current_signal,
                price=price,
                currency=currency,
                atr=atr  # Now includes ATR for dynamic SL/TP
            )

            signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}
            signal_name = signal_names.get(current_signal, str(current_signal))

            # Enhanced message with ATR and quality info
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

            alert_results = send_all_alerts(message, coin)
            alerts_sent = ", ".join(k for k, v in alert_results.items() if v)

            last_signals[coin] = current_signal
            save_last_signals(last_signals)

            log_msg = f"{coin}: {previous_signal} → {current_signal}"
            if signal_quality:
                log_msg += f" | Quality: {signal_quality:.0f}"
            log_msg += f" | Alerts: {alerts_sent}"
            
            logging.info(log_msg)
            print(f"\n{message}\nAlerts: {alerts_sent}\n")
        else:
            logging.info(f"{coin}: No change (signal {current_signal})")

    except Exception as e:
        logging.error(f"{coin} error: {e}")
        print(f"ERROR {coin}: {e}")


def check_all_positions_for_exits():
    """
    Check all open positions for stop loss or take profit hits.
    This runs independently of signal changes for better risk management.
    """
    try:
        from execution.enhanced_paper_trader import load_json, POSITIONS_FILE
        
        positions = load_json(POSITIONS_FILE, {})
        
        if not positions:
            return
        
        for coin, position in list(positions.items()):
            try:
                # Fetch current price
                df = fetch_ohlcv(symbol=coin, limit=1)
                if df is None or df.empty:
                    continue
                
                current_price = float(df["close"].iloc[-1])
                sl = position.get("stop_loss")
                tp = position.get("take_profit")
                entry = position.get("entry_price")
                currency = position.get("currency", DEFAULT_CURRENCY)
                
                # Check for SL/TP hits
                if sl and current_price <= sl:
                    logging.info(f"{coin}: Stop Loss hit at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Stop Loss hit!")
                    execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    
                elif tp and current_price >= tp:
                    logging.info(f"{coin}: Take Profit hit at ${current_price:.2f}")
                    print(f"\n[AUTO EXIT] {coin} Take Profit hit!")
                    execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    
            except Exception as e:
                logging.error(f"Error checking position {coin}: {e}")
                
    except Exception as e:
        logging.error(f"Error in check_all_positions_for_exits: {e}")


def main(continuous: bool = False, interval: int = 300):
    run_count = 0

    # Prefer active preset from Supabase if available, fall back to local config
    try:
        supabase_config = get_active_preset("moderate")
    except Exception:
        supabase_config = None

    if supabase_config:
        config = supabase_config
        print("Risk Config from Supabase:")
        print(f"  Max Positions: {config['max_positions']}")
        print(f"  Risk/Trade: {config['risk_per_trade']*100:.1f}%")
        print(f"  ATR SL/TP: {config['atr_multiplier_sl']}x / {config['atr_multiplier_tp']}x")
    else:
        config = load_config()

    while True:
        run_count += 1
        print(f"\n{'='*70}")
        print(f"RUN #{run_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(70))
        print(f"{'='*70}\n")

        print("Risk Config:")
        print(f"  Max Positions: {config.get('max_positions', 5)}")
        print(f"  Max Risk/Trade: {config.get('max_loss_per_trade_pct', 0.02)*100:.1f}%")
        print(f"  ATR SL: {config.get('atr_multiplier_sl', 2.0)}× | TP: {config.get('atr_multiplier_tp', 3.0)}×\n")

        # Process each coin for signals
        for coin in COIN_CURRENCY:
            print(f"→ {coin}")
            run_for_coin(coin)
            time.sleep(1)

        # FIXED: Check all open positions for SL/TP exits
        print("\n→ Checking open positions for exits...")
        check_all_positions_for_exits()

        print(f"\n{'='*70}")
        summarize_paper_trades()
        print(f"{'='*70}\n")

        if not continuous:
            break

        print(f"Next run in {interval} seconds...")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=300, help="Sleep interval in seconds")
    args = parser.parse_args()

    main(continuous=not args.once, interval=args.interval)