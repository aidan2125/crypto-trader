# run_backtest_simple.py
"""
Standalone Backtester for Crypto Trader Project
- Fully self-contained (no import/package issues)
- Uses your existing enhanced_strategy and fetch_ohlcv
- Integrates with your risk_config.json presets
- Professional output with trades, PnL, ROI, drawdown

Run with:
    python run_backtest_simple.py

Compatible with your run_with_risk_preset.py workflow:
1. Run preset applier → updates data/risk_config.json
2. Run this backtest → uses the same risk settings
"""

import pandas as pd
import json
from pathlib import Path
from data.market_data import fetch_ohlcv
from strategies.enhanced_signals import enhanced_strategy  # Your strategy function

# Load risk config to sync with your live bot presets
RISK_CONFIG_PATH = Path("data") / "risk_config.json"

def load_risk_config():
    """Load your risk preset from data/risk_config.json (applied by run_with_risk_preset.py)"""
    default_config = {
        "risk_per_trade": 0.01,          # 1% risk per trade
        "atr_multiplier_sl": 2.0,         # Stop Loss = 2 x ATR
        "atr_multiplier_tp": 3.0,         # Take Profit = 3 x ATR (1:1.5 RR)
        "min_signal_quality": 60,        # Only trade high-quality signals
        "position_size_pct": 0.10        # Fallback fixed size if ATR missing
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

class BacktestPro:
    def __init__(self, initial_balance=10000, risk_config=None):
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.equity = []
        self.trades = []
        self.position = None
        self.risk_config = risk_config or {}

    def run(self, df: pd.DataFrame, symbol: str = "BTC/USDT", strategy_name: str = "Enhanced Strategy"):
        if df.empty:
            print("No data to backtest.")
            return

        # Clean data: only require close and signal
        df = df.copy()
        df = df.dropna(subset=['close', 'signal']).reset_index(drop=True)

        if len(df) < 50:
            print("Not enough valid data after cleaning.")
            return

        print(f"=== BACKTEST START ===")
        print(f"Symbol           : {symbol}")
        print(f"Valid candles    : {len(df)}")
        print(f"Strategy         : {strategy_name}")
        print(f"Initial Balance  : ${self.initial_balance:,.0f}\n")

        # Signal stats
        buys = (df['signal'] == 1).sum()
        sells = (df['signal'] == -1).sum()
        print(f"Total BUY signals  : {buys}")
        print(f"Total SELL signals : {sells}\n")

        sl_mult = self.risk_config.get('atr_multiplier_sl', 2.0)
        tp_mult = self.risk_config.get('atr_multiplier_tp', 3.0)
        risk_pct = self.risk_config.get('risk_per_trade', 0.01)

        for i in range(1, len(df)):
            row = df.iloc[i]
            price = float(row['close'])

            # Exit first
            if self.position:
                self._check_exit(row, price, sl_mult, tp_mult)

            # Entry
            signal = int(row['signal'])
            if signal != 0 and self.position is None and self.balance > 100:
                self._open_position(signal, row, price, risk_pct, sl_mult, tp_mult)

            # Equity tracking
            current_value = self.balance + (self.position['value'] if self.position else 0)
            self.equity.append(current_value)

        # Close final position
        if self.position:
            final_price = float(df['close'].iloc[-1])
            self._close_position(final_price, "END_OF_DATA", sl_mult, tp_mult)

        self.print_summary(symbol, strategy_name)

    def _open_position(self, signal: int, row: pd.Series, price: float, risk_pct: float, sl_mult: float, tp_mult: float):
        entry_price = price * (1.0005 if signal == 1 else 0.9995)  # 0.05% slippage

        # Stop distance
        if 'atr' in row and pd.notna(row['atr']) and row['atr'] > 0:
            sl_distance = sl_mult * row['atr']
        else:
            sl_distance = entry_price * 0.02  # fallback

        # Position sizing: risk fixed % of balance
        risk_amount = self.balance * risk_pct
        size_usd = risk_amount / (sl_distance / entry_price)
        size_usd = min(size_usd, self.balance * 0.95)

        if size_usd < 50:
            return

        # Fee on entry
        size_usd *= 0.999  # 0.1% fee

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

    def _check_exit(self, row: pd.Series, price: float, sl_mult: float, tp_mult: float):
        pos = self.position
        exit_price = price * (0.9995 if pos['side'] == 'long' else 1.0005)

        hit_sl = (pos['side'] == 'long' and price <= pos['sl']) or (pos['side'] == 'short' and price >= pos['sl'])
        hit_tp = (pos['side'] == 'long' and price >= pos['tp']) or (pos['side'] == 'short' and price <= pos['tp'])
        opposite = (pos['side'] == 'long' and row['signal'] == -1) or (pos['side'] == 'short' and row['signal'] == 1)

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
        pnl_pct = pnl / pos['size_usd'] * 100

        self.trades.append({'pnl': pnl, 'pnl_pct': pnl_pct, 'reason': reason})

        side_close = "SELL" if pos['side'] == 'long' else "BUY "
        print(f"{side_close} @ {exit_price:.2f} | PnL: ${pnl:+,.0f} ({pnl_pct:+.1f}%) | {reason}")

        self.position = None

    def print_summary(self, symbol: str, strategy_name: str):
        if not self.trades:
            print("\nNo trades executed — check signal generation or filters.")
            return

        df_trades = pd.DataFrame(self.trades)
        total_pnl = df_trades['pnl'].sum()
        roi = (self.balance / self.initial_balance - 1) * 100
        win_rate = (df_trades['pnl'] > 0).mean()
        gross_profit = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df_trades[df_trades['pnl'] <= 0]['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        equity_curve = pd.Series([self.initial_balance] + self.equity)
        max_dd = (equity_curve / equity_curve.cummax() - 1).min()

        print("\n" + "═" * 70)
        print(f" BACKTEST SUMMARY - {symbol.upper()}")
        print("═" * 70)
        print(f"Strategy         : {strategy_name}")
        print(f"Total Trades     : {len(df_trades)}")
        print(f"Win Rate         : {win_rate:.1%}")
        print(f"Profit Factor    : {profit_factor:.2f}")
        print(f"Total PnL        : ${total_pnl:+,.0f}")
        print(f"Final Balance    : ${self.balance:,.0f}")
        print(f"ROI              : {roi:+.1f}%")
        print(f"Max Drawdown     : {max_dd:.1%}")
        print(f"Avg PnL/Trade    : ${df_trades['pnl'].mean():+.0f}")
        print("═" * 70)


# === MAIN EXECUTION ===
if __name__ == "__main__":
    # Load your active risk preset
    risk_config = load_risk_config()

    # Configuration
    symbol = "BTC/USDT"
    timeframe = "1h"
    limit = 5000  # Adjust based on your exchange API  2000

    print("Fetching market data...")
    df = fetch_ohlcv(symbol, timeframe, limit)

    if df is None or df.empty:
        print("Failed to fetch data.")
    else:
        print(f"Raw data: {len(df)} candles\n")
        df = enhanced_strategy(df)
        print("Strategy applied.\n")

        backtester = BacktestPro(initial_balance=10000, risk_config=risk_config)
        backtester.run(df, symbol=symbol, strategy_name="Enhanced Strategy")