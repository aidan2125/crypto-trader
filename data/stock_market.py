"""
data/stock_market_data.py
Fetches OHLCV data for stocks using yfinance.
Returns a Polars DataFrame in the exact same format as fetch_ohlcv()
so enhanced_signals.py works with zero changes.
"""

import logging
import pandas as pd
import polars as pl
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    raise ImportError("Install yfinance: pip install yfinance")

# Interval map — mirrors your existing timeframe strings
INTERVAL_MAP = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "60m",   # yfinance uses "60m" not "1h"
    "4h":  "1h",    # yfinance max granularity; use 1h and aggregate if needed
    "1d":  "1d",
}


def fetch_stock_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 500,
) -> pl.DataFrame | None:
    """
    Fetch OHLCV candles for a stock ticker from yfinance.

    Args:
        symbol:    Ticker string e.g. "TQQQ", "NVDA", "TSLA", "COIN"
        timeframe: Candle size — "1m","5m","15m","30m","1h","1d"
        limit:     Number of candles to return (approximate — yfinance works
                   on date ranges, so we trim to `limit` rows at the end)

    Returns:
        Polars DataFrame with columns: timestamp, open, high, low, close, volume
        Returns None on failure (same contract as fetch_ohlcv).
    """
    try:
        yf_interval = INTERVAL_MAP.get(timeframe, "60m")

        # Work out a safe period string from limit + interval
        period = _limit_to_period(timeframe, limit)

        ticker = yf.Ticker(symbol)
        df_pd: pd.DataFrame = ticker.history(period=period, interval=yf_interval)

        if df_pd is None or df_pd.empty:
            logging.warning(f"[stock_market_data] No data returned for {symbol}")
            return None

        # yfinance returns a timezone-aware DatetimeIndex — flatten to UTC epoch ms
        df_pd = df_pd.reset_index()

        # Column name varies by yfinance version ("Datetime" vs "Date")
        time_col = "Datetime" if "Datetime" in df_pd.columns else "Date"

        df_pd = df_pd.rename(columns={
            time_col: "timestamp",
            "Open":   "open",
            "High":   "high",
            "Low":    "low",
            "Close":  "close",
            "Volume": "volume",
        })

        # Keep only the columns your strategy needs
        df_pd = df_pd[["timestamp", "open", "high", "low", "close", "volume"]]

        # Convert timestamp to UTC-naive datetime (Polars friendly)
        df_pd["timestamp"] = pd.to_datetime(df_pd["timestamp"], utc=True).dt.tz_localize(None)

        # Cast numerics so Polars doesn't complain
        for col in ["open", "high", "low", "close"]:
            df_pd[col] = df_pd[col].astype(float)
        df_pd["volume"] = df_pd["volume"].astype(float)

        # Convert to Polars — same type as fetch_ohlcv output
        df_pl = pl.from_pandas(df_pd)

        # Trim to requested limit (most recent candles)
        if df_pl.height > limit:
            df_pl = df_pl.tail(limit)

        logging.info(f"[stock_market_data] {symbol}: {df_pl.height} candles ({timeframe})")
        return df_pl

    except Exception as e:
        logging.error(f"[stock_market_data] fetch failed for {symbol}: {e}")
        return None


def _limit_to_period(timeframe: str, limit: int) -> str:
    """
    Convert a candle count + timeframe into a yfinance period string.
    yfinance intraday data caps at 60 days; daily caps at 'max'.
    """
    minutes_per_candle = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440,
    }
    mins = minutes_per_candle.get(timeframe, 60)
    total_minutes = mins * limit
    total_days = max(1, total_minutes // (60 * 24))

    # yfinance intraday max lookback is 60 days
    if timeframe in ("1m",):
        total_days = min(total_days, 7)    # 1m data: max 7 days
    elif timeframe in ("5m", "15m", "30m", "1h"):
        total_days = min(total_days, 60)   # intraday: max 60 days

    if total_days <= 7:
        return "7d"
    elif total_days <= 30:
        return "1mo"
    elif total_days <= 60:
        return "60d"
    elif total_days <= 90:
        return "3mo"
    elif total_days <= 180:
        return "6mo"
    else:
        return "1y"