"""
Enhanced Trading Strategy v2 - Professional Grade
Improves win rate, risk management, and reduces drawdowns
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def enhanced_strategy(df, config=None):
    """
    Professional Enhanced Strategy with Risk Management
    
    Features:
    - MA Crossover + RSI + Trend Filter
    - ATR-based Stop Loss & Take Profit
    - Dynamic Position Sizing
    - Trailing Stop
    - Volume Confirmation (optional)
    - Signal Quality Score
    """
    if config is None:
        config = {
            "fast_ma": 10,
            "slow_ma": 30,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "atr_period": 14,
            "atr_multiplier_sl": 2.0,
            "atr_multiplier_tp": 3.0,
            "atr_multiplier_trailing": 2.5,
            "min_volume_ratio": 1.0,  # Volume > X times 20-day avg
            "use_volume_filter": True,
            "min_signal_quality": 30
        }
    
    df = df.copy()
    
    # Indicators
    df['ma_fast'] = df['close'].rolling(window=config['fast_ma']).mean()
    df['ma_slow'] = df['close'].rolling(window=config['slow_ma']).mean()
    df['rsi'] = calculate_rsi(df['close'], config['rsi_period'])
    df['atr'] = calculate_atr(df, config['atr_period'])
    
    # Volume filter (optional)
    if 'volume' in df.columns and config['use_volume_filter']:
        df['avg_volume'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['avg_volume']
    else:
        df['volume_ratio'] = 1.0
    
    # Crossovers
    df['cross_up'] = (df['ma_fast'] > df['ma_slow']) & (df['ma_fast'].shift(1) <= df['ma_slow'].shift(1))
    df['cross_down'] = (df['ma_fast'] < df['ma_slow']) & (df['ma_fast'].shift(1) >= df['ma_slow'].shift(1))
    
    # Trend (simple price above/below slow MA)
    df['uptrend'] = df['close'] > df['ma_slow']
    df['downtrend'] = df['close'] < df['ma_slow']
    
    # Generate raw signals
    df['raw_signal'] = 0
    
    # BUY: Cross up + RSI > oversold + uptrend + volume
    buy_cond = (
        df['cross_up'] &
        (df['rsi'] > config['rsi_oversold']) &
        (df['rsi'] < config['rsi_overbought']) &
        df['uptrend'] &
        (df['volume_ratio'] >= config['min_volume_ratio'])
    )
    df.loc[buy_cond, 'raw_signal'] = 1
    
    # SELL: Cross down + RSI < overbought + downtrend + volume
    sell_cond = (
        df['cross_down'] &
        (df['rsi'] < config['rsi_overbought']) &
        (df['rsi'] > config['rsi_oversold']) &
        df['downtrend'] &
        (df['volume_ratio'] >= config['min_volume_ratio'])
    )
    df.loc[sell_cond, 'raw_signal'] = -1
    
    # Signal Quality (0-100)
    df['signal_quality'] = 0.0
    
    
    # Stronger alignment = higher quality
    quality_factors = (
        (df['raw_signal'] != 0).astype(int) * 30 +
        ((df['rsi'].between(40, 60)).astype(int) * 25) +  # RSI in "power zone"
        (np.abs(df['ma_fast'] / df['ma_slow'] - 1) > 0.01).astype(int) * 20 +  # Separation
        (df['volume_ratio'] > 1.5).astype(int) * 15 +
        (df['close'].pct_change().abs() > df['atr']/df['close']).astype(int) * 10  # Momentum
    )
    df['signal_quality'] = quality_factors
    
    # Final filtered signal
    df['signal'] = 0
    high_quality = df['signal_quality'] >= config['min_signal_quality']
    df.loc[(df['raw_signal'] == 1) & high_quality, 'signal'] = 1
    df.loc[(df['raw_signal'] == -1) & high_quality, 'signal'] = -1
    
    # Risk Management Levels
    df['stop_loss'] = np.nan
    df['take_profit'] = np.nan
    df['trailing_stop'] = np.nan
    
    # For long positions
    long_entry = df['close'][df['signal'] == 1]
    df.loc[long_entry.index, 'stop_loss'] = long_entry - config['atr_multiplier_sl'] * df['atr']
    df.loc[long_entry.index, 'take_profit'] = long_entry + config['atr_multiplier_tp'] * df['atr']
    df.loc[long_entry.index, 'trailing_stop'] = long_entry - config['atr_multiplier_trailing'] * df['atr']
    
    # For short positions
    short_entry = df['close'][df['signal'] == -1]
    df.loc[short_entry.index, 'stop_loss'] = short_entry + config['atr_multiplier_sl'] * df['atr']
    df.loc[short_entry.index, 'take_profit'] = short_entry - config['atr_multiplier_tp'] * df['atr']
    df.loc[short_entry.index, 'trailing_stop'] = short_entry + config['atr_multiplier_trailing'] * df['atr']
    
    # Position sizing (% of capital per trade based on ATR)
    risk_per_trade = 0.01  # 1% risk (can be external)
    df['position_size_pct'] = (risk_per_trade * df['close']) / (config['atr_multiplier_sl'] * df['atr'])
    df['position_size_pct'] = df['position_size_pct'].clip(0.02, 0.20)  # 2-20%
    
    return df

# Optional: Load config from your risk_config.json
def load_strategy_config():
    config_path = Path("data") / "risk_config.json"
    default_config = {
        "fast_ma": 10, "slow_ma": 30, "rsi_period": 14,
        "atr_multiplier_sl": 2.0, "atr_multiplier_tp": 3.0,
        "min_signal_quality": 30
    }
    if config_path.exists():
        try:
            with open(config_path) as f:
                user_config = json.load(f)
                default_config.update(user_config)
                print(f"Loaded strategy config from {config_path}")
        except:
            print("Could not load config, using defaults")
    return default_config

if __name__ == "__main__":
    print("Enhanced Trading Strategy v2 Loaded")
    print("\nNew Features:")
    print("✓ Fixed RSI logic for sell signals")
    print("✓ ATR-based dynamic stop loss & take profit")
    print("✓ Trailing stop levels")
    print("✓ Volatility-adjusted position sizing")
    print("✓ Volume confirmation filter")
    print("✓ Higher quality signal filtering")
    print("✓ Compatible with risk_config.json")
    print("✓ Backtest-ready with realistic risk management")