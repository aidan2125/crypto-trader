"""
Enhanced Crypto Trading Bot
Dynamic ATR-based Risk Management + Multi-Channel Alerts
"""

import logging
import os
import time
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

# CORRECT IMPORT — file is risk/dynamic_risk.py
from risk.dynamic_risk import (
    load_enhanced_risk_config as load_config,
    save_enhanced_risk_config as save_config,
    ENHANCED_RISK_CONFIG
)

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

        if current_signal not in [-1, 0, 1]:
            logging.warning(f"{coin}: Invalid signal {current_signal}")
            return

        last_signals = load_last_signals()
        previous_signal = last_signals.get(coin)

        if current_signal != previous_signal:
            trade_result = execute_paper_trade(
                coin=coin,
                signal=current_signal,
                price=price,
                currency=currency
            )

            signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}
            signal_name = signal_names.get(current_signal, str(current_signal))

            message = (
                f"**SIGNAL CHANGE**\n"
                f"Coin: {coin}\n"
                f"Signal: {signal_name}\n"
                f"Price: ${price:.2f} {currency}\n"
                f"Previous: {signal_names.get(previous_signal, 'None')}\n"
                f"\nTrade: {trade_result or 'No action'}"
            )

            alert_results = send_all_alerts(message, coin)
            alerts_sent = ", ".join(k for k, v in alert_results.items() if v)

            last_signals[coin] = current_signal
            save_last_signals(last_signals)

            logging.info(f"{coin}: {previous_signal} → {current_signal} | Alerts: {alerts_sent}")
            print(f"\n{message}\nAlerts: {alerts_sent}\n")
        else:
            logging.info(f"{coin}: No change (signal {current_signal})")

    except Exception as e:
        logging.error(f"{coin} error: {e}")
        print(f"ERROR {coin}: {e}")


def main(continuous: bool = False, interval: int = 300):
    run_count = 0
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

        for coin in COIN_CURRENCY:
            print(f"→ {coin}")
            run_for_coin(coin)
            time.sleep(1)

        print(f"\n{'='*70}")
        summarize_paper_trades()
        print(f"{'='*70}\n")

        if not continuous:
            break

        print(f"Next run in {interval} seconds...")
        time.sleep(interval)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        main(continuous=True, interval=interval)
    else:
        main()