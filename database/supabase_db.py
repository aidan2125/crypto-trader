# database/supabase_db.py

import os
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime
import logging

# Load .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✓ Supabase client initialized successfully")
    except Exception as e:
        print(f"✗ Failed to create Supabase client: {e}")
        supabase = None
else:
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    print(f"✗ Supabase not configured: Missing env vars: {', '.join(missing)}")
    supabase = None


def insert_backtest_result(backtest_data: dict) -> bool:
    """Insert backtest result into Supabase. Returns True on success."""
    if supabase is None:
        logging.warning("Supabase not configured; cannot insert backtest result")
        print("✗ Supabase client not available – check .env file")
        return False

    try:
        # Ensure required fields
        if "run_time" not in backtest_data:
            backtest_data["run_time"] = datetime.utcnow().isoformat()

        print(f"[Supabase] Inserting backtest result: ROI {backtest_data.get('roi', 0)*100:+.1f}%, "
              f"Win Rate {backtest_data.get('win_rate', 0)*100:.1f}%")

        response = supabase.table("backtests").insert(backtest_data).execute()

        if response.data:
            print("✓ Backtest result saved to Supabase")
            return True
        else:
            print("✗ Supabase insert returned no data (possible RLS issue)")
            print("Response:", response)
            return False

    except Exception as e:
        print(f"✗ Supabase insert failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_or_create_coin(symbol: str) -> int | None:
    if supabase is None:
        return None
    try:
        # Try to find existing coin
        resp = supabase.table("coins").select("id").eq("symbol", symbol).execute()
        if resp.data:
            return resp.data[0]["id"]

        # Insert new coin
        insert_resp = supabase.table("coins").insert({"symbol": symbol}).execute()
        if insert_resp.data:
            return insert_resp.data[0]["id"]
    except Exception as e:
        print(f"Error with coin {symbol}: {e}")
    return None


def seed_coins():
    """Optional: pre-seed common coins"""
    common_coins = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    for coin in common_coins:
        get_or_create_coin(coin)


def get_active_preset():
    if supabase is None:
        return None
    try:
        resp = supabase.table("presets").select("*").eq("is_active", True).single().execute()
        return resp.data
    except:
        return None