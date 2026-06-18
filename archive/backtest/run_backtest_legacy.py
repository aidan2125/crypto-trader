# backtest/run_backtest.py

from data.market_data import fetch_ohlcv
from strategies.enhanced_signals import enhanced_strategy
from backtest.backtest import BacktestPro
from database.supabase_db import insert_backtest_result, seed_coins
import pandas as pd
from datetime import datetime, timezone

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

    # On first run, seed the coins table
    seed_coins()

    # Then insert backtests
    backtest_data = {
        "preset_id": 2,
        "coin_id": 1,  # Or NULL if coin doesn't exist
        "run_time": datetime.now(timezone.utc).isoformat(),
        "num_trades": 31,
        "win_rate": 0.387,
        "roi": -0.052,
        "max_drawdown": -0.107,
        "avg_pnl": -17,
        "passed": False
    }

    insert_backtest_result(backtest_data)

if __name__ == "__main__":
    main()