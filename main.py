import logging
from data.market_data import fetch_ohlcv
from strategies.signals import moving_average_signal
from reports.plot_signals import plot_signals
from data.multi_coin_list import COIN_CURRENCY
from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email
from alerts.discord_alerts import send_discord_message
from data.last_signal_store import load_last_signals, save_last_signals
from execution.paper_trader import execute_paper_trade

# Setup logging
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
    fetch data → calculate signals → plot chart → alerts → paper trade
    """
    try:
        # Determine currency for this coin
        currency = COIN_CURRENCY.get(coin, DEFAULT_CURRENCY)

        # Step 1: Fetch OHLCV data
        df = fetch_ohlcv(symbol=coin)

        # Step 2: Calculate indicators/signals
        df = moving_average_signal(df)

        # Step 3: Plot signals chart
        plot_signals(df, filename=f"reports/{coin.replace('/', '_')}_signals.png")

        # Step 4: Load last signals and check for changes
        last_signals = load_last_signals()
        current_signal = int(df["signal"].iloc[-1])
        previous_signal = last_signals.get(coin)

        # Step 5: Execute paper trade
        price = float(df["close"].iloc[-1])
        trade_result = execute_paper_trade(
            coin=coin,
            signal=current_signal,
            price=price,
            currency=currency,
            trade_size=trade_size
        )

        # Step 6: Send alerts if signal changed
        if current_signal != previous_signal:
            message = f"{coin} NEW SIGNAL: {current_signal} ({currency})"

            send_telegram_message(message)
            send_email(subject=f"{coin} Signal", body=message)
            send_discord_message(message)

            # Update last signals
            last_signals[coin] = current_signal
            save_last_signals(last_signals)

            logging.info("%s: Signal changed to %s (%s)", coin, current_signal, currency)
            print(message)
        else:
            logging.info("%s: No signal change (%s)", coin, current_signal)

        # Step 7: Log paper trade result if any
        if trade_result:
            print(trade_result)
            logging.info(trade_result)

    except Exception as e:
        logging.error("%s: Pipeline failure: %s", coin, e)


def main():
    """
    Runs the pipeline for all coins.
    """
    for coin in COIN_CURRENCY.keys():
        run_for_coin(coin, trade_size=DEFAULT_TRADE_SIZE)


if __name__ == "__main__":
    main()
