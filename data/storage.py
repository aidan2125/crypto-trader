import os

def save_to_csv(df, symbol, timeframe):
    os.makedirs("data/history", exist_ok=True)

    filename = f"data/history/{symbol.replace('/', '')}_{timeframe}.csv"

    df.to_csv(filename, index=False)
    print(f"Saved data to {filename}")
