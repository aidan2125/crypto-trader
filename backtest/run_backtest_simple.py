#!/usr/bin/env python3
"""
Standalone Backtester for Crypto Trader Project
- Uses Polars throughout
- Complete BacktestPro class with all methods
- Saves results to Supabase via supabase_db module

SL/TP source: reads pre-computed stop_loss and take_profit columns from the
strategy dataframe. The backtest engine does NOT recompute them from
risk_config multipliers — that would silently override _MODE_CONFIG values.
risk_config is still used for risk_per_trade (position sizing) only.
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import polars as pl
from dotenv import load_dotenv

from data.market_data import fetch_ohlcv
from strategies.enhanced_signals_refactored import enhanced_strategy
from strategies.adaptive_mode import choose_strategy_mode

# Supabase removed — results are logged to SQLite via TradeLogger instead
def insert_backtest_result(*args, **kwargs):
    return False  # no-op stub

load_dotenv()


# ────────────────────────────────────────────────
# Load risk config
# ────────────────────────────────────────────────
RISK_CONFIG_PATH = Path("data") / "risk_config.json"


def load_risk_config():
    """Load risk preset from data/risk_config.json.
    Only risk_per_trade is used by the backtester — SL/TP come from the strategy df.
    """
    default_config = {
        "risk_per_trade":      0.01,
        "min_signal_quality":  60,
        "position_size_pct":   0.10,
    }
    if RISK_CONFIG_PATH.exists():
        try:
            with open(RISK_CONFIG_PATH, "r") as f:
                user_config = json.load(f)
                default_config.update(user_config)
                print(f"Loaded risk config: {RISK_CONFIG_PATH}")
                print(f"   Risk per trade: {default_config['risk_per_trade']:.1%}\n")
        except Exception as e:
            print(f"Could not load risk config: {e}. Using defaults.")
    else:
        print("No risk_config.json found — using default settings.\n")
    return default_config


# ────────────────────────────────────────────────
# Backtest engine
# ────────────────────────────────────────────────
class BacktestPro:
    def __init__(self, initial_balance=10000, risk_config=None):
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.equity = []
        self.trades = []
        self.position = None
        self.risk_config = risk_config or {}

    def run(
        self,
        df: pl.DataFrame,
        symbol: str = "BTC/USDT",
        strategy_name: str = "Enhanced Strategy",
    ):
        if df.is_empty():
            print("No data to backtest.")
            return

        print(f"=== BACKTEST START ===")
        print(f"Symbol           : {symbol}")
        print(f"Valid candles    : {df.height}")
        print(f"Strategy         : {strategy_name}")
        print(f"Initial Balance  : ${self.initial_balance:,.0f}\n")

        buys  = df.filter(pl.col("signal") == 1).height
        sells = df.filter(pl.col("signal") == -1).height
        print(f"Total BUY signals  : {buys}")
        print(f"Total SELL signals : {sells}\n")

        risk_pct = self.risk_config.get("risk_per_trade", 0.01)

        # Cache column indices
        columns     = df.columns
        close_idx   = columns.index("close")          if "close"          in columns else -1
        signal_idx  = columns.index("signal")         if "signal"         in columns else -1
        atr_idx     = columns.index("atr")            if "atr"            in columns else -1
        quality_idx = columns.index("signal_quality") if "signal_quality" in columns else -1
        sl_idx      = columns.index("stop_loss")      if "stop_loss"      in columns else -1
        tp_idx      = columns.index("take_profit")    if "take_profit"    in columns else -1

        if close_idx == -1 or signal_idx == -1:
            print("Missing required columns: close or signal")
            return

        if sl_idx == -1 or tp_idx == -1:
            print("WARNING: stop_loss / take_profit columns missing — "
                  "falling back to ATR-based computation from risk_config.")

        print(
            f"Using column indices → "
            f"close:{close_idx}, signal:{signal_idx}, "
            f"atr:{atr_idx}, signal_quality:{quality_idx}, "
            f"stop_loss:{sl_idx}, take_profit:{tp_idx}\n"
        )

        for i in range(1, df.height):
            row   = df.row(i)
            price = float(row[close_idx])

            # Update position mark-to-market value for accurate equity tracking
            if self.position:
                pos = self.position
                current_pnl = (price - pos["entry"]) * (pos["size_usd"] / pos["entry"])
                if pos["side"] == "short":
                    current_pnl = -current_pnl
                pos["value"] = pos["size_usd"] + current_pnl

            # Exit check runs before entry — SL/TP only, no signal-based exit
            if self.position:
                self._check_exit(row, price)

            # Entry: only enter if no position is open
            signal = int(row[signal_idx])
            if signal != 0 and self.position is None and self.balance > 100:
                self._open_position(
                    signal, row, price, risk_pct,
                    atr_idx, quality_idx, sl_idx, tp_idx
                )

            # Equity tracking
            current_value = self.balance + (self.position["value"] if self.position else 0)
            self.equity.append(current_value)

        # Close final open position
        if self.position:
            final_price = float(df["close"].tail(1)[0])
            self._close_position(final_price, "END_OF_DATA")

        self.print_summary(symbol, strategy_name)

    def _open_position(
        self,
        signal: int,
        row: tuple,
        price: float,
        risk_pct: float,
        atr_idx: int,
        quality_idx: int,
        sl_idx: int,
        tp_idx: int,
    ):
        entry_price = price * (1.0005 if signal == 1 else 0.9995)  # 0.05% slippage

        # ── Read SL/TP from strategy dataframe (primary source) ───────────────
        # The strategy already computed these using _MODE_CONFIG multipliers.
        # Reading them here ensures the backtest actually tests what the
        # strategy intends, rather than silently overriding with risk_config.
        sl_price = None
        tp_price = None

        if sl_idx >= 0 and row[sl_idx] is not None:
            try:
                sl_price = float(row[sl_idx])
            except (ValueError, TypeError):
                sl_price = None

        if tp_idx >= 0 and row[tp_idx] is not None:
            try:
                tp_price = float(row[tp_idx])
            except (ValueError, TypeError):
                tp_price = None

        # ── Fallback: recompute from ATR if df columns are missing/null ───────
        if sl_price is None or tp_price is None:
            atr = None
            if atr_idx >= 0 and row[atr_idx] is not None:
                try:
                    atr = float(row[atr_idx])
                except (ValueError, TypeError):
                    atr = None

            sl_distance = atr * 2.5 if (atr is not None and atr > 0) else entry_price * 0.02
            tp_distance = sl_distance * 1.5

            if signal == 1:
                sl_price = entry_price - sl_distance
                tp_price = entry_price + tp_distance
            else:
                sl_price = entry_price + sl_distance
                tp_price = entry_price - tp_distance

        # ── Position sizing: risk a fixed % of balance per trade ──────────────
        sl_distance = abs(entry_price - sl_price)

        # Signal quality scaling
        signal_quality = 60.0
        if quality_idx >= 0 and row[quality_idx] is not None:
            try:
                signal_quality = float(row[quality_idx])
            except (ValueError, TypeError):
                pass

        if signal_quality >= 80:
            risk_pct_adjusted = risk_pct * 1.5
        elif signal_quality >= 60:
            risk_pct_adjusted = risk_pct
        else:
            risk_pct_adjusted = risk_pct * 0.5

        risk_amount = self.balance * risk_pct_adjusted
        size_usd = (
            risk_amount / (sl_distance / entry_price)
            if sl_distance > 0
            else 0
        )
        size_usd = min(size_usd, self.balance * 0.50)  # max 50% of balance per trade

        if size_usd < 50:
            return

        size_usd *= 0.999  # entry fee

        self.position = {
            "side":     "long" if signal == 1 else "short",
            "entry":    entry_price,
            "size_usd": size_usd,
            "value":    size_usd,
            "sl":       sl_price,
            "tp":       tp_price,
        }

        self.balance -= size_usd
        side_str = "LONG " if signal == 1 else "SHORT"
        print(
            f"{side_str} @ {entry_price:.2f} | "
            f"Size: ${size_usd:,.0f} | "
            f"SL: {sl_price:.2f} | "
            f"TP: {tp_price:.2f}"
        )

    def _check_exit(self, row: tuple, price: float):
        pos = self.position
        exit_price = price * (0.9995 if pos["side"] == "long" else 1.0005)

        hit_sl = (pos["side"] == "long"  and price <= pos["sl"]) or (
                  pos["side"] == "short" and price >= pos["sl"])
        hit_tp = (pos["side"] == "long"  and price >= pos["tp"]) or (
                  pos["side"] == "short" and price <= pos["tp"])

        if hit_sl or hit_tp:
            self._close_position(exit_price, "SL" if hit_sl else "TP")

    def _close_position(self, exit_price: float, reason: str):
        pos = self.position
        pnl_raw = (exit_price - pos["entry"]) * (pos["size_usd"] / pos["entry"])
        if pos["side"] == "short":
            pnl_raw = -pnl_raw

        pnl     = pnl_raw * 0.999  # exit fee
        pnl_pct = pnl / pos["size_usd"] * 100 if pos["size_usd"] != 0 else 0

        self.balance += pos["size_usd"] + pnl
        self.trades.append({
            "pnl":     pnl,
            "pnl_pct": pnl_pct,
            "reason":  reason,
            "side":    pos["side"],
            "entry":   pos["entry"],
            "exit":    exit_price,
        })

        side_close = "SELL" if pos["side"] == "long" else "BUY "
        print(f"{side_close} @ {exit_price:.2f} | PnL: ${pnl:+,.0f} ({pnl_pct:+.1f}%) | {reason}")

        self.position = None

    def print_summary(self, symbol: str, strategy_name: str):
        if not self.trades:
            print("\nNo trades executed — check signal generation or filters.")
            return

        df_trades     = pl.DataFrame(self.trades)
        total_pnl     = df_trades["pnl"].sum()
        roi           = (self.balance / self.initial_balance - 1) * 100
        win_rate      = (
            df_trades.filter(pl.col("pnl") > 0).height / df_trades.height
            if df_trades.height > 0 else 0.0
        )
        gross_profit  = df_trades.filter(pl.col("pnl") > 0)["pnl"].sum()
        gross_loss    = abs(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        equity_curve  = pl.Series([self.initial_balance] + self.equity)
        max_dd        = (
            (equity_curve / equity_curve.cum_max() - 1).min()
            if equity_curve.len() > 1 else 0.0
        )

        sl_count = df_trades.filter(pl.col("reason") == "SL").height
        tp_count = df_trades.filter(pl.col("reason") == "TP").height

        print("\n" + "═" * 70)
        print(f" BACKTEST SUMMARY - {symbol.upper()}")
        print("═" * 70)
        print(f"Strategy         : {strategy_name}")
        print(f"Total Trades     : {df_trades.height}")
        print(f"Win Rate         : {win_rate:.1%}")
        print(f"Profit Factor    : {profit_factor:.2f}")
        print(f"SL Exits         : {sl_count} | TP Exits: {tp_count}")
        print(f"Total PnL        : ${total_pnl:+,.0f}")
        print(f"Final Balance    : ${self.balance:,.0f}")
        print(f"ROI              : {roi:+.1f}%")
        print(f"Max Drawdown     : {max_dd:.1%}")
        print(f"Avg PnL/Trade    : ${df_trades['pnl'].mean():+.0f}")
        print("═" * 70)


# ────────────────────────────────────────────────
# CLI argument parsing
# ────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest a trading strategy against historical OHLCV data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbol",    type=str, default="BTC/USDT")
    parser.add_argument("--timeframe", type=str, default="1h")
    parser.add_argument("--limit",     type=int, default=1000)
    parser.add_argument("--mode",      type=str, default="auto",
                        choices=["auto", "testing", "balanced", "strict"])
    return parser.parse_args()


# ────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────
if __name__ == "__main__":
    args        = parse_args()
    risk_config = load_risk_config()

    print("=== RUN PARAMETERS ===")
    print(f"Symbol    : {args.symbol}")
    print(f"Timeframe : {args.timeframe}")
    print(f"Limit     : {args.limit} candles")
    print(f"Mode      : {args.mode}")
    print("=" * 22 + "\n")

    print("Fetching market data...")
    df = fetch_ohlcv(args.symbol, args.timeframe, args.limit)

    if df is None or df.is_empty():
        print("Failed to fetch data.")
    else:
        print(f"Raw data: {df.height} candles\n")

        # Step 1: indicator pass so ATR exists before mode selection
        df_indicator_pass = enhanced_strategy(df.clone(), mode="strict")

        # Step 2: choose mode
        selected_mode = choose_strategy_mode(
            args.symbol, df_indicator_pass, requested_mode=args.mode
        )
        print(f"Selected strategy mode: {selected_mode}\n")

        # Step 3: final strategy pass with resolved mode
        df_final = enhanced_strategy(df.clone(), mode=selected_mode)
        print("Strategy applied.\n")
       
        

        backtester = BacktestPro(initial_balance=10000, risk_config=risk_config)
        backtester.run(
            df_final,
            symbol=args.symbol,
            strategy_name=f"Enhanced Strategy [{selected_mode}]",
        )

        if insert_backtest_result is None:
            print("\nSupabase not available — skipping save.")
        else:
            print("\nSaving backtest result to Supabase...")
            try:
                df_trades    = pl.DataFrame(backtester.trades) if backtester.trades else pl.DataFrame()
                gross_profit = float(df_trades.filter(pl.col("pnl") > 0)["pnl"].sum()) if df_trades.height > 0 else 0.0
                gross_loss   = abs(float(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum())) if df_trades.height > 0 else 0.0
                equity_curve = pl.Series([backtester.initial_balance] + backtester.equity)

                result = {
                    "preset_id":      2,
                    "coin_id":        1,
                    "symbol":         args.symbol,
                    "requested_mode": args.mode,
                    "selected_mode":  selected_mode,
                    "run_time":       datetime.now(timezone.utc).isoformat(),
                    "timeframe":      args.timeframe,
                    "num_candles":    df_final.height,
                    "num_trades":     len(backtester.trades),
                    "win_rate":       float(df_trades.filter(pl.col("pnl") > 0).height / df_trades.height) if df_trades.height > 0 else 0.0,
                    "profit_factor":  gross_profit / gross_loss if gross_loss > 0 else 0.0,
                    "roi":            float(backtester.balance / backtester.initial_balance - 1),
                    "max_drawdown":   float((equity_curve / equity_curve.cum_max() - 1).min()) if equity_curve.len() > 1 else 0.0,
                    "avg_pnl":        float(df_trades["pnl"].mean()) if df_trades.height > 0 else 0.0,
                    "total_pnl":      float(df_trades["pnl"].sum()) if df_trades.height > 0 else 0.0,
                    "passed":         int(backtester.balance > backtester.initial_balance),
                }

                success = insert_backtest_result(result)
                print(f"Backtest saved successfully: {success}")

            except Exception as e:
                print(f"Failed to save to Supabase: {e}")
                import traceback
                traceback.print_exc()

            