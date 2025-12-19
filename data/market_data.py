import ccxt
import pandas as pd
from data.storage import save_to_csv



def fetch_ohlcv(symbol="BTC/USDT", timeframe="1h", limit=100):
    exchange = ccxt.binance()

    ohlcv = exchange.fetch_ohlcv(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit
    )

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    return df


if __name__ == "__main__":
    df = fetch_ohlcv()
    save_to_csv(df, "BTC/USDT", "1h")

