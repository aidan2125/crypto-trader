import matplotlib.pyplot as plt

def plot_signals(df, filename=None):
    """
    Plots close price with signals.
    If filename is provided, saves the chart to that file.
    """
    plt.figure(figsize=(12,6))
    plt.plot(df['timestamp'], df['close'], label='Close Price')
    plt.plot(df['timestamp'], df['sma_20'], label='SMA 20')
    plt.plot(df['timestamp'], df['ema_20'], label='EMA 20')

    buy_signals = df[df['signal'] == 1]
    sell_signals = df[df['signal'] == -1]

    plt.scatter(buy_signals['timestamp'], buy_signals['close'], marker='^', color='g', label='Buy Signal')
    plt.scatter(sell_signals['timestamp'], sell_signals['close'], marker='v', color='r', label='Sell Signal')

    plt.legend()
    plt.xlabel('Timestamp')
    plt.ylabel('Price')
    plt.title('Trading Signals')

    # Save chart if filename provided
    if filename:
        plt.savefig(filename)
    plt.close()
