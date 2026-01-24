"""
Balanced Trading Strategy - Optimized for Real Market Testing
More signals, reasonable filters, good for stress testing
"""

import polars as pl
import json
from pathlib import Path

def calculate_rsi(series: pl.Expr, period: int = 14) -> pl.Expr:
    delta = series.diff()
    gain = delta.clip(lower_bound=0)
    loss = (-delta).clip(lower_bound=0)

    avg_gain = gain.rolling_mean(window_size=period, min_periods=period)
    avg_loss = loss.rolling_mean(window_size=period, min_periods=period)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(df: pl.DataFrame, period: int = 14) -> pl.Expr:
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
    ema_fast = close.ewm_mean(span=fast, adjust=False)
    ema_slow = close.ewm_mean(span=slow, adjust=False)
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm_mean(span=signal, adjust=False)
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def enhanced_strategy(df: pl.DataFrame, config: dict = None) -> pl.DataFrame:
    """
    Balanced Strategy for Real Market Testing
    """
    if config is None:
        config = {
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
            "min_signal_quality": 50
        }

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

    # 7. Signal Quality Scoring – single chained expression (no duplicate error)
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

    # 8. Final Signal – single expression (no duplicate column error)
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

    risk_per_trade = 0.015
    df = df.with_columns(
        ((risk_per_trade * pl.col("close")) / (config["atr_multiplier_sl"] * pl.col("atr")))
        .clip(0.03, 0.15)
        .alias("position_size_pct")
    )

    return df


def load_strategy_config():
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