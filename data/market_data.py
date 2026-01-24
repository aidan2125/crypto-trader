"""
Market Data Fetching Module
Fetches OHLCV data from exchange using ccxt and returns Polars DataFrame.
"""

import logging
import os
from typing import Optional

import ccxt
import polars as pl
from datetime import datetime, timezone

# Setup logging
logger = logging.getLogger(__name__)

# Default exchange configuration
DEFAULT_EXCHANGE = "binance"
exchange = getattr(ccxt, DEFAULT_EXCHANGE)({
    'enableRateLimit': True,
    # Uncomment if using authenticated endpoints later
    # 'apiKey': os.getenv('EXCHANGE_API_KEY'),
    # 'secret': os.getenv('EXCHANGE_SECRET'),
})


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 1000,
    since: Optional[int] = None,
    params: dict = None
) -> Optional[pl.DataFrame]:
    """
    Fetch OHLCV data from exchange and return as Polars DataFrame.

    Args:
        symbol: Trading pair (e.g. "BTC/USDT")
        timeframe: Chart interval (e.g. "1m", "5m", "1h", "4h", "1d")
        limit: Number of candles to fetch
        since: Unix timestamp (ms) to start from
        params: Additional exchange parameters

    Returns:
        Polars DataFrame with columns: timestamp, open, high, low, close, volume
        or None on failure
    """
    try:
        logger.info(f"Fetching {limit} {timeframe} candles for {symbol}")

        ohlcv = exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=limit,
            params=params or {}
        )

        if not ohlcv:
            logger.warning(f"No OHLCV data returned for {symbol} {timeframe}")
            return None

        # Create Polars DataFrame with explicit row orientation
        df = pl.DataFrame(
            ohlcv,
            schema=[
                ("timestamp", pl.Int64),   # ms Unix timestamp
                ("open",      pl.Float64),
                ("high",      pl.Float64),
                ("low",       pl.Float64),
                ("close",     pl.Float64),
                ("volume",    pl.Float64),
            ],
            orient="row"
        )

        # Convert timestamp to proper UTC datetime
        df = df.with_columns(
            pl.col("timestamp")
            .cast(pl.Datetime(time_unit="ms", time_zone="UTC"))
            .alias("timestamp")
        )

        # Ensure chronological order
        df = df.sort("timestamp")

        logger.info(f"Successfully fetched {df.height} candles")
        return df

    except ccxt.NetworkError as e:
        logger.error(f"Network error while fetching {symbol}: {e}")
        return None
    except ccxt.ExchangeError as e:
        logger.error(f"Exchange error for {symbol}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching {symbol} {timeframe}: {e}")
        return None


def fetch_multiple_symbols(
    symbols: list[str],
    timeframe: str = "1h",
    limit: int = 1000
) -> dict[str, pl.DataFrame]:
    results = {}
    for symbol in symbols:
        df = fetch_ohlcv(symbol, timeframe, limit)
        if df is not None:
            results[symbol] = df
    return results


# Quick standalone test when run directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example usage
    df = fetch_ohlcv("BTC/USDT", "1h", 100)

    if df is not None:
        print(df.head(5))
        print(f"\nShape: {df.shape}")
        print(f"Columns: {df.columns}")

        # Save to CSV example (using your storage function)
        # from data.storage import save_to_csv
        # save_to_csv(df, "BTC/USDT", "1h")
    else:
        print("Fetch failed")