#!/usr/bin/env python3
"""
Strategy Comparison Script
--------------------------
Compares the old persistent-signal strategy with the new event-based strategy
to demonstrate the improvements in signal generation and trade frequency.
"""

# ── Path bootstrap (must come before any project imports) ──────────────────
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
# ───────────────────────────────────────────────────────────────────────────

import polars as pl

from strategies.enhanced_signals import enhanced_strategy as old_strategy
from strategies.enhanced_signals_refactored import enhanced_strategy as new_strategy
from data.market_data import fetch_ohlcv


def compare_strategies(symbol="BTC/USDT", timeframe="1h", limit=3000):
    """
    Compare old vs new strategy on the same data
    """
    print("\n" + "="*80)
    print(f" STRATEGY COMPARISON: {symbol} {timeframe}")
    print("="*80 + "\n")

    # Fetch data
    print(f"Fetching {limit} candles of {symbol} {timeframe} data...")
    df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

    if df is None or df.is_empty():
        print(" Failed to fetch data")
        return

    print(f" Fetched {df.height} candles\n")

    # ========================================================================
    # OLD STRATEGY
    # ========================================================================
    print("─" * 80)
    print(" OLD STRATEGY (Persistent Signal State)")
    print("─" * 80)

    df_old = old_strategy(df.clone())

    old_buy_signals = df_old.filter(pl.col("signal") == 1).height
    old_sell_signals = df_old.filter(pl.col("signal") == -1).height
    old_hold_signals = df_old.filter(pl.col("signal") == 0).height

    old_signal_series = df_old["signal"].to_list()
    old_signal_changes = sum(
        1 for i in range(1, len(old_signal_series))
        if old_signal_series[i] != old_signal_series[i-1] and old_signal_series[i] != 0
    )

    print(f"  Total BUY signal candles:  {old_buy_signals:>4}")
    print(f"  Total SELL signal candles: {old_sell_signals:>4}")
    print(f"  Total HOLD signal candles: {old_hold_signals:>4}")
    print(f"  Signal changes (trades):   {old_signal_changes:>4}")

    if "signal_quality" in df_old.columns:
        old_signals_df = df_old.filter(pl.col("signal") != 0)
        if old_signals_df.height > 0:
            old_avg_quality = old_signals_df["signal_quality"].mean()
            old_min_quality = old_signals_df["signal_quality"].min()
            old_max_quality = old_signals_df["signal_quality"].max()
            print(f"  Avg signal quality:        {old_avg_quality:>4.1f}/100")
            print(f"  Quality range:             {old_min_quality:.0f}-{old_max_quality:.0f}")

    # ========================================================================
    # NEW STRATEGY - TESTING MODE
    # ========================================================================
    print("\n" + "─" * 80)
    print(" NEW STRATEGY - TESTING MODE (Event-Based, More Signals)")
    print("─" * 80)

    df_new_test = new_strategy(df.clone(), mode="testing")

    new_test_enter_long = df_new_test.filter(pl.col("enter_long")).height
    new_test_enter_short = df_new_test.filter(pl.col("enter_short")).height
    new_test_total_entries = new_test_enter_long + new_test_enter_short

    new_test_raw_long = df_new_test.filter(pl.col("enter_long_raw")).height
    new_test_raw_short = df_new_test.filter(pl.col("enter_short_raw")).height
    new_test_total_raw = new_test_raw_long + new_test_raw_short

    print(f"  Raw LONG setups detected:  {new_test_raw_long:>4}")
    print(f"  Raw SHORT setups detected: {new_test_raw_short:>4}")
    print(f"  Total raw setups:          {new_test_total_raw:>4}")
    print(f"  ────────────────────────────────")
    print(f"  LONG entries (after filter): {new_test_enter_long:>4}")
    print(f"  SHORT entries (after filter):{new_test_enter_short:>4}")
    print(f"  Total entry events:          {new_test_total_entries:>4}")

    signal_types = df_new_test.filter(
        pl.col("enter_long") | pl.col("enter_short")
    )["signal_type"].value_counts()

    if signal_types.height > 0:
        print(f"\n  Signal Type Breakdown:")
        for row in signal_types.iter_rows():
            sig_type, count = row
            print(f"    {sig_type:>15}: {count:>3}")

    quality_df = df_new_test.filter(pl.col("enter_long") | pl.col("enter_short"))
    if quality_df.height > 0:
        avg_quality = quality_df["signal_quality"].mean()
        min_quality = quality_df["signal_quality"].min()
        max_quality = quality_df["signal_quality"].max()
        print(f"\n  Avg signal quality:        {avg_quality:>4.1f}/100")
        print(f"  Quality range:             {min_quality:.0f}-{max_quality:.0f}")

    rejected_df = df_new_test.filter(
        (pl.col("enter_long_raw") | pl.col("enter_short_raw")) &
        ~pl.col("trade_ready")
    )

    if rejected_df.height > 0:
        print(f"\n  Rejected setups: {rejected_df.height}")
        rejection_reasons = rejected_df["trade_reason"].value_counts()
        for row in rejection_reasons.iter_rows():
            reason, count = row
            print(f"    {reason:>15}: {count:>3}")

    # ========================================================================
    # NEW STRATEGY - BALANCED MODE
    # ========================================================================
    print("\n" + "─" * 80)
    print(" NEW STRATEGY - BALANCED MODE (Default)")
    print("─" * 80)

    df_new_balanced = new_strategy(df.clone(), mode="balanced")

    new_bal_enter_long = df_new_balanced.filter(pl.col("enter_long")).height
    new_bal_enter_short = df_new_balanced.filter(pl.col("enter_short")).height
    new_bal_total = new_bal_enter_long + new_bal_enter_short

    print(f"  LONG entry events:         {new_bal_enter_long:>4}")
    print(f"  SHORT entry events:        {new_bal_enter_short:>4}")
    print(f"  Total entry events:        {new_bal_total:>4}")

    # ========================================================================
    # NEW STRATEGY - STRICT MODE
    # ========================================================================
    print("\n" + "─" * 80)
    print(" NEW STRATEGY - STRICT MODE (Conservative)")
    print("─" * 80)

    df_new_strict = new_strategy(df.clone(), mode="strict")

    new_strict_enter_long = df_new_strict.filter(pl.col("enter_long")).height
    new_strict_enter_short = df_new_strict.filter(pl.col("enter_short")).height
    new_strict_total = new_strict_enter_long + new_strict_enter_short

    print(f"  LONG entry events:         {new_strict_enter_long:>4}")
    print(f"  SHORT entry events:        {new_strict_enter_short:>4}")
    print(f"  Total entry events:        {new_strict_total:>4}")

    # ========================================================================
    # COMPARISON SUMMARY
    # ========================================================================
    print("\n" + "="*80)
    print(" SUMMARY")
    print("="*80 + "\n")

    print(f"  Old Strategy (Persistent State):")
    print(f"    Trade-triggering signal changes: {old_signal_changes:>3}")
    print(f"    Issue: Signal persists across candles, unclear timing")
    print()
    print(f"  New Strategy - Testing Mode (Event-Based):")
    print(f"    Entry events: {new_test_total_entries:>3}")
    print(f"    Improvement: {new_test_total_entries / max(old_signal_changes, 1):.1f}x more signals")
    print(f"    Benefit: More data for testing and optimization")
    print()
    print(f"  New Strategy - Balanced Mode:")
    print(f"    Entry events: {new_bal_total:>3}")
    print(f"    Improvement: {new_bal_total / max(old_signal_changes, 1):.1f}x more signals")
    print(f"    Benefit: Good for paper trading")
    print()
    print(f"  New Strategy - Strict Mode:")
    print(f"    Entry events: {new_strict_total:>3}")
    print(f"    Improvement: {new_strict_total / max(old_signal_changes, 1):.1f}x more signals")
    print(f"    Benefit: Conservative for live trading")

    print("\n" + "="*80)
    print(" KEY IMPROVEMENTS")
    print("="*80 + "\n")

    improvements = [
        " Event-based trading (enter_long, exit_long columns)",
        " Clear entry timing (signal TRUE only on event candle)",
        " Multiple independent signal paths (MA OR RSI OR MACD)",
        " Soft filtering (volume/RSI add to score, don't block)",
        " Trade readiness validation (every rejection has a reason)",
        " Three modes (testing/balanced/strict) for different purposes",
        " Much higher signal frequency for realistic testing",
        " Preserved ATR risk management and position sizing",
        " Backward compatible (still has 'signal' column)",
    ]

    for imp in improvements:
        print(f"  {imp}")

    print("\n" + "="*80 + "\n")

    # ========================================================================
    # RECOMMENDATIONS
    # ========================================================================
    print(" RECOMMENDATIONS:")
    print()

    if new_test_total_entries < 20:
        print("  ⚠️  Still low signal frequency in testing mode")
        print("      Consider:")
        print("        - Lowering min_signal_quality to 25-30")
        print("        - Adjusting MA periods (try 10/30 instead of 20/50)")
        print("        - Using shorter timeframe (15m or 5m)")
    elif new_test_total_entries < 40:
        print("   Adequate signal frequency for testing")
        print("      You can proceed with backtesting")
    else:
        print("   Good signal frequency for testing")
        print("      Strong dataset for optimization")

    print()

    if new_bal_total < 15:
        print("    Balanced mode may need adjustment")
        print("      Consider lowering thresholds slightly")
    else:
        print("   Balanced mode looks good for paper trading")

    print()

    if new_strict_total < 10:
        print("    Strict mode is very conservative (expected)")
        print("      Good for live trading with small positions")
    else:
        print("   Strict mode has enough signals for live trading")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare old vs new trading strategy")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe")
    parser.add_argument("--limit", type=int, default=3000, help="Number of candles")

    args = parser.parse_args()

    compare_strategies(
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
    )