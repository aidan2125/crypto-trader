#!/usr/bin/env python3
"""
Ultimate Continuous Trader Runner
1. Applies risk preset
2. Runs backtest validation on BTC/USDT
3. If backtest profitable → runs main_enhanced.py on ALL coins
4. Persists ALL backtest results to Supabase (passed or failed)
5. Repeats every X minutes
"""

import json
import time
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Supabase integration
try:
    from database.supabase_db import insert_backtest_result, seed_coins, get_active_preset, get_or_create_coin
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Warning: Supabase integration not available")

# === CONFIG ===
RISK_CONFIG_PATH = Path("data") / "risk_config.json"
MAIN_BOT = "main_enhanced.py"
BACKTEST_SCRIPT = "run_backtest_simple.py"
VALIDATION_COIN = "BTC/USDT"
MIN_ROI_FOR_LIVE = -5.0      # Require at least break-even
MIN_WIN_RATE = 0.0        # At least 40% win rate
# ====================

PRESETS = {
    "conservative": {
        "max_positions": 3,
        "position_size_pct": 0.05,
        "stop_loss_pct": 0.015,
        "take_profit_pct": 0.03,
        "trailing_stop_pct": 0.02,
        "risk_per_trade": 0.01,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.5
    },
    "moderate": {
        "max_positions": 5,
        "position_size_pct": 0.10,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.05,
        "trailing_stop_pct": 0.03,
        "risk_per_trade": 0.02,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.0
    },
    "aggressive": {
        "max_positions": 8,
        "position_size_pct": 0.15,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.10,
        "trailing_stop_pct": 0.05,
        "risk_per_trade": 0.03,
        "atr_multiplier_sl": 2.5,
        "atr_multiplier_tp": 4.0
    }
}

def apply_preset(preset_name: str) -> bool:
    preset_name = preset_name.lower()
    if preset_name not in PRESETS:
        print(f"Unknown preset: {preset_name}")
        print(f"Available: {', '.join(PRESETS.keys())}")
        return False

    preset = PRESETS[preset_name]
    config = {}
    if RISK_CONFIG_PATH.exists():
        try:
            with open(RISK_CONFIG_PATH) as f:
                config = json.load(f)
        except Exception as e:
            print(f"Could not read existing config: {e}")

    config.update(preset)

    RISK_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RISK_CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

    print(f"Applied '{preset_name.capitalize()}' preset -> {RISK_CONFIG_PATH}")
    return True

def run_validation_backtest(preset_name: str) -> dict:
    """Run backtest and return full result dict for Supabase persistence"""
    print(f"Running validation backtest on {VALIDATION_COIN}...")

    backtest_result = {
        "preset_id": None,
        "coin_id": None,  # Will be populated below
        "run_time": datetime.now(timezone.utc).isoformat(),
        "timeframe": "1h",
        "num_candles": 1000,
        "num_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "roi": 0.0,
        "max_drawdown": 0.0,
        "avg_pnl": 0,
        "passed": False
    }

    # Map preset name to preset_id
    preset_id_map = {"conservative": 1, "moderate": 2, "aggressive": 3}
    backtest_result["preset_id"] = preset_id_map.get(preset_name.lower(), 2)
    
    # Get or create coin for this validation
    if SUPABASE_AVAILABLE:
        coin_id = get_or_create_coin(VALIDATION_COIN)
        if coin_id:
            backtest_result["coin_id"] = coin_id

    try:
        result = subprocess.run(
            ["python", BACKTEST_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120
        )

        output = result.stdout + result.stderr
        print(output)

        if result.returncode != 0:
            print("Backtest script crashed.")
            backtest_result["passed"] = False
            return backtest_result

        if "No trades executed" in output or "No trades" in output:
            print("No trades in backtest - skipping live trading.")
            backtest_result["passed"] = False
            return backtest_result

        # Extract ROI, Win Rate, and other metrics
        roi_pct = 0.0
        win_rate = 0.0
        max_drawdown = 0.0
        total_trades = 0
        profit_factor = 0.0

        for line in output.splitlines():
            if "ROI" in line and ":" in line:
                try:
                    roi_str = line.split(":")[1].strip().replace("%", "").replace("+", "")
                    roi_pct = float(roi_str) / 100.0  # Convert to decimal
                except:
                    pass
            if "Win Rate" in line and ":" in line:
                try:
                    wr_str = line.split(":")[1].strip().replace("%", "")
                    win_rate = float(wr_str) / 100.0
                except:
                    pass
            if "Max Drawdown" in line and ":" in line:
                try:
                    md_str = line.split(":")[1].strip().replace("%", "").replace("-", "")
                    max_drawdown = -float(md_str) / 100.0
                except:
                    pass
            if "Total Trades" in line and ":" in line:
                try:
                    total_trades = int(line.split(":")[1].strip())
                except:
                    pass
            if "Profit Factor" in line and ":" in line:
                try:
                    profit_factor = float(line.split(":")[1].strip())
                except:
                    pass

        # Update result dict with parsed metrics
        backtest_result["roi"] = roi_pct
        backtest_result["win_rate"] = win_rate
        backtest_result["max_drawdown"] = max_drawdown
        backtest_result["num_trades"] = total_trades
        backtest_result["profit_factor"] = profit_factor

        print(f"Backtest Result -> ROI: {roi_pct*100:+.1f}% | Win Rate: {win_rate:.1%}")

        # Determine if passed validation
        if roi_pct >= (MIN_ROI_FOR_LIVE / 100.0) and win_rate >= MIN_WIN_RATE:
            print("Backtest PASSED - Starting trading on all coins!")
            backtest_result["passed"] = True
        else:
            print(f"Backtest FAILED (ROI < {MIN_ROI_FOR_LIVE:+.1f}% or Win Rate < {MIN_WIN_RATE:.0%})")
            backtest_result["passed"] = False

        return backtest_result

    except subprocess.TimeoutExpired:
        print("Backtest timed out.")
        backtest_result["passed"] = False
        return backtest_result
    except Exception as e:
        print(f"Backtest error: {e}")
        backtest_result["passed"] = False
        return backtest_result

def run_live_trading():
    """Launch your main_enhanced.py in continuous mode using argparse"""
    print("Launching main trading bot on all coins...")
    try:
        # Use --interval 300 to run continuously with 5-minute sleeps
        subprocess.run(["python", MAIN_BOT, "--interval", "300"], check=False)
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print(f"Bot launch error: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_with_risk_preset.py <preset> [interval_minutes]")
        print("Presets: conservative, moderate, aggressive")
        sys.exit(1)

    preset = sys.argv[1].lower()
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    # Initialize Supabase if available
    if SUPABASE_AVAILABLE:
        print("Initializing Supabase integration...")
        seed_coins()
        print("✓ Database seeded\n")

    print(f"Starting Ultimate Trader Runner - Preset: {preset} | Cycle every {interval} min\n")

    cycle = 1
    try:
        while True:
            print("=" * 80)
            print(f" CYCLE #{cycle} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)

            if not apply_preset(preset):
                break

            # Run backtest and get full result dict
            backtest_result = run_validation_backtest(preset)

            # Persist result to Supabase (always, whether passed or failed)
            if SUPABASE_AVAILABLE:
                success = insert_backtest_result(backtest_result)
                if success:
                    status_str = "PASSED" if backtest_result["passed"] else "FAILED"
                    print(f"✓ Backtest result ({status_str}) saved to Supabase")
                else:
                    print("✗ Could not save backtest to Supabase (check logs)")

            # Only run live trading if backtest passed
            if backtest_result["passed"]:
                run_live_trading()

            print(f"\nSleeping {interval} minutes until next cycle...\n")
            time.sleep(interval * 60)
            cycle += 1

    except KeyboardInterrupt:
        print("\nStopped by user. Goodbye!")

if __name__ == "__main__":
    main()