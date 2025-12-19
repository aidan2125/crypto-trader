def moving_average_signal(df):
    df["sma_20"] = df["close"].rolling(20).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()

    df["signal"] = 0
    df.loc[df["ema_20"] > df["sma_20"], "signal"] = 1
    df.loc[df["ema_20"] < df["sma_20"], "signal"] = -1

    return df

from strategies.indicators import rsi

def moving_average_signal(df):
    df["sma_20"] = df["close"].rolling(20).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["rsi"] = rsi(df)

    df["signal"] = 0

    df.loc[
        (df["ema_20"] > df["sma_20"]) & (df["rsi"] < 70),
        "signal"
    ] = 1

    df.loc[
        (df["ema_20"] < df["sma_20"]) & (df["rsi"] > 30),
        "signal"
    ] = -1

    return df
