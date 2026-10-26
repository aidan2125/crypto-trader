#!/usr/bin/env python3
"""Test backtest insert with coins seeded"""

from datetime import datetime, timezone
from database.supabase_db import seed_coins, insert_backtest_result

if __name__ == "__main__":
    print("Step 1: Seeding coins table...")
    seed_result = seed_coins()
    print(f"Seed result: {seed_result}\n")
    
    print("Step 2: Inserting backtest result...")
    test_data = {
        "preset_id": 2,
        "coin_id": 1,  # Now should work if coin exists
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
    
    result = insert_backtest_result(test_data)
    
    if result:
        print("✓ Backtest result inserted successfully!")
    else:
        print("✗ Insert failed (check logs)")
