# backtest/backtest.py

import pandas as pd
import numpy as np

class BacktestPro:  # You can name it Backtest if you prefer
    def __init__(self, initial_balance=10000, fee_pct=0.001, slippage_pct=0.0005, risk_per_trade=0.01):
        self.initial_balance = initial_balance
        self.balance = float(initial_balance)
        self.equity = []
        self.trades = []
        self.position = None
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.risk_per_trade = risk_per_trade

    def run_with_data(self, df: pd.DataFrame, symbol: str = "ASSET", strategy_name: str = "Strategy"):
        if df.empty:
            print("No data provided for backtest.")
            return

        df = df.copy().dropna().reset_index(drop=True)

        print(f"\n=== BACKTEST START ===")
        print(f"Symbol           : {symbol}")
        print(f"Candles          : {len(df)}")
        print(f"Strategy         : {strategy_name}")
        print(f"Initial Balance  : ${self.initial_balance:,.0f}")
        print(f"Risk per Trade   : {self.risk_per_trade:.1%}\n")

        for i in range(1, len(df)):
            row = df.iloc[i]
            price = float(row['close'])

            if self.position:
                self._check_exit(row, price)

            signal = int(row['signal'])
            if signal != 0 and self.position is None and self.balance > 100:
                self._open_position(signal, row, price)

            current_value = self.balance + (self.position['value'] if self.position else 0)
            self.equity.append(current_value)

        if self.position:
            final_price = float(df['close'].iloc[-1])
            self._close_position(final_price, "END_OF_DATA")

        self.print_summary(symbol, strategy_name)

    def _open_position(self, signal: int, row: pd.Series, price: float):
        entry_price = price * (1 + self.slippage_pct if signal == 1 else 1 - self.slippage_pct)

        sl_distance = 2.0 * row['atr'] if 'atr' in row and pd.notna(row['atr']) and row['atr'] > 0 else entry_price * 0.02

        risk_amount = self.balance * self.risk_per_trade
        size_usd = risk_amount / (sl_distance / entry_price)
        size_usd = min(size_usd, self.balance * 0.95)

        if size_usd < 50:
            return

        entry_fee = size_usd * self.fee_pct
        size_usd -= entry_fee

        sl_price = entry_price - sl_distance if signal == 1 else entry_price + sl_distance
        tp_price = entry_price + (sl_distance * 2) if signal == 1 else entry_price - (sl_distance * 2)

        self.position = {
            'side': 'long' if signal == 1 else 'short',
            'entry': entry_price,
            'size_usd': size_usd,
            'value': size_usd,
            'sl': sl_price,
            'tp': tp_price
        }

        self.balance -= (size_usd + entry_fee)

        side_str = "BUY " if signal == 1 else "SELL"
        print(f"{side_str} @ {entry_price:.2f} | Size: ${size_usd:,.0f} | SL: {sl_price:.2f}")

    def _check_exit(self, row: pd.Series, price: float):
        pos = self.position
        exit_price = price * (1 - self.slippage_pct if pos['side'] == 'long' else 1 + self.slippage_pct)

        hit_sl = (pos['side'] == 'long' and price <= pos['sl']) or (pos['side'] == 'short' and price >= pos['sl'])
        hit_tp = (pos['side'] == 'long' and price >= pos['tp']) or (pos['side'] == 'short' and price <= pos['tp'])
        opposite_signal = (pos['side'] == 'long' and int(row['signal']) == -1) or (pos['side'] == 'short' and int(row['signal']) == 1)

        if hit_sl or hit_tp or opposite_signal:
            reason = "SL" if hit_sl else ("TP" if hit_tp else "SIGNAL")
            self._close_position(exit_price, reason)

    def _close_position(self, exit_price: float, reason: str):
        pos = self.position
        pnl_raw = (exit_price - pos['entry']) * (pos['size_usd'] / pos['entry'])
        if pos['side'] == 'short':
            pnl_raw = -pnl_raw

        exit_fee = pos['size_usd'] * self.fee_pct
        pnl = pnl_raw - exit_fee

        self.balance += pos['size_usd'] + pnl
        pnl_pct = pnl / pos['size_usd'] * 100 if pos['size_usd'] > 0 else 0

        self.trades.append({'pnl': pnl, 'pnl_pct': pnl_pct, 'reason': reason})

        side_close = "SELL" if pos['side'] == 'long' else "BUY "
        print(f"{side_close} @ {exit_price:.2f} | PnL: ${pnl:+,.0f} ({pnl_pct:+.1f}%) | {reason}")

        self.position = None

    def print_summary(self, symbol: str, strategy_name: str):
        if not self.trades:
            print("\nNo trades executed.")
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

        print("\n" + "═" * 60)
        print(f" BACKTEST SUMMARY - {symbol.upper()}")
        print("═" * 60)
        print(f"Strategy       : {strategy_name}")
        print(f"Trades         : {len(df_trades)}")
        print(f"Win Rate       : {win_rate:.1%}")
        print(f"Profit Factor  : {profit_factor:.2f}")
        print(f"Total PnL      : ${total_pnl:+,.0f}")
        print(f"Final Balance  : ${self.balance:,.0f}")
        print(f"ROI            : {roi:+.1f}%")
        print(f"Max Drawdown   : {max_dd:.1%}")
        print("═" * 60)