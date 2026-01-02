"""
Enhanced Main Bot with Risk Management and Discord Alerts
Integrates: signals, risk management, alerts, paper trading
"""

# At the very top of your main bot script, BEFORE other imports
import subprocess
import sys

# Check dependencies first
try:
    from check_dependencies import ensure_dependencies
    
    required_packages = [
        "numpy",
        "pandas",
        "ccxt",
        "matplotlib",
        "requests"
    ]
    
    ensure_dependencies(required_packages)
except ImportError:
    # If check_dependencies doesn't exist, create inline check
    def check_pkg(pkg):
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            print(f"Installed {pkg}. Please restart the script.")
            sys.exit(0)
    
    for pkg in ["numpy", "pandas"]:
        check_pkg(pkg)
   
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
from execution.enhanced_paper_trader import (
    execute_paper_trade,
    summarize_paper_trades,
    check_exit_conditions,
    update_peak_price
)
from risk.dynamic_risk import load_risk_config



# Ensure directories exist
os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# Logging
logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DEFAULT_CURRENCY = "USD"



def send_all_alerts(message, coin=""):
    """
    Send alerts to all configured channels.
    
    Args:
        message: Alert message to send
        coin: Coin symbol (for subject line)
        
    Returns:
        dict: Status of each alert service
    """
    results = {
        "telegram": False,
        "email": False,
        "discord": False
    }
    
    # Discord Alert
    try:
        results["discord"] = send_discord_message(message)
        if results["discord"]:
            logging.info(f"Discord alert sent for {coin}")
    except Exception as e:
        logging.error(f"Discord alert failed for {coin}: {e}")
    
    # Telegram Alert
    try:
        send_telegram_message(message)
        results["telegram"] = True
        logging.info(f"Telegram alert sent for {coin}")
    except Exception as e:
        logging.error(f"Telegram alert failed for {coin}: {e}")
    
    # Email Alert
    try:
        subject = f"{coin} Trading Alert" if coin else "Trading Alert"
        send_email(subject=subject, body=message)
        results["email"] = True
        logging.info(f"Email alert sent for {coin}")
    except Exception as e:
        logging.error(f"Email alert failed for {coin}: {e}")
    
    return results

def check_position_risk_exits(coin, current_price):
    """
    Check if any open positions need to be closed due to risk rules.
    Returns trade result if exit executed, None otherwise.
    """
    should_exit, reason, pnl_pct = check_exit_conditions(coin, current_price)
    
    if should_exit:
        logging.info(f"{coin}: Risk exit triggered - {reason} at ${current_price:.2f}")
        
        # Execute risk-based exit
        result = execute_paper_trade(
            coin=coin,
            signal=-1,  # Force sell
            price=current_price,
            currency=COIN_CURRENCY.get(coin, DEFAULT_CURRENCY),
            override_risk=True
        )
        
        return result, reason
    
    return None, None

def run_for_coin(coin):
    """
    Enhanced pipeline with risk management for a single coin.
    """
    try:
        currency = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)

        # Step 1: Fetch OHLCV data
        df = fetch_ohlcv(symbol=coin)
        
        if df is None or df.empty:
            logging.warning(f"{coin}: No data fetched")
            return

        # Step 2: Calculate indicators/signals
        df = enhanced_strategy(df)
        
        if "signal" not in df.columns or df.empty:
            logging.warning(f"{coin}: No signal column in dataframe")
            return

        # Step 3: Plot signals chart
        try:
            plot_signals(df, filename=f"reports/{coin.replace('/', '_')}_signals.png")
        except Exception as e:
            logging.error(f"{coin}: Plot failed: {e}")

        # Step 4: Get current signal and price
        current_signal = int(df["signal"].iloc[-1])
        price = float(df["close"].iloc[-1])
        
        # Validate signal
        if current_signal not in [-1, 0, 1]:
            logging.warning(f"{coin}: Invalid signal value: {current_signal}")
            return

        # Step 5: Check for risk-based exits FIRST (before signal logic)
        risk_exit_result, exit_reason = check_position_risk_exits(coin, price)
        
        if risk_exit_result:
            # Position was closed due to risk management
            message = (
                f"🚨 **RISK EXIT** 🚨\n"
                f"Coin: {coin}\n"
                f"Reason: {exit_reason}\n"
                f"Price: ${price:.2f}\n"
                f"\n{risk_exit_result}"
            )
            
            alert_results = send_all_alerts(message, coin)
            
            logging.info(f"{coin}: Risk exit - Alerts sent (Discord: {alert_results['discord']})")
            print(f"\n{message}\n")
            return

        # Step 6: Update peak price for trailing stop (if holding)
        update_peak_price(coin, price)

        # Step 7: Load last signals and check for changes
        last_signals = load_last_signals()
        previous_signal = last_signals.get(coin)

        # Step 8: Only execute trade on signal change
        if current_signal != previous_signal:
            # Execute paper trade on signal change
            trade_result = execute_paper_trade(
                coin=coin,
                signal=current_signal,
                price=price,
                currency=currency
            )

            # Prepare alert message
            signal_names = {-1: "🔴 SELL", 0: "⚪ HOLD", 1: "🟢 BUY"}
            signal_name = signal_names.get(current_signal, str(current_signal))
            
            # Create formatted message
            message = (
                f"📊 **SIGNAL CHANGE** 📊\n"
                f"Coin: {coin}\n"
                f"Signal: {signal_name}\n"
                f"Price: ${price:.2f} {currency}\n"
                f"Previous: {signal_names.get(previous_signal, 'None')}\n"
                f"\n**Trade Result:**\n{trade_result}"
            )
            
            # Send alerts to all channels
            alert_results = send_all_alerts(message, coin)

            # Update last signals
            last_signals[coin] = current_signal
            save_last_signals(last_signals)

            # Log results
            alerts_sent = ", ".join([k for k, v in alert_results.items() if v])
            logging.info(f"{coin}: Signal changed from {previous_signal} to {current_signal} - Alerts: {alerts_sent}")
            print(f"\n{message}")
            print(f"Alerts sent: {alerts_sent}\n")
        else:
            # No signal change, but log current state
            logging.info(f"{coin}: No signal change (current: {current_signal}, price: ${price:.2f})")

    except Exception as e:
        error_msg = f"{coin}: Pipeline failure: {str(e)}"
        logging.error(error_msg)
        print(f"ERROR: {error_msg}")

def main(continuous=False, interval=60):
    """
    Enhanced main loop with risk management.
    
    Args:
        continuous: If True, runs continuously
        interval: Seconds between runs (if continuous)
    """
    run_count = 0
    
    while True:
        run_count += 1
        print(f"\n{'='*60}")
        print(f"Bot Run #{run_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(60))
        print(f"{'='*60}\n")
        
        config = load_risk_config()
        print(f"Risk Config: {config['max_positions']} max positions, "
              f"{config['position_size_pct']*100}% position size, "
              f"{config['stop_loss_pct']*100}% stop loss")
        print()
        
        # Process all coins
        for coin in COIN_CURRENCY.keys():
            print(f"Processing {coin}...")
            run_for_coin(coin)
            time.sleep(1)  # Small delay between coins to avoid API rate limits

        # Show summary
        print(f"\n{'='*60}")
        summarize_paper_trades()
        
        if not continuous:
            break
        
        print(f"Waiting {interval} seconds until next run...")
        print(f"{'='*60}\n")
        time.sleep(interval)

def simulate_live_trading(duration_minutes=60, check_interval=60):
    """
    Simulate live trading for a specified duration.
    Checks market every interval and executes trades.
    
    Args:
        duration_minutes: How long to run simulation
        check_interval: Seconds between market checks
    """
    print(f"\n{'='*60}")
    print(f"LIVE TRADING SIMULATION".center(60))
    print(f"{'='*60}")
    print(f"\nDuration: {duration_minutes} minutes")
    print(f"Check Interval: {check_interval} seconds")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nPress Ctrl+C to stop early\n")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    try:
        while time.time() < end_time:
            remaining = int((end_time - time.time()) / 60)
            print(f"\n--- Market Check (Time Remaining: {remaining} minutes) ---\n")
            
            main(continuous=False)
            
            if time.time() < end_time:
                time.sleep(check_interval)
    
    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user")
    
    print(f"\n{'='*60}")
    print("SIMULATION COMPLETE".center(60))
    print(f"{'='*60}\n")
    
    summarize_paper_trades()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "continuous":
            # Run continuously
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            print(f"Starting continuous mode (checking every {interval} seconds)")
            main(continuous=True, interval=interval)
        
        elif sys.argv[1] == "simulate":
            # Run live simulation
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            interval = int(sys.argv[3]) if len(sys.argv) > 3 else 60
            simulate_live_trading(duration_minutes=duration, check_interval=interval)
        
        elif sys.argv[1] == "test":
            # Test mode - just one run with verbose output
            print("Running in TEST mode (single run)")
            main(continuous=False)
    else:
        # Single run
        main(continuous=False)
