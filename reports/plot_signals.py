# reports/plot_signals.py

import matplotlib.pyplot as plt
import os
from datetime import datetime

def plot_signals(df, filename="signals_plot.png"):
    """
    Plot price, moving averages, RSI, ATR, and buy/sell signals.
    Compatible with enhanced_strategy output.
    """
    if df is None or df.empty:
        print("No data to plot")
        return

    os.makedirs("reports", exist_ok=True)
    filepath = os.path.join("reports", filename)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), 
                                        gridspec_kw={'height_ratios': [3, 1, 1]})

    # --- Price + MAs + Signals ---
    ax1.plot(df.index, df['close'], label='Close Price', color='black', linewidth=1.2)
    ax1.plot(df.index, df['ma_fast'], label=f"Fast MA ({df['ma_fast'].name if hasattr(df['ma_fast'], 'name') else ''})", 
             color='blue', alpha=0.7)
    ax1.plot(df.index, df['ma_slow'], label=f"Slow MA ({df['ma_slow'].name if hasattr(df['ma_slow'], 'name') else ''})", 
             color='orange', alpha=0.7)

    # Buy/Sell markers
    buys = df[df['signal'] == 1]
    sells = df[df['signal'] == -1]

    ax1.scatter(buys.index, buys['close'], marker='^', color='green', s=100, label='BUY Signal', zorder=5)
    ax1.scatter(sells.index, sells['close'], marker='v', color='red', s=100, label='SELL Signal', zorder=5)

    ax1.set_title(f"{filename.replace('_signals.png', '').replace('_', '/')} - Price & Signals")
    ax1.set_ylabel("Price (USD)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # --- RSI ---
    if 'rsi' in df.columns:
        ax2.plot(df.index, df['rsi'], color='purple', linewidth=1)
        ax2.axhline(70, color='red', linestyle='--', alpha=0.5)
        ax2.axhline(30, color='green', linestyle='--', alpha=0.5)
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("RSI")
        ax2.set_title("RSI")
        ax2.grid(True, alpha=0.3)

    # --- ATR ---
    if 'atr' in df.columns:
        ax3.plot(df.index, df['atr'], color='teal', linewidth=1)
        ax3.set_ylabel("ATR")
        ax3.set_title("Average True Range (Volatility)")
        ax3.grid(True, alpha=0.3)

    # Final layout
    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Chart saved: {filepath}")