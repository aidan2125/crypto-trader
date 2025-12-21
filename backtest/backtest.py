import pandas as pd
from data.market_data import fetch_ohlcv
from strategies.signals import moving_average_signal


class Backtest:
    def __init__(self, initial_balance=1000):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = None
        self.trades = []
        self.pnl = 0.0

    def run(self, symbol, timeframe="1h", limit=200, trade_size=100):
        print(f"\n=== BACKTEST STARTED: {symbol} ===")
        print(f"Initial Balance: {self.balance:.2f}\n")

        # 1. Fetch historical data
        df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)

        # 2. Apply strategy
        df = moving_average_signal(df)

        # 3. Iterate through candles
        for i in range(len(df)):
            price = float(df["close"].iloc[i])
            signal = int(df["signal"].iloc[i])

            if signal == 1 and self.position is None:
                if self.balance >= trade_size:
                    self.position = {
                        "entry_price": price,
                        "trade_size": trade_size,
                        "time": df.index[i]
                    }
                    self.balance -= trade_size
                    print(f"BUY @ {price:.2f} | Balance: {self.balance:.2f}")

            elif signal == -1 and self.position is not None:
                entry = self.position["entry_price"]
                size = self.position["trade_size"]
                pnl = (price - entry) * (size / entry)

                self.balance += size + pnl
                self.pnl += pnl

                self.trades.append({
                    "entry": entry,
                    "exit": price,
                    "pnl": pnl
                })

                print(f"SELL @ {price:.2f} | PnL: {pnl:.2f} | Balance: {self.balance:.2f}")
                self.position = None


        # 🔒 FORCE CLOSE LAST POSITION (THIS WAS MISSED)
        if self.position is not None:
            last_price = float(df["close"].iloc[-1])
            entry = self.position["entry_price"]
            size = self.position["trade_size"]

            pnl = (last_price - entry) * (size / entry)
            self.balance += size + pnl
            self.pnl += pnl

            self.trades.append({
                "entry": entry,
                "exit": last_price,
                "pnl": pnl,
                "forced": True
            })

            print(f"FORCED SELL @ {last_price:.2f} | PnL: {pnl:.2f} | Balance: {self.balance:.2f}")
            self.position = None

        self.print_summary(symbol)

    def print_summary(self, symbol):
        print("\n=== BACKTEST SUMMARY ===")
        print(f"Symbol: {symbol}")
        print(f"Trades Executed: {len(self.trades)}")
        print(f"Final Balance: {self.balance:.2f}")
        print(f"Total PnL: {self.pnl:.2f}")
        print("========================\n")
