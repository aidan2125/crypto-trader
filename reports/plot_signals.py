"""
Plot Signals Module - Updated for Polars Compatibility
Compatible with enhanced_strategy output
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import polars as pl
from pathlib import Path
from datetime import datetime


def plot_signals(df, filename: str = "signals_plot.png"):
    """
    Plot price, moving averages, RSI, ATR, and buy/sell signals.
    Compatible with Polars DataFrames from enhanced_strategy output.
    
    Args:
        df: Polars DataFrame with columns: timestamp, close, ma_fast, ma_slow, 
            signal, rsi (optional), atr (optional)
        filename: Output filename for the chart
    """
    try:
        # Check if DataFrame is empty (Polars method)
        if df is None or df.is_empty():
            print("No data to plot")
            return
        
        # Handle filepath - check if filename already includes directory
        if "/" in filename or "\\" in filename:
            # Filename includes path, use it directly
            filepath = Path(filename)
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Just a filename, add reports directory
            Path("reports").mkdir(parents=True, exist_ok=True)
            filepath = Path("reports") / filename
        
        # Convert Polars DataFrame to Pandas for plotting
        # (matplotlib works better with pandas)
        df_pd = df.to_pandas()
        
        # Determine if we have RSI and ATR for subplot layout
        has_rsi = 'rsi' in df_pd.columns
        has_atr = 'atr' in df_pd.columns
        
        # Dynamic subplot configuration
        if has_rsi and has_atr:
            fig, (ax1, ax2, ax3) = plt.subplots(
                3, 1, figsize=(14, 10), 
                gridspec_kw={'height_ratios': [3, 1, 1]}
            )
        elif has_rsi or has_atr:
            fig, (ax1, ax2) = plt.subplots(
                2, 1, figsize=(14, 8), 
                gridspec_kw={'height_ratios': [3, 1]}
            )
            ax3 = None
        else:
            fig, ax1 = plt.subplots(figsize=(14, 6))
            ax2 = ax3 = None
        
        # Use timestamp as index for plotting
        if 'timestamp' in df_pd.columns:
            x_axis = df_pd['timestamp']
        else:
            x_axis = df_pd.index
        
        # ═══════════════════════════════════════════════════════════════
        # PLOT 1: Price + Moving Averages + Signals
        # ═══════════════════════════════════════════════════════════════
        
        ax1.plot(x_axis, df_pd['close'], label='Close Price', 
                color='black', linewidth=1.2)
        
        # Plot moving averages if available
        if 'ma_fast' in df_pd.columns:
            ax1.plot(x_axis, df_pd['ma_fast'], label='Fast MA', 
                    color='blue', alpha=0.7, linewidth=1)
        
        if 'ma_slow' in df_pd.columns:
            ax1.plot(x_axis, df_pd['ma_slow'], label='Slow MA', 
                    color='orange', alpha=0.7, linewidth=1)
        
        # Plot EMA if available
        if 'ema_50' in df_pd.columns:
            ax1.plot(x_axis, df_pd['ema_50'], label='EMA 50', 
                    color='purple', alpha=0.5, linewidth=1, linestyle='--')
        
        # Buy/Sell signal markers
        if 'signal' in df_pd.columns:
            buys = df_pd[df_pd['signal'] == 1]
            sells = df_pd[df_pd['signal'] == -1]
            
            if not buys.empty:
                buy_x = buys['timestamp'] if 'timestamp' in buys.columns else buys.index
                ax1.scatter(buy_x, buys['close'], marker='^', 
                           color='green', s=120, label='BUY Signal', 
                           zorder=5, edgecolors='darkgreen', linewidth=1.5)
            
            if not sells.empty:
                sell_x = sells['timestamp'] if 'timestamp' in sells.columns else sells.index
                ax1.scatter(sell_x, sells['close'], marker='v', 
                           color='red', s=120, label='SELL Signal', 
                           zorder=5, edgecolors='darkred', linewidth=1.5)
        
        # Formatting
        coin_name = filename.replace('_signals.png', '').replace('_', '/')
        ax1.set_title(f"{coin_name} - Price & Signals", fontsize=14, fontweight='bold')
        ax1.set_ylabel("Price (USD)", fontsize=12)
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3, linestyle='--')
        
        # ═══════════════════════════════════════════════════════════════
        # PLOT 2: RSI (if available)
        # ═══════════════════════════════════════════════════════════════
        
        if has_rsi and ax2 is not None:
            ax2.plot(x_axis, df_pd['rsi'], color='purple', linewidth=1.2)
            ax2.axhline(70, color='red', linestyle='--', alpha=0.5, linewidth=1)
            ax2.axhline(30, color='green', linestyle='--', alpha=0.5, linewidth=1)
            ax2.axhline(50, color='gray', linestyle=':', alpha=0.3, linewidth=0.8)
            ax2.fill_between(x_axis, 70, 100, alpha=0.1, color='red')
            ax2.fill_between(x_axis, 0, 30, alpha=0.1, color='green')
            ax2.set_ylim(0, 100)
            ax2.set_ylabel("RSI", fontsize=12)
            ax2.set_title("Relative Strength Index", fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3, linestyle='--')
        
        # ═══════════════════════════════════════════════════════════════
        # PLOT 3: ATR (if available)
        # ═══════════════════════════════════════════════════════════════
        
        if has_atr:
            # Use ax3 if we have 3 subplots, otherwise use ax2
            atr_ax = ax3 if ax3 is not None else (ax2 if not has_rsi else None)
            
            if atr_ax is not None:
                atr_ax.plot(x_axis, df_pd['atr'], color='teal', linewidth=1.2)
                atr_ax.fill_between(x_axis, df_pd['atr'], alpha=0.2, color='teal')
                atr_ax.set_ylabel("ATR", fontsize=12)
                atr_ax.set_title("Average True Range (Volatility)", 
                               fontsize=12, fontweight='bold')
                atr_ax.grid(True, alpha=0.3, linestyle='--')
        
        # ═══════════════════════════════════════════════════════════════
        # Final Layout and Save
        # ═══════════════════════════════════════════════════════════════
        
        # Rotate x-axis labels for better readability
        if ax3 is not None:
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')
        elif ax2 is not None:
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        else:
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Tight layout to prevent label cutoff
        plt.tight_layout()
        
        # Save figure
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print(f"Chart saved: {filepath}")
        
    except Exception as e:
        print(f"Error generating chart: {e}")
        import traceback
        traceback.print_exc()


def plot_backtest_results(df, trades, filename: str = "backtest.png"):
    """
    Plot backtest results with entry/exit points and equity curve.
    
    Args:
        df: Polars DataFrame with price data and equity column
        trades: List of trade dictionaries with keys: timestamp, type, price, pnl
        filename: Output filename for the chart
    """
    try:
        # Check if DataFrame is empty
        if df is None or df.is_empty():
            print("No data to plot for backtest")
            return
        
        # Handle filepath - check if filename already includes directory
        if "/" in filename or "\\" in filename:
            filepath = Path(filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)
        else:
            Path("reports").mkdir(parents=True, exist_ok=True)
            filepath = Path("reports") / filename
        
        # Convert to pandas
        df_pd = df.to_pandas()
        
        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(14, 10), 
            gridspec_kw={'height_ratios': [3, 2]}
        )
        
        # Use timestamp for x-axis
        x_axis = df_pd['timestamp'] if 'timestamp' in df_pd.columns else df_pd.index
        
        # ═══════════════════════════════════════════════════════════════
        # PLOT 1: Price with Entry/Exit Points
        # ═══════════════════════════════════════════════════════════════
        
        ax1.plot(x_axis, df_pd['close'], label='Close Price', 
                color='blue', linewidth=1.5)
        
        # Plot entry points (green arrows)
        if trades:
            entries = [t for t in trades if t.get('type') == 'entry']
            exits = [t for t in trades if t.get('type') == 'exit']
            
            if entries:
                entry_times = [t['timestamp'] for t in entries]
                entry_prices = [t['price'] for t in entries]
                ax1.scatter(entry_times, entry_prices, color='green', 
                           marker='^', s=150, label='Entry', zorder=5,
                           edgecolors='darkgreen', linewidth=2)
            
            if exits:
                exit_times = [t['timestamp'] for t in exits]
                exit_prices = [t['price'] for t in exits]
                
                # Color exits by profit/loss
                exit_colors = ['darkgreen' if t.get('pnl', 0) > 0 else 'darkred' 
                              for t in exits]
                ax1.scatter(exit_times, exit_prices, c=exit_colors, 
                           marker='v', s=150, label='Exit', zorder=5,
                           edgecolors='black', linewidth=1)
        
        ax1.set_ylabel('Price (USD)', fontsize=12)
        ax1.set_title('Backtest Results - Price & Trade Signals', 
                     fontsize=14, fontweight='bold')
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3, linestyle='--')
        
        # ═══════════════════════════════════════════════════════════════
        # PLOT 2: Equity Curve
        # ═══════════════════════════════════════════════════════════════
        
        if 'equity' in df_pd.columns:
            ax2.plot(x_axis, df_pd['equity'], 
                    color='green', linewidth=2, label='Equity')
            ax2.fill_between(x_axis, df_pd['equity'], 
                            alpha=0.3, color='green')
            
            # Add horizontal line at starting equity
            initial_equity = df_pd['equity'].iloc[0]
            ax2.axhline(initial_equity, color='gray', 
                       linestyle='--', alpha=0.5, label='Initial Balance')
        
        ax2.set_xlabel('Timestamp', fontsize=12)
        ax2.set_ylabel('Equity ($)', fontsize=12)
        ax2.set_title('Equity Curve', fontsize=12, fontweight='bold')
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3, linestyle='--')
        
        # Rotate x-axis labels
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Tight layout
        plt.tight_layout()
        
        # Save
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print(f"Backtest chart saved: {filepath}")
        
    except Exception as e:
        print(f"Error generating backtest chart: {e}")
        import traceback
        traceback.print_exc()


def plot_signal_quality_distribution(df, filename: str = "signal_quality.png"):
    """
    Plot distribution of signal quality scores.
    
    Args:
        df: Polars DataFrame with signal_quality column
        filename: Output filename for the chart
    """
    try:
        if df is None or df.is_empty():
            print("No data to plot")
            return
        
        if 'signal_quality' not in df.columns:
            print("No signal_quality column found")
            return
        
        # Handle filepath - check if filename already includes directory
        if "/" in filename or "\\" in filename:
            filepath = Path(filename)
            filepath.parent.mkdir(parents=True, exist_ok=True)
        else:
            Path("reports").mkdir(parents=True, exist_ok=True)
            filepath = Path("reports") / filename
        
        # Convert to pandas
        df_pd = df.to_pandas()
        
        # Filter out zero quality signals
        quality_scores = df_pd[df_pd['signal_quality'] > 0]['signal_quality']
        
        if quality_scores.empty:
            print("No non-zero quality scores to plot")
            return
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Histogram
        ax1.hist(quality_scores, bins=20, color='steelblue', 
                edgecolor='black', alpha=0.7)
        ax1.axvline(quality_scores.mean(), color='red', 
                   linestyle='--', linewidth=2, label=f'Mean: {quality_scores.mean():.1f}')
        ax1.axvline(quality_scores.median(), color='green', 
                   linestyle='--', linewidth=2, label=f'Median: {quality_scores.median():.1f}')
        ax1.set_xlabel('Signal Quality Score', fontsize=12)
        ax1.set_ylabel('Frequency', fontsize=12)
        ax1.set_title('Signal Quality Distribution', fontsize=14, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Box plot
        ax2.boxplot(quality_scores, vert=True, patch_artist=True,
                   boxprops=dict(facecolor='lightblue', color='blue'),
                   medianprops=dict(color='red', linewidth=2),
                   whiskerprops=dict(color='blue'),
                   capprops=dict(color='blue'))
        ax2.set_ylabel('Signal Quality Score', fontsize=12)
        ax2.set_title('Signal Quality Box Plot', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print(f"Signal quality chart saved: {filepath}")
        
    except Exception as e:
        print(f"Error generating signal quality chart: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test with sample Polars DataFrame
    print("Testing plot_signals with Polars DataFrame...")
    
    import numpy as np
    from datetime import timedelta
    
    # Create sample data
    n = 200
    start_date = datetime.now() - timedelta(days=n)
    
    # Generate sample price data
    price = 100 + np.cumsum(np.random.randn(n) * 2)
    
    df = pl.DataFrame({
        'timestamp': [start_date + timedelta(hours=i) for i in range(n)],
        'open': price + np.random.randn(n),
        'high': price + abs(np.random.randn(n)),
        'low': price - abs(np.random.randn(n)),
        'close': price,
        'volume': np.random.randint(1000, 10000, n),
        'ma_fast': price + np.random.randn(n) * 0.5,
        'ma_slow': price + np.random.randn(n) * 0.8,
        'rsi': 30 + np.random.randn(n) * 20,
        'atr': 2 + abs(np.random.randn(n)),
        'signal': [0] * n
    })
    
    # Add some buy/sell signals
    df = df.with_columns([
        pl.when(pl.col('rsi') < 35).then(1)
          .when(pl.col('rsi') > 65).then(-1)
          .otherwise(0).alias('signal')
    ])
    
    # Test plot
    plot_signals(df, filename="test_signals.png")
    print("\nTest complete!")
    print("Check reports/test_signals.png")
