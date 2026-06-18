"""
Balanced Trading Strategy - Optimized for Real Market Testing
More signals, reasonable filters, good for stress testing

SECURITY NOTE: This strategy file works with the security-hardened main_enhanced.py
Compatible with: Polars DataFrames
"""

import polars as pl
import json
from pathlib import Path
import logging


def calculate_rsi(series: pl.Expr, period: int = 14) -> pl.Expr:
    """
    Calculate Relative Strength Index (RSI).
    
    Args:
        series: Polars expression for price series
        period: RSI period (default: 14)
        
    Returns:
        RSI values as Polars expression
    """
    delta = series.diff()
    gain = delta.clip(lower_bound=0)
    loss = (-delta).clip(lower_bound=0)

    avg_gain = gain.rolling_mean(window_size=period, min_periods=period)
    avg_loss = loss.rolling_mean(window_size=period, min_periods=period)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(df: pl.DataFrame, period: int = 14) -> pl.Expr:
    """
    Calculate Average True Range (ATR).
    
    Args:
        df: Polars DataFrame with OHLC data
        period: ATR period (default: 14)
        
    Returns:
        ATR values as Polars expression
    """
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()

    tr = pl.max_horizontal(high_low, high_close, low_close)
    atr = tr.rolling_mean(window_size=period, min_periods=period)
    return atr


def calculate_macd(
    close: pl.Expr,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> tuple[pl.Expr, pl.Expr, pl.Expr]:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        close: Polars expression for close prices
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal line period (default: 9)
        
    Returns:
        Tuple of (macd, signal_line, histogram)
    """
    ema_fast = close.ewm_mean(span=fast, adjust=False)
    ema_slow = close.ewm_mean(span=slow, adjust=False)
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm_mean(span=signal, adjust=False)
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def enhanced_strategy(df: pl.DataFrame, config: dict = None) -> pl.DataFrame:
    """
    Balanced Strategy for Real Market Testing.
    
    Combines multiple technical indicators:
    - Moving Average crossovers
    - RSI reversals
    - MACD momentum
    - Volume confirmation
    - Signal quality scoring
    
    Args:
        df: Polars DataFrame with OHLC data (columns: open, high, low, close, volume, timestamp)
        config: Optional strategy configuration dictionary
        
    Returns:
        DataFrame with trading signals and risk management levels
    """
    if config is None:
        config = get_default_config()
    
    try:
        # Validate input DataFrame
        required_cols = ['open', 'high', 'low', 'close', 'timestamp']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logging.error(f"Missing required columns: {missing_cols}")
            return df.with_columns(pl.lit(0).alias("signal"))
        
        # Check if DataFrame is empty
        if df.is_empty():
            logging.warning("Empty DataFrame passed to strategy")
            return df.with_columns(pl.lit(0).alias("signal"))

        # 1. Core Indicators
        df = df.with_columns([
            pl.col("close").rolling_mean(window_size=config["fast_ma"]).alias("ma_fast"),
            pl.col("close").rolling_mean(window_size=config["slow_ma"]).alias("ma_slow"),
            calculate_rsi(pl.col("close"), config["rsi_period"]).alias("rsi"),
            calculate_atr(df, config["atr_period"]).alias("atr"),
            calculate_macd(pl.col("close"))[0].alias("macd"),
            calculate_macd(pl.col("close"))[1].alias("macd_signal"),
            calculate_macd(pl.col("close"))[2].alias("macd_hist"),
        ])

        # 2. Volume analysis
        if "volume" in df.columns and config["use_volume_filter"]:
            df = df.with_columns(
                pl.col("volume")
                  .rolling_mean(window_size=20, min_periods=1)
                  .alias("avg_volume")
            )
            df = df.with_columns(
                (pl.col("volume") / pl.col("avg_volume"))
                  .alias("volume_ratio")
            )
        else:
            df = df.with_columns(pl.lit(1.0).alias("volume_ratio"))

        # 3. Price momentum & trend
        df = df.with_columns([
            pl.col("close").pct_change().alias("price_change"),
            pl.col("close").pct_change(n=5).alias("momentum_5")
        ])

        df = df.with_columns(
            pl.col("close").ewm_mean(span=50, adjust=False).alias("ema_50")
        )

        df = df.with_columns([
            (pl.col("close") > pl.col("ema_50")).alias("uptrend"),
            (pl.col("close") < pl.col("ema_50")).alias("downtrend")
        ])

        # 4. Crossovers
        df = df.with_columns([
            ((pl.col("ma_fast") > pl.col("ma_slow")) &
             (pl.col("ma_fast").shift(1) <= pl.col("ma_slow").shift(1))).alias("cross_up"),
            ((pl.col("ma_fast") < pl.col("ma_slow")) &
             (pl.col("ma_fast").shift(1) >= pl.col("ma_slow").shift(1))).alias("cross_down"),
            ((pl.col("macd") > pl.col("macd_signal")) &
             (pl.col("macd").shift(1) <= pl.col("macd_signal").shift(1))).alias("macd_cross_up"),
            ((pl.col("macd") < pl.col("macd_signal")) &
             (pl.col("macd").shift(1) >= pl.col("macd_signal").shift(1))).alias("macd_cross_down")
        ])

        # 5. Initialize signals
        df = df.with_columns([
            pl.lit(0).alias("raw_signal"),
            pl.lit("").alias("signal_type")
        ])

        # 6. Apply signals in priority order (MA > RSI Reversal > MACD)
        ma_buy = (
            pl.col("cross_up") &
            (pl.col("rsi") < 70) &
            (pl.col("volume_ratio") >= config["min_volume_ratio"])
        )
        ma_sell = (
            pl.col("cross_down") &
            (pl.col("rsi") > 30) &
            (pl.col("volume_ratio") >= config["min_volume_ratio"])
        )

        df = df.with_columns([
            pl.when(ma_buy).then(1)
              .when(ma_sell).then(-1)
              .otherwise(pl.col("raw_signal"))
              .alias("raw_signal"),
            pl.when(ma_buy | ma_sell).then(pl.lit("MA_CROSS"))
              .otherwise(pl.col("signal_type"))
              .alias("signal_type")
        ])

        rsi_reversal_buy = (
            (pl.col("rsi") < config["rsi_oversold"]) &
            (pl.col("rsi").shift(1) < pl.col("rsi")) &
            (pl.col("macd_hist") > pl.col("macd_hist").shift(1)) &
            (pl.col("raw_signal") == 0)
        )
        rsi_reversal_sell = (
            (pl.col("rsi") > config["rsi_overbought"]) &
            (pl.col("rsi").shift(1) > pl.col("rsi")) &
            (pl.col("macd_hist") < pl.col("macd_hist").shift(1)) &
            (pl.col("raw_signal") == 0)
        )

        df = df.with_columns([
            pl.when(rsi_reversal_buy).then(1)
              .when(rsi_reversal_sell).then(-1)
              .otherwise(pl.col("raw_signal"))
              .alias("raw_signal"),
            pl.when(rsi_reversal_buy | rsi_reversal_sell).then(pl.lit("RSI_REVERSAL"))
              .otherwise(pl.col("signal_type"))
              .alias("signal_type")
        ])

        macd_buy = (
            pl.col("macd_cross_up") &
            pl.col("uptrend") &
            (pl.col("rsi") < 65) &
            (pl.col("raw_signal") == 0)
        )
        macd_sell = (
            pl.col("macd_cross_down") &
            pl.col("downtrend") &
            (pl.col("rsi") > 35) &
            (pl.col("raw_signal") == 0)
        )

        df = df.with_columns([
            pl.when(macd_buy).then(1)
              .when(macd_sell).then(-1)
              .otherwise(pl.col("raw_signal"))
              .alias("raw_signal"),
            pl.when(macd_buy | macd_sell).then(pl.lit("MACD"))
              .otherwise(pl.col("signal_type"))
              .alias("signal_type")
        ])

        # 7. Signal Quality Scoring
        df = df.with_columns(
            pl.lit(0.0)
            .add(pl.when(pl.col("raw_signal") != 0).then(30).otherwise(0))
            .add(pl.when((pl.col("raw_signal") == 1) & pl.col("uptrend")).then(20)
                 .when((pl.col("raw_signal") == -1) & pl.col("downtrend")).then(20)
                 .otherwise(0))
            .add(pl.when(pl.col("rsi").is_between(45, 55)).then(15).otherwise(0))
            .add(pl.when(pl.col("momentum_5").abs() > 0.02).then(15).otherwise(0))
            .add(pl.when((pl.col("raw_signal") == 1) & (pl.col("macd_hist") > 0)).then(10)
                 .when((pl.col("raw_signal") == -1) & (pl.col("macd_hist") < 0)).then(10)
                 .otherwise(0))
            .add(pl.when((pl.col("raw_signal") != 0) & (pl.col("volume_ratio") > 1.2)).then(10)
                 .otherwise(0))
            .alias("signal_quality")
        )

        # 8. Final Signal with quality filter
        df = df.with_columns(pl.lit(0).alias("signal"))

        high_quality = pl.col("signal_quality") >= config["min_signal_quality"]

        df = df.with_columns(
            pl.when(pl.col("raw_signal") == 1)
              .then(pl.when(high_quality).then(1).otherwise(0))
              .when(pl.col("raw_signal") == -1)
              .then(pl.when(high_quality).then(-1).otherwise(0))
              .otherwise(pl.col("signal"))
              .alias("signal")
        )

        # 9. Risk Management Levels
        df = df.with_columns([
            pl.lit(None).alias("stop_loss"),
            pl.lit(None).alias("take_profit"),
            pl.lit(None).alias("trailing_stop")
        ])

        # Long positions
        long_mask = pl.col("signal") == 1
        df = df.with_columns([
            pl.when(long_mask)
              .then(pl.col("close") - config["atr_multiplier_sl"] * pl.col("atr"))
              .otherwise(pl.col("stop_loss"))
              .alias("stop_loss"),
            pl.when(long_mask)
              .then(pl.col("close") + config["atr_multiplier_tp"] * pl.col("atr"))
              .otherwise(pl.col("take_profit"))
              .alias("take_profit"),
            pl.when(long_mask)
              .then(pl.col("close") - config["atr_multiplier_trailing"] * pl.col("atr"))
              .otherwise(pl.col("trailing_stop"))
              .alias("trailing_stop")
        ])

        # Short positions
        short_mask = pl.col("signal") == -1
        df = df.with_columns([
            pl.when(short_mask)
              .then(pl.col("close") + config["atr_multiplier_sl"] * pl.col("atr"))
              .otherwise(pl.col("stop_loss"))
              .alias("stop_loss"),
            pl.when(short_mask)
              .then(pl.col("close") - config["atr_multiplier_tp"] * pl.col("atr"))
              .otherwise(pl.col("take_profit"))
              .alias("take_profit"),
            pl.when(short_mask)
              .then(pl.col("close") + config["atr_multiplier_trailing"] * pl.col("atr"))
              .otherwise(pl.col("trailing_stop"))
              .alias("trailing_stop")
        ])

        # Position sizing
        risk_per_trade = config.get("risk_per_trade", 0.015)
        df = df.with_columns(
            ((risk_per_trade * pl.col("close")) / (config["atr_multiplier_sl"] * pl.col("atr")))
            .clip(0.03, 0.15)
            .alias("position_size_pct")
        )

        return df
        
    except Exception as e:
        logging.error(f"Error in enhanced_strategy: {e}", exc_info=True)
        # Return DataFrame with neutral signal if strategy fails
        if "signal" not in df.columns:
            df = df.with_columns(pl.lit(0).alias("signal"))
        return df


def get_default_config() -> dict:
    """
    Get default strategy configuration.
    
    Returns:
        Dictionary with default strategy parameters
    """
    return {
        "fast_ma": 20,
        "slow_ma": 50,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "atr_period": 14,
        "atr_multiplier_sl": 1.5,
        "atr_multiplier_tp": 3.0,
        "atr_multiplier_trailing": 1.0,
        "min_volume_ratio": 1.5,
        "use_volume_filter": True,
        "min_signal_quality": 50,
        "risk_per_trade": 0.015
    }


def load_strategy_config(config_path: str = None) -> dict:
    """
    Load strategy configuration from file with fallback to defaults.
    
    Args:
        config_path: Optional path to config file (default: data/risk_config.json)
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = Path("data") / "risk_config.json"
    else:
        config_path = Path(config_path)
    
    default_config = get_default_config()
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # Merge user config with defaults
                default_config.update(user_config)
                logging.info(f"Loaded strategy config from {config_path}")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in config file {config_path}: {e}")
        except Exception as e:
            logging.error(f"Error loading config from {config_path}: {e}")
    else:
        logging.info(f"Config file not found at {config_path}, using defaults")
    
    return default_config


def save_strategy_config(config: dict, config_path: str = None) -> bool:
    """
    Save strategy configuration to file.
    
    Args:
        config: Configuration dictionary to save
        config_path: Optional path to save config (default: data/risk_config.json)
        
    Returns:
        True if successful, False otherwise
    """
    if config_path is None:
        config_path = Path("data") / "risk_config.json"
    else:
        config_path = Path(config_path)
    
    try:
        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logging.info(f"Saved strategy config to {config_path}")
        return True
        
    except Exception as e:
        logging.error(f"Error saving config to {config_path}: {e}")
        return False


if __name__ == "__main__":
    print("Balanced Trading Strategy - Loaded")
    print("\nDefault Configuration:")
    config = get_default_config()
    for key, value in config.items():
        print(f"  {key}: {value}")
