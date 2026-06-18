#!/usr/bin/env python3
"""
Debug Supabase backtest insert with verbose logging
"""

import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print(f"URL: {url}")
print(f"Key: {key[:20]}..." if key else "Key: None")
print()

if not url or not key:
    print("ERROR: Credentials missing")
    exit(1)

try:
    from supabase import create_client
    supabase = create_client(url, key)
    print("✓ Supabase client created\n")
except Exception as e:
    print(f"✗ Client creation failed: {e}")
    exit(1)

# Test backtest insert
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

print("=" * 60)
print("Inserting test data into 'backtests' table:")
print(f"Data: {test_data}\n")

try:
    response = supabase.table("backtests").insert(test_data).execute()
    print(f"Response type: {type(response)}")
    print(f"Response: {response}")
    
    if isinstance(response, dict):
        data = response.get("data")
        error = response.get("error")
    else:
        data = getattr(response, "data", None)
        error = getattr(response, "error", None)
    
    print(f"\nData: {data}")
    print(f"Error: {error}")
    
    if data:
        print("\n✓ INSERT SUCCEEDED!")
        print(f"Inserted row: {data}")
    else:
        print("\n✗ INSERT FAILED")
        
except Exception as e:
    print(f"\n✗ EXCEPTION: {e}")
    import traceback
    traceback.print_exc()
