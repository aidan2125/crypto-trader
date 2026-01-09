#!/usr/bin/env python3
"""
Quick test for insert_backtest_result()
"""

from datetime import datetime, timezone
from database.supabase_db import insert_backtest_result

if __name__ == "__main__":
    test_data = {
        "preset_id": 2,
        "coin_id": 1,
        "run_time": datetime.now(timezone.utc).isoformat(),
        "timeframe": "1h",
        "num_candles": 1000,
        "num_trades": 31,
        "win_rate": 0.387,
        "profit_factor": 0.77,
        "roi": -0.052,
        "max_drawdown": -0.107,
        "avg_pnl": -17,
        "passed": False
    }
    
    print("Testing insert_backtest_result()...")
    print(f"Data: {test_data}\n")
    
    result = insert_backtest_result(test_data)
    
    if result:
        print("✓ Insert succeeded!")
    else:
        print("✗ Insert failed (check logs)")
