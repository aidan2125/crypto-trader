import pandas as pd
import numpy as np
from data.market_data import fetch_ohlcv
from strategies.signals import moving_average_signal

class Backtest:
    def __init__(self, initial_balance=1000, fee_pct=0.001, slippage_pct=0.0005, risk_per_trade=0.02):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades = []
        self.position = None
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.risk_per_trade = risk_per_trade

    def run(self, symbol, timeframe="1h", limit=500):
        print(f"\n=== BACKTEST: {symbol} ({timeframe}) ===")
        df = fetch_ohlcv(symbol, timeframe, limit).pipe(moving_average_signal).dropna()
        
        for i, row in df.iterrows():
            price = float(row.close)
            signal = int(row.signal)
            
            # Exit checks
            if self.position:
                entry, size = self.position['entry'], self.position['size']
                if price <= self.position['sl'] or price >= self.position['tp'] or signal == -1:
                    self._close(price, "EXIT")
                    continue
            
            # Entry
            if signal == 1 and not self.position and self.balance > 50:
                size = min(self.balance * 0.1, self.balance * self.risk_per_trade / 0.02)
                entry_price = price * (1 + self.slippage_pct)
                fee = size * self.fee_pct
                self.position = {
                    'entry': entry_price, 'size': size - fee,
                    'sl': entry_price * 0.98, 'tp': entry_price * 1.05
                }
                self.balance -= size
                print(f"BUY @{entry_price:.2f} | Size: ${size:.0f}")

        # Force close
        if self.position: self._close(df.close.iloc[-1], "FORCE")

        self.print_summary(symbol)

    def _close(self, price, reason):
        entry, size = self.position['entry'], self.position['size']
        exit_price = price * (1 - self.slippage_pct)
        pnl = ((exit_price - entry) * (size / entry)) - (size * self.fee_pct)
        
        self.balance += size + pnl
        self.trades.append({'pnl': pnl, 'reason': reason})
        print(f"SELL @{exit_price:.2f} | PnL: {pnl:.2f} ({reason})")
        self.position = None

    def print_summary(self, symbol):
        df_trades = pd.DataFrame(self.trades)
        roi = (self.balance / self.initial_balance - 1) * 100
        print(f"Trades: {len(df_trades)} | Win Rate: {len(df_trades[df_trades.pnl>0])/len(df_trades):.0%}")
        print(f"Final: ${self.balance:.0f} | ROI: {roi:.1f}% | Avg PnL: ${df_trades.pnl.mean():.2f}")
        print("═" * 40)