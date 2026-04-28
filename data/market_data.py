"""
Market Data Fetching Module
Fetches OHLCV data from exchange using ccxt and returns Polars DataFrame.
"""

import logging
import os
import time
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


# ─────────────────────────────────────────────────────────────────────────────
# Timeframe helper
# ─────────────────────────────────────────────────────────────────────────────

_TIMEFRAME_MS: dict[str, int] = {
    "1m":  60_000,
    "3m":  3  * 60_000,
    "5m":  5  * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h":  60 * 60_000,
    "2h":  2  * 60 * 60_000,
    "4h":  4  * 60 * 60_000,
    "6h":  6  * 60 * 60_000,
    "8h":  8  * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d":  24 * 60 * 60_000,
    "3d":  3  * 24 * 60 * 60_000,
    "1w":  7  * 24 * 60 * 60_000,
}


def _timeframe_to_ms(timeframe: str) -> int:
    """
    Convert a timeframe string (e.g. '1h', '15m', '4h', '1d') to milliseconds.
    Raises ValueError for unrecognised strings.
    """
    ms = _TIMEFRAME_MS.get(timeframe.lower())
    if ms is None:
        raise ValueError(
            f"Unrecognised timeframe '{timeframe}'. "
            f"Supported: {list(_TIMEFRAME_MS)}"
        )
    return ms


# ─────────────────────────────────────────────────────────────────────────────
# Main fetch function
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",          # fixed typo: was "41"
    limit: int = 1000,
    since: Optional[int] = None,
    params: dict = None,
) -> Optional[pl.DataFrame]:
    """
    Fetch OHLCV data from the exchange and return as a Polars DataFrame.

    When `limit > 1000` and `since` is None, the function calculates a starting
    timestamp far enough in the past so that paginating *forward* in 1 000-candle
    batches collects exactly `limit` candles.

    Parameters
    ----------
    symbol    : Trading pair, e.g. "BTC/USDT".
    timeframe : Candle interval, e.g. "1h", "15m", "4h", "1d".
    limit     : Total number of candles to return.
    since     : Optional start timestamp in milliseconds (UTC).
                When None the function derives it automatically.
    params    : Extra kwargs forwarded to ccxt.

    Returns
    -------
    Polars DataFrame sorted by timestamp, or None on error.
    """
    try:
        logger.info(f"Fetching {limit} {timeframe} candles for {symbol}")

        timeframe_ms = _timeframe_to_ms(timeframe)
        batch_size   = 1000

        # ── Determine where to start ──────────────────────────────────────────
        # When since is None we calculate a start timestamp so that
        # paginating forward lands us at the most-recent `limit` candles.
        # Without this, a bare fetch_ohlcv call with since=None only ever
        # returns the latest 1 000 candles regardless of `limit`.
        if since is None:
            now_ms     = int(time.time() * 1000)
            fetch_since = now_ms - (limit * timeframe_ms)
        else:
            fetch_since = since

        # ── Paginate forward in batches ───────────────────────────────────────
        all_ohlcv: list[list] = []

        while len(all_ohlcv) < limit:
            remaining     = limit - len(all_ohlcv)
            current_limit = min(batch_size, remaining)

            batch = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=fetch_since,
                limit=current_limit,
                params=params or {},
            )

            if not batch:
                break

            all_ohlcv.extend(batch)

            # Advance the cursor just past the last returned candle's timestamp
            fetch_since = batch[-1][0] + 1

            # Exchange returned fewer candles than asked — we've hit the edge
            if len(batch) < current_limit:
                break

        if not all_ohlcv:
            logger.warning(f"No OHLCV data returned for {symbol} {timeframe}")
            return None

        # ── Deduplicate by timestamp, sort, and trim to limit ─────────────────
        unique: dict[int, list] = {}
        for candle in all_ohlcv:
            unique[candle[0]] = candle

        ohlcv = sorted(unique.values(), key=lambda c: c[0])
        ohlcv = ohlcv[-limit:]   # keep the most-recent `limit` candles

        # ── Build Polars DataFrame ────────────────────────────────────────────
        df = pl.DataFrame(
            ohlcv,
            schema=[
                ("timestamp", pl.Int64),
                ("open",      pl.Float64),
                ("high",      pl.Float64),
                ("low",       pl.Float64),
                ("close",     pl.Float64),
                ("volume",    pl.Float64),
            ],
            orient="row",
        )

        df = df.with_columns(
            pl.col("timestamp")
            .cast(pl.Datetime(time_unit="ms", time_zone="UTC"))
            .alias("timestamp")
        )

        df = df.sort("timestamp")

        print(f"Pagination fetch complete: requested={limit}, received={df.height}")
        logger.info(f"Successfully fetched {df.height} candles for {symbol}")
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


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helper
# ─────────────────────────────────────────────────────────────────────────────

def fetch_multiple_symbols(
    symbols: list[str],
    timeframe: str = "1h",
    limit: int = 1000,
) -> dict[str, pl.DataFrame]:
    results = {}
    for symbol in symbols:
        df = fetch_ohlcv(symbol, timeframe, limit)
        if df is not None:
            results[symbol] = df
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Quick standalone test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    df = fetch_ohlcv("BTC/USDT", "1h", 3000)

    if df is not None:
        print(df.head(5))
        print(f"\nShape:   {df.shape}")
        print(f"Columns: {df.columns}")
    else:
        print("Failed to fetch data.")