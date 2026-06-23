

import os
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime
import logging

# Load .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# SUPABASE REMOVED — bot now uses SQLite via database/trade_logger.py
# Kept as no-op stub so old imports don't crash at runtime.
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
    """Get coin ID or create if doesn't exist"""
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
    """Pre-seed common coins"""
    if supabase is None:
        print("✗ Cannot seed coins - Supabase not configured")
        return
    
    common_coins = ["BTC/USDT", "ETH/USDT", "LTC/USDT", "XRP/USDT", "ADA/USDT", "DOT/USDT"]
    for coin in common_coins:
        coin_id = get_or_create_coin(coin)
        if coin_id:
            print(f"✓ Coin {coin} ready (ID: {coin_id})")


def get_active_preset(preset_name: str = "moderate") -> dict | None:
    """
    Fetch the active risk preset from Supabase
    Falls back to default if not found
    """
    if supabase is None:
        print("✗ Supabase not available - using default preset")
        return get_default_preset()
    
    try:
        response = supabase.table("risk_presets")\
            .select("*")\
            .eq("preset_name", preset_name)\
            .single()\
            .execute()
        
        if response.data:
            print(f"✓ Loaded '{preset_name}' preset from Supabase")
            return response.data
        else:
            print(f"✗ Preset '{preset_name}' not found in Supabase - using default")
            return get_default_preset()
    except Exception as e:
        print(f"✗ Error fetching preset: {e} - using default")
        return get_default_preset()


def get_default_preset() -> dict:
    """Fallback preset if Supabase unavailable"""
    return {
        "preset_name": "moderate",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "risk_per_trade": 0.02,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.0,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.05,
        "trailing_stop_pct": 0.03,
        "max_loss_per_trade_pct": 0.02,
        "min_signal_quality": 60
    }


def log_trade(trade_data: dict) -> bool:
    """Log a trade to Supabase"""
    if supabase is None:
        return False
    
    try:
        response = supabase.table("trades").insert(trade_data).execute()
        if response.data:
            print(f"✓ Trade logged to Supabase: {trade_data.get('coin', 'Unknown')}")
            return True
        return False
    except Exception as e:
        print(f"✗ Failed to log trade: {e}")
        return False


def seed_risk_presets():
    """Seed default risk presets into Supabase"""
    if supabase is None:
        print("✗ Cannot seed presets - Supabase not configured")
        return
    
    presets = [
        {
            "preset_name": "conservative",
            "max_positions": 3,
            "position_size_pct": 0.05,
            "risk_per_trade": 0.01,
            "atr_multiplier_sl": 2.5,
            "atr_multiplier_tp": 4.0,
            "stop_loss_pct": 0.015,
            "take_profit_pct": 0.04,
            "trailing_stop_pct": 0.025,
            "max_loss_per_trade_pct": 0.01,
            "min_signal_quality": 70
        },
        {
            "preset_name": "moderate",
            "max_positions": 5,
            "position_size_pct": 0.10,
            "risk_per_trade": 0.02,
            "atr_multiplier_sl": 2.0,
            "atr_multiplier_tp": 3.0,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.03,
            "max_loss_per_trade_pct": 0.02,
            "min_signal_quality": 60
        },
        {
            "preset_name": "aggressive",
            "max_positions": 8,
            "position_size_pct": 0.15,
            "risk_per_trade": 0.03,
            "atr_multiplier_sl": 1.5,
            "atr_multiplier_tp": 2.5,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.07,
            "trailing_stop_pct": 0.04,
            "max_loss_per_trade_pct": 0.03,
            "min_signal_quality": 50
        }
    ]
    
    for preset in presets:
        try:
            # Check if exists
            existing = supabase.table("risk_presets")\
                .select("id")\
                .eq("preset_name", preset["preset_name"])\
                .execute()
            
            if existing.data:
                print(f"✓ Preset '{preset['preset_name']}' already exists")
            else:
                # Insert new
                supabase.table("risk_presets").insert(preset).execute()
                print(f"✓ Created preset '{preset['preset_name']}'")
        except Exception as e:
            print(f"✗ Error seeding preset '{preset['preset_name']}': {e}")


# Initialize database on import
if supabase:
    print("Initializing Supabase integration...")
    seed_coins()
    seed_risk_presets()
    print("✓ Database seeded")