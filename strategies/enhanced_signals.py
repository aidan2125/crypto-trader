"""
Balanced Trading Strategy - Optimized for Real Market Testing
More signals, reasonable filters, good for stress testing
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

def calculate_macd(close, fast=12, slow=26, signal=9):
    """MACD for momentum confirmation"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def enhanced_strategy(df, config=None):
    """
    Balanced Strategy for Real Market Testing
    
    Key Changes:
    - Relaxed RSI thresholds (40/60 instead of 30/70)
    - Shorter MA periods for faster signals
    - Multiple signal types (MA cross, RSI extremes, MACD)
    - Minimum quality scoring but not too strict
    - Volume filter optional
    """
    if config is None:
        config = {
            "fast_ma": 5,              # Faster: was 10
            "slow_ma": 18,             # Faster: was 30
            "rsi_period": 7,
            "rsi_oversold": 45,        # Relaxed: was 30
            "rsi_overbought": 55,      # Relaxed: was 70
            "atr_period": 10,
            "atr_multiplier_sl": 1.0,
            "atr_multiplier_tp": 1.5,
            "atr_multiplier_trailing": 1.0,
            "min_volume_ratio": 0.5,   # Relaxed: was 1.0
            "use_volume_filter": False, # Disabled for more signals
            "min_signal_quality": 20   # Relaxed: was 60
        }
    
    df = df.copy()
    
    # Core Indicators
    df['ma_fast'] = df['close'].rolling(window=config['fast_ma']).mean()
    df['ma_slow'] = df['close'].rolling(window=config['slow_ma']).mean()
    df['rsi'] = calculate_rsi(df['close'], config['rsi_period'])
    df['atr'] = calculate_atr(df, config['atr_period'])
    # Defensive: ensure ATR is numeric (avoid accidental dict/object types)
    df['atr'] = pd.to_numeric(df['atr'], errors='coerce')
    # Replace zero ATR with NaN to avoid division-by-zero or meaningless sizing
    # Use assignment form to avoid pandas chained-assignment FutureWarning
    df['atr'] = df['atr'].replace(0, np.nan)
    
    # MACD for momentum
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df['close'])
    
    # Volume analysis (optional)
    if 'volume' in df.columns and config['use_volume_filter']:
        df['avg_volume'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['avg_volume']
    else:
        df['volume_ratio'] = 1.0
    
    # Price momentum
    df['price_change'] = df['close'].pct_change()
    df['momentum_5'] = df['close'].pct_change(5)
    
    # Trend identification
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['uptrend'] = df['close'] > df['ema_50']
    df['downtrend'] = df['close'] < df['ema_50']
    
    # MA Crossovers
    df['cross_up'] = (df['ma_fast'] > df['ma_slow']) & (df['ma_fast'].shift(1) <= df['ma_slow'].shift(1))
    df['cross_down'] = (df['ma_fast'] < df['ma_slow']) & (df['ma_fast'].shift(1) >= df['ma_slow'].shift(1))
    
    # MACD Crossovers
    df['macd_cross_up'] = (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1))
    df['macd_cross_down'] = (df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1))
    
    # Initialize signals
    df['raw_signal'] = 0
    df['signal_type'] = ''
    
    # ===== MULTIPLE ENTRY CONDITIONS =====
    
    # 1. MA Crossover Strategy (Primary)
    ma_buy = (
        df['cross_up'] &
        (df['rsi'] < 70) &  # Not overbought
        (df['volume_ratio'] >= config['min_volume_ratio'])
    )
    
    ma_sell = (
        df['cross_down'] &
        (df['rsi'] > 30) &  # Not oversold
        (df['volume_ratio'] >= config['min_volume_ratio'])
    )
    
    df.loc[ma_buy, 'raw_signal'] = 1
    df.loc[ma_buy, 'signal_type'] = 'MA_CROSS'
    
    df.loc[ma_sell, 'raw_signal'] = -1
    df.loc[ma_sell, 'signal_type'] = 'MA_CROSS'
    
    # 2. RSI Extreme Reversal (Secondary)
    rsi_reversal_buy = (
        (df['rsi'] < config['rsi_oversold']) &
        (df['rsi'].shift(1) < df['rsi']) &  # RSI turning up
        (df['macd_hist'] > df['macd_hist'].shift(1)) &  # MACD momentum positive
        (df['raw_signal'] == 0)  # Don't override MA signals
    )
    
    rsi_reversal_sell = (
        (df['rsi'] > config['rsi_overbought']) &
        (df['rsi'].shift(1) > df['rsi']) &  # RSI turning down
        (df['macd_hist'] < df['macd_hist'].shift(1)) &  # MACD momentum negative
        (df['raw_signal'] == 0)
    )
    
    df.loc[rsi_reversal_buy, 'raw_signal'] = 1
    df.loc[rsi_reversal_buy, 'signal_type'] = 'RSI_REVERSAL'
    
    df.loc[rsi_reversal_sell, 'raw_signal'] = -1
    df.loc[rsi_reversal_sell, 'signal_type'] = 'RSI_REVERSAL'
    
    # 3. MACD Momentum Strategy (Tertiary)
    macd_buy = (
        df['macd_cross_up'] &
        (df['uptrend']) &
        (df['rsi'] < 65) &
        (df['raw_signal'] == 0)
    )
    
    macd_sell = (
        df['macd_cross_down'] &
        (df['downtrend']) &
        (df['rsi'] > 35) &
        (df['raw_signal'] == 0)
    )
    
    df.loc[macd_buy, 'raw_signal'] = 1
    df.loc[macd_buy, 'signal_type'] = 'MACD'
    
    df.loc[macd_sell, 'raw_signal'] = -1
    df.loc[macd_sell, 'signal_type'] = 'MACD'
    
    # ===== SIGNAL QUALITY SCORING =====
    
    df['signal_quality'] = 0.0
    
    # Base score for having any signal
    df.loc[df['raw_signal'] != 0, 'signal_quality'] += 30
    
    # Trend alignment bonus
    df.loc[(df['raw_signal'] == 1) & df['uptrend'], 'signal_quality'] += 20
    df.loc[(df['raw_signal'] == -1) & df['downtrend'], 'signal_quality'] += 20
    
    # RSI in good zone (not extreme)
    df.loc[df['rsi'].between(45, 55), 'signal_quality'] += 15
    
    # Strong momentum
    df.loc[np.abs(df['momentum_5']) > 0.02, 'signal_quality'] += 15
    
    # MACD confirmation
    df.loc[(df['raw_signal'] == 1) & (df['macd_hist'] > 0), 'signal_quality'] += 10
    df.loc[(df['raw_signal'] == -1) & (df['macd_hist'] < 0), 'signal_quality'] += 10
    
    # Volume confirmation
    df.loc[(df['raw_signal'] != 0) & (df['volume_ratio'] > 1.2), 'signal_quality'] += 10
    
    # ===== FINAL SIGNAL =====
    
    df['signal'] = 0
    
    # Apply quality filter
    high_quality = df['signal_quality'] >= config['min_signal_quality']
    df.loc[(df['raw_signal'] == 1) & high_quality, 'signal'] = 1
    df.loc[(df['raw_signal'] == -1) & high_quality, 'signal'] = -1
    
    # ===== RISK MANAGEMENT LEVELS =====
    
    df['stop_loss'] = np.nan
    df['take_profit'] = np.nan
    df['trailing_stop'] = np.nan
    
    # For long positions
    long_mask = df['signal'] == 1
    df.loc[long_mask, 'stop_loss'] = df['close'] - config['atr_multiplier_sl'] * df['atr']
    df.loc[long_mask, 'take_profit'] = df['close'] + config['atr_multiplier_tp'] * df['atr']
    df.loc[long_mask, 'trailing_stop'] = df['close'] - config['atr_multiplier_trailing'] * df['atr']
    
    # For short positions
    short_mask = df['signal'] == -1
    df.loc[short_mask, 'stop_loss'] = df['close'] + config['atr_multiplier_sl'] * df['atr']
    df.loc[short_mask, 'take_profit'] = df['close'] - config['atr_multiplier_tp'] * df['atr']
    df.loc[short_mask, 'trailing_stop'] = df['close'] + config['atr_multiplier_trailing'] * df['atr']
    
    # Position sizing based on volatility
    risk_per_trade = 0.015  # 1.5% risk
    df['position_size_pct'] = (risk_per_trade * df['close']) / (config['atr_multiplier_sl'] * df['atr'])
    df['position_size_pct'] = df['position_size_pct'].clip(0.03, 0.15)  # 3-15%
    
    return df

def load_strategy_config():
    """Load config from risk_config.json"""
    config_path = Path("data") / "risk_config.json"
    default_config = {
        "fast_ma": 8,
        "slow_ma": 21,
        "rsi_oversold": 40,
        "rsi_overbought": 60,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.0,
        "min_signal_quality": 40,
        "use_volume_filter": False
    }
    
    if config_path.exists():
        try:
            with open(config_path) as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except:
            pass
    
    return default_config

if __name__ == "__main__":
    print("Balanced Trading Strategy - Loaded")
    print("\nKey Features:")
    print("  - Multiple signal types: MA Cross, RSI Reversal, MACD")
    print("  - Relaxed filters for more signals")
    print("  - Quality scoring: 40+ threshold")
    print("  - Fast MA periods (8/21) for responsiveness")
    print("  - Volume filter disabled by default")
    print("  - ATR-based dynamic risk management")
    print("\nExpected Behavior:")
    print("  - More frequent signals than strict strategy")
    print("  - Better for stress testing real market conditions")
    print("  - Quality filter prevents garbage trades")
    print("  - Good balance of signal frequency and quality")