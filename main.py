import logging
from data.market_data import fetch_ohlcv
from strategies.signals import moving_average_signal
from reports.plot_signals import plot_signals
from data.multi_coin_list import COINS
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message

# Setup logging
logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def run_for_coin(coin):
    """
    Runs the full pipeline for a single coin.
    """
    try:
        # Step 1: Fetch data for this coin
        df = fetch_ohlcv(symbol=coin)

        # Step 2: Calculate indicators and signals
        df = moving_average_signal(df)

        # Step 3: Plot chart and save to reports folder with coin-specific filename
        plot_signals(df, filename=f"reports/{coin.replace('/', '_')}_signals.png")

        # Step 4: Log and print last few rows for verification
        logging.info("%s: Last signal: %s", coin, df["signal"].iloc[-1])
        print(f"{coin} last 5 rows:")
        print(df[["timestamp", "close", "sma_20", "ema_20", "rsi", "signal"]].tail())

        last_signal = df["signal"].iloc[-1]
        message = f"{coin} last signal: {last_signal}"

        send_telegram_message(message=message)
        send_email(subject=f"{coin} signal", body=message)
        send_discord_message(message=message)


    except Exception as e:
        logging.error("%s: Error in pipeline: %s", coin, e)

def main():
    """
    Loops through all coins and runs the pipeline for each.
    """
    for coin in COINS:
        run_for_coin(coin)

if __name__ == "__main__":
    main()
