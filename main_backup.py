import logging
import os
from data.multi_coin_list import COIN_CURRENCY
from data.market_data import fetch_ohlcv
from strategies.signals import moving_average_signal
from reports.plot_signals import plot_signals
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message
from data.last_signal_store import load_last_signals, save_last_signals
from execution.paper_trader import execute_paper_trade, summarize_paper_trades

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
DEFAULT_TRADE_SIZE = 100

def run_for_coin(coin, trade_size=DEFAULT_TRADE_SIZE):
    """
    Runs the full pipeline for a single coin:
    fetch data → calculate signals → plot chart → check for signal change → alerts → paper trade
    """
    try:
        currency = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)

        # Step 1: Fetch OHLCV data
        df = fetch_ohlcv(symbol=coin)
        
        if df is None or df.empty:
            logging.warning("%s: No data fetched", coin)
            return

        # Step 2: Calculate indicators/signals
        df = moving_average_signal(df)
        
        if "signal" not in df.columns or df.empty:
            logging.warning("%s: No signal column in dataframe", coin)
            return

        # Step 3: Plot signals chart
        plot_signals(df, filename=f"reports/{coin.replace('/', '_')}_signals.png")

        # Step 4: Get current signal and price
        current_signal = int(df["signal"].iloc[-1])
        price = float(df["close"].iloc[-1])
        
        # Validate signal
        if current_signal not in [-1, 0, 1]:
            logging.warning("%s: Invalid signal value: %s", coin, current_signal)
            return

        # Step 5: Load last signals and check for changes
        last_signals = load_last_signals()
        previous_signal = last_signals.get(coin)

        # Step 6: Only execute trade and send alerts if signal changed
        if current_signal != previous_signal:
            # Execute paper trade on signal change
            trade_result = execute_paper_trade(
                coin=coin,
                signal=current_signal,
                price=price,
                currency=currency,
                trade_size=trade_size
            )

            # Prepare alert message
            signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}
            signal_name = signal_names.get(current_signal, str(current_signal))
            message = f"{coin} NEW SIGNAL: {signal_name} @ {price:.2f} {currency}"
            
            if trade_result:
                message += f"\n{trade_result}"

            # Send alerts
            try:
                send_telegram_message(message)
            except Exception as e:
                logging.error("%s: Telegram alert failed: %s", coin, e)
            
            try:
                send_email(subject=f"{coin} Signal Change", body=message)
            except Exception as e:
                logging.error("%s: Email alert failed: %s", coin, e)
            
            try:
                send_discord_message(message)
            except Exception as e:
                logging.error("%s: Discord alert failed: %s", coin, e)

            # Update last signals
            last_signals[coin] = current_signal
            save_last_signals(last_signals)

            logging.info("%s: Signal changed from %s to %s (%s)", 
                        coin, previous_signal, current_signal, currency)
            print(message)
            
            if trade_result:
                logging.info(trade_result)
        else:
            logging.info("%s: No signal change (current: %s)", coin, current_signal)

    except Exception as e:
        error_msg = f"{coin}: Pipeline failure: {str(e)}"
        logging.error(error_msg)
        print(f"ERROR: {error_msg}")

# ------------------- Main loop -------------------

def main():
    """
    Runs the pipeline for all coins.
    """
    print(f"\n{'='*50}")
    print(f"Starting crypto trading bot for {len(COIN_CURRENCY)} coins")
    print(f"{'='*50}\n")
    
    for coin in COIN_CURRENCY.keys():
        print(f"Processing {coin}...")
        run_for_coin(coin, trade_size=DEFAULT_TRADE_SIZE)

    print(f"\n{'='*50}")
    # Show human-readable summary at the end
    summarize_paper_trades()
    print(f"Bot run completed")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()