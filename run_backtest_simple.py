#!/usr/bin/env python3
"""
Standalone Backtester for Crypto Trader Project
- Uses Polars throughout
- Complete BacktestPro class with all methods
- Saves results to Supabase
"""

import json
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

from data.market_data import fetch_ohlcv
from strategies.enhanced_signals import enhanced_strategy
from database.supabase_db import insert_backtest_result        # Supabase save function

# ────────────────────────────────────────────────
# Load risk config
# ────────────────────────────────────────────────
RISK_CONFIG_PATH = Path("data") / "risk_config.json"

def load_risk_config():
    """Load your risk preset from data/risk_config.json"""
    default_config = {
        "risk_per_trade": 0.01,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.0,
        "min_signal_quality": 60,
        "position_size_pct": 0.10
    }
    if RISK_CONFIG_PATH.exists():
        try:
            with open(RISK_CONFIG_PATH, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
                print(f"Loaded risk config: {RISK_CONFIG_PATH}")
                print(f"   Risk per trade: {default_config['risk_per_trade']:.1%}")
                print(f"   SL multiplier : {default_config['atr_multiplier_sl']}x ATR")
                print(f"   TP multiplier : {default_config['atr_multiplier_tp']}x ATR\n")
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

    def run(self, df: pl.DataFrame, symbol: str = "BTC/USDT", strategy_name: str = "Enhanced Strategy"):
        if df.is_empty():
            print("No data to backtest.")
            return

        print(f"=== BACKTEST START ===")
        print(f"Symbol           : {symbol}")
        print(f"Valid candles    : {df.height}")
        print(f"Strategy         : {strategy_name}")
        print(f"Initial Balance  : ${self.initial_balance:,.0f}\n")

        # Signal stats
        buys = df.filter(pl.col("signal") == 1).height
        sells = df.filter(pl.col("signal") == -1).height
        print(f"Total BUY signals  : {buys}")
        print(f"Total SELL signals : {sells}\n")

        sl_mult = self.risk_config.get('atr_multiplier_sl', 2.0)
        tp_mult = self.risk_config.get('atr_multiplier_tp', 3.0)
        risk_pct = self.risk_config.get('risk_per_trade', 0.01)

        # Cache column indices
        columns = df.columns
        close_idx  = columns.index("close") if "close" in columns else -1
        signal_idx = columns.index("signal") if "signal" in columns else -1
        atr_idx    = columns.index("atr") if "atr" in columns else -1

        if close_idx == -1 or signal_idx == -1:
            print("Missing required columns: close or signal")
            return

        print(f"Using column indices → close:{close_idx}, signal:{signal_idx}, atr:{atr_idx}\n")

        for i in range(1, df.height):
            row = df.row(i)
            price = float(row[close_idx])

            # Exit first
            if self.position:
                self._check_exit(row, price, sl_mult, tp_mult, signal_idx)

            # Entry
            signal = int(row[signal_idx])
            if signal != 0 and self.position is None and self.balance > 100:
                self._open_position(signal, row, price, risk_pct, sl_mult, tp_mult, atr_idx)

            # Equity tracking
            current_value = self.balance + (self.position['value'] if self.position else 0)
            self.equity.append(current_value)

        # Close final position if open
        if self.position:
            final_price = float(df["close"].tail(1)[0])
            self._close_position(final_price, "END_OF_DATA", sl_mult, tp_mult)

        self.print_summary(symbol, strategy_name)

    def _open_position(self, signal: int, row: tuple, price: float, risk_pct: float, sl_mult: float, tp_mult: float, atr_idx: int):
        entry_price = price * (1.0005 if signal == 1 else 0.9995)  # 0.05% slippage

        atr = None
        if atr_idx >= 0:
            atr_value = row[atr_idx]
            if atr_value is not None:
                try:
                    atr = float(atr_value)
                except (ValueError, TypeError):
                    atr = None

        if atr is not None and atr > 0:
            sl_distance = sl_mult * atr
        else:
            sl_distance = entry_price * 0.02  # fallback

        risk_amount = self.balance * risk_pct
        size_usd = risk_amount / (sl_distance / entry_price) if sl_distance > 0 else 0
        size_usd = min(size_usd, self.balance * 0.95)

        if size_usd < 50:
            return

        size_usd *= 0.999  # entry fee

        sl_price = entry_price - sl_distance if signal == 1 else entry_price + sl_distance
        tp_price = entry_price + (sl_distance * (tp_mult / sl_mult)) if signal == 1 else entry_price - (sl_distance * (tp_mult / sl_mult))

        self.position = {
            'side': 'long' if signal == 1 else 'short',
            'entry': entry_price,
            'size_usd': size_usd,
            'value': size_usd,
            'sl': sl_price,
            'tp': tp_price
        }

        self.balance -= size_usd
        side_str = "LONG " if signal == 1 else "SHORT"
        print(f"{side_str} @ {entry_price:.2f} | Size: ${size_usd:,.0f} | SL: {sl_price:.2f} | TP: {tp_price:.2f}")

    def _check_exit(self, row: tuple, price: float, sl_mult: float, tp_mult: float, signal_idx: int):
        pos = self.position
        exit_price = price * (0.9995 if pos['side'] == 'long' else 1.0005)

        hit_sl = (pos['side'] == 'long' and price <= pos['sl']) or (pos['side'] == 'short' and price >= pos['sl'])
        hit_tp = (pos['side'] == 'long' and price >= pos['tp']) or (pos['side'] == 'short' and price <= pos['tp'])

        opposite = False
        if signal_idx >= 0:
            current_signal = row[signal_idx]
            if current_signal is not None:
                opposite = (pos['side'] == 'long' and int(current_signal) == -1) or \
                           (pos['side'] == 'short' and int(current_signal) == 1)

        if hit_sl or hit_tp or opposite:
            reason = "SL" if hit_sl else ("TP" if hit_tp else "SIGNAL")
            self._close_position(exit_price, reason, sl_mult, tp_mult)

    def _close_position(self, exit_price: float, reason: str, sl_mult: float, tp_mult: float):
        pos = self.position
        pnl_raw = (exit_price - pos['entry']) * (pos['size_usd'] / pos['entry'])
        if pos['side'] == 'short':
            pnl_raw = -pnl_raw

        pnl = pnl_raw * 0.999  # exit fee

        self.balance += pos['size_usd'] + pnl
        pnl_pct = pnl / pos['size_usd'] * 100 if pos['size_usd'] != 0 else 0

        self.trades.append({'pnl': pnl, 'pnl_pct': pnl_pct, 'reason': reason})

        side_close = "SELL" if pos['side'] == 'long' else "BUY "
        print(f"{side_close} @ {exit_price:.2f} | PnL: ${pnl:+,.0f} ({pnl_pct:+.1f}%) | {reason}")

        self.position = None

    def print_summary(self, symbol: str, strategy_name: str):
        if not self.trades:
            print("\nNo trades executed — check signal generation or filters.")
            return

        df_trades = pl.DataFrame(self.trades)
        total_pnl = df_trades["pnl"].sum()
        roi = (self.balance / self.initial_balance - 1) * 100 if self.initial_balance != 0 else 0
        win_rate = df_trades.filter(pl.col("pnl") > 0).height / df_trades.height if df_trades.height > 0 else 0.0
        gross_profit = df_trades.filter(pl.col("pnl") > 0)["pnl"].sum()
        gross_loss = abs(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        equity_curve = pl.Series([self.initial_balance] + self.equity)
        max_dd = (equity_curve / equity_curve.cum_max() - 1).min() if equity_curve.len() > 1 else 0.0

        print("\n" + "═" * 70)
        print(f" BACKTEST SUMMARY - {symbol.upper()}")
        print("═" * 70)
        print(f"Strategy         : {strategy_name}")
        print(f"Total Trades     : {df_trades.height}")
        print(f"Win Rate         : {win_rate:.1%}")
        print(f"Profit Factor    : {profit_factor:.2f}")
        print(f"Total PnL        : ${total_pnl:+,.0f}")
        print(f"Final Balance    : ${self.balance:,.0f}")
        print(f"ROI              : {roi:+.1f}%")
        print(f"Max Drawdown     : {max_dd:.1%}")
        print(f"Avg PnL/Trade    : ${df_trades['pnl'].mean():+.0f}" if df_trades.height > 0 else "Avg PnL/Trade    : $0")
        print("═" * 70)


# ────────────────────────────────────────────────
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    risk_config = load_risk_config()

    symbol = "BTC/USDT"
    timeframe = "1h"
    limit = 5000

    print("Fetching market data...")
    df = fetch_ohlcv(symbol, timeframe, limit)

    if df is None or df.is_empty():
        print("Failed to fetch data.")
    else:
        print(f"Raw data: {df.height} candles\n")
        df = enhanced_strategy(df)
        print("Strategy applied.\n")

        backtester = BacktestPro(initial_balance=10000, risk_config=risk_config)
        backtester.run(df, symbol=symbol, strategy_name="Enhanced Strategy")

        # Save to Supabase
        print("\nSaving backtest result to Supabase...")
        try:
            df_trades = pl.DataFrame(backtester.trades) if backtester.trades else pl.DataFrame()
            total_pnl = df_trades["pnl"].sum() if df_trades.height > 0 else 0
            roi = (backtester.balance / backtester.initial_balance - 1) if backtester.initial_balance != 0 else 0
            win_rate = df_trades.filter(pl.col("pnl") > 0).height / df_trades.height if df_trades.height > 0 else 0.0
            gross_profit = df_trades.filter(pl.col("pnl") > 0)["pnl"].sum() if df_trades.height > 0 else 0
            gross_loss = abs(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum()) if df_trades.height > 0 else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
            equity_curve = pl.Series([backtester.initial_balance] + backtester.equity)
            max_dd = (equity_curve / equity_curve.cum_max() - 1).min() if equity_curve.len() > 1 else 0.0

            result = {
                "preset_id": 2,
                "coin_id": 1,
                "run_time": datetime.now(timezone.utc).isoformat(),
                "timeframe": timeframe,
                "num_candles": df.height,
                "num_trades": len(backtester.trades),
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "roi": roi,
                "max_drawdown": max_dd,
                "avg_pnl": df_trades["pnl"].mean() if df_trades.height > 0 else 0.0,
                "passed": int(roi > 0)
            }

            success = insert_backtest_result(result)
            print("Saved successfully:", success)

        except Exception as e:
            print(f"Failed to save to Supabase: {e}")
            import traceback
            traceback.print_exc()