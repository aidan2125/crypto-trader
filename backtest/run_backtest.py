# backtest/run_backtest.py

from data.market_data import fetch_ohlcv
from strategies.enhanced_signals import enhanced_strategy
from backtest.backtest import BacktestPro
import pandas as pd

def main():
    symbol = "BTC/USDT"
    timeframe = "1h"
    limit = 2000

    print("Fetching data...")
    df = fetch_ohlcv(symbol, timeframe, limit)
    if df is None or df.empty:
        print("No data fetched.")
        return

    print("Applying strategy...")
    df = enhanced_strategy(df)

    print("Running backtest...")
    bt = BacktestPro(initial_balance=10000, risk_per_trade=0.01)
    bt.run_with_data(df, symbol=symbol, strategy_name="Enhanced Strategy")

if __name__ == "__main__":
    main()