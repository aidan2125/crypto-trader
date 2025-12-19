def sma(df, window=20):
    return df["close"].rolling(window=window).mean()


def ema(df, window=20):
    return df["close"].ewm(span=window, adjust=False).mean()

def rsi(df, period=14):
    delta = df["close"].diff()

    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi
