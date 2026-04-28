#!/usr/bin/env python3
"""
Enhanced Signals Strategy (Refactored)
---------------------------------------
Event-based, candle-level trading strategy using RSI, MACD, MA crossover,
ATR risk management, and volume confirmation.

Supports three operating modes:
  - testing  : loosest thresholds, most signals
  - balanced : moderate filtering (default)
  - strict   : tightest filtering, fewest signals

New in this version:
  - Full market regime detection (TRENDING / CHOPPY / HIGH_VOLATILITY / LOW_VOLATILITY)
  - market_quality_ok gates entries on BOTH trend strength AND volatility bounds
  - volatility_pct column exposed for downstream diagnostics

Usage:
    df_out = new_strategy(df, mode="balanced")
"""

from __future__ import annotations

import polars as pl


# ──────────────────────────────────────────────────────────────────────────────
# Mode configuration
# ──────────────────────────────────────────────────────────────────────────────

_MODE_CONFIG: dict[str, dict] = {
    "testing": {
        "min_signal_quality":    25,
        "volume_ratio_soft":     0.7,
        "rsi_oversold":          45,
        "rsi_overbought":        55,
        "atr_sl_mult":           1.5,
        "atr_tp_mult":           2.5,
        "atr_trail_mult":        1.2,
        "position_size_pct":     0.05,
        # Regime thresholds
        "min_trend_strength":    0.002,   # |ma_fast - ma_slow| / close
        "min_volatility_pct":    0.002,   # atr / close lower bound
        "max_volatility_pct":    0.030,   # atr / close upper bound
    },
    "balanced": {
        "min_signal_quality":    40,
        "volume_ratio_soft":     0.9,
        "rsi_oversold":          40,
        "rsi_overbought":        60,
        "atr_sl_mult":           1.8,
        "atr_tp_mult":           3.0,
        "atr_trail_mult":        1.5,
        "position_size_pct":     0.03,
        "min_trend_strength":    0.004,
        "min_volatility_pct":    0.003,
        "max_volatility_pct":    0.025,
    },
    "strict": {
        "min_signal_quality":    60,
        "volume_ratio_soft":     1.1,
        "rsi_oversold":          35,
        "rsi_overbought":        65,
        "atr_sl_mult":           2.0,
        "atr_tp_mult":           3.5,
        "atr_trail_mult":        1.8,
        "position_size_pct":     0.02,
        "min_trend_strength":    0.004,
        "min_volatility_pct":    0.004,
        "max_volatility_pct":    0.030,
    },
}

# Regime label constants
_REGIME_TRENDING       = "TRENDING"
_REGIME_CHOPPY         = "CHOPPY"
_REGIME_HIGH_VOL       = "HIGH_VOLATILITY"
_REGIME_LOW_VOL        = "LOW_VOLATILITY"


# ──────────────────────────────────────────────────────────────────────────────
# Indicator helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ema(series: pl.Series, period: int) -> pl.Series:
    """Exponential moving average (pandas-compatible ewm formula)."""
    k = 2.0 / (period + 1)
    values = series.to_list()
    result: list[float | None] = [None] * len(values)
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None:
        return pl.Series(result, dtype=pl.Float64)
    result[start] = float(values[start])
    for i in range(start + 1, len(values)):
        if values[i] is None:
            result[i] = result[i - 1]
        else:
            result[i] = float(values[i]) * k + (result[i - 1] or 0.0) * (1 - k)
    return pl.Series(result, dtype=pl.Float64)


def _sma(series: pl.Series, period: int) -> pl.Series:
    return series.cast(pl.Float64).rolling_mean(window_size=period)


def _rsi(close: pl.Series, period: int = 14) -> pl.Series:
    delta    = close.cast(pl.Float64).diff()
    gain     = delta.map_elements(lambda x: x if x > 0 else 0.0, return_dtype=pl.Float64)
    loss     = delta.map_elements(lambda x: -x if x < 0 else 0.0, return_dtype=pl.Float64)
    avg_gain = gain.rolling_mean(window_size=period)
    avg_loss = loss.rolling_mean(window_size=period)
    rs       = avg_gain / avg_loss.map_elements(
        lambda x: x if x != 0.0 else 1e-10, return_dtype=pl.Float64
    )
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(high: pl.Series, low: pl.Series, close: pl.Series, period: int = 14) -> pl.Series:
    prev_close = close.shift(1)
    tr = pl.Series([
        max(h - l, abs(h - pc), abs(l - pc)) if pc is not None else h - l
        for h, l, pc in zip(high.to_list(), low.to_list(), prev_close.to_list())
    ], dtype=pl.Float64)
    return tr.rolling_mean(window_size=period)


def _macd(
    close: pl.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pl.Series, pl.Series, pl.Series]:
    ema_fast    = _ema(close, fast)
    ema_slow    = _ema(close, slow)
    macd_line   = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


# ──────────────────────────────────────────────────────────────────────────────
# Signal quality scoring
# ──────────────────────────────────────────────────────────────────────────────

def _score_long(
    rsi_val: float | None,
    volume_ratio_val: float | None,
    macd_hist_val: float | None,
    uptrend_val: bool,
    cfg: dict,
) -> float:
    """Score a candidate long setup 0–100. Soft factors add points."""
    score = 40.0
    if rsi_val is not None:
        if rsi_val < cfg["rsi_oversold"]:
            score += 20.0
        elif rsi_val < 50:
            score += 8.0
    if volume_ratio_val is not None:
        if volume_ratio_val > cfg["volume_ratio_soft"]:
            score += 15.0
        elif volume_ratio_val > 0.8:
            score += 5.0
    if macd_hist_val is not None and macd_hist_val > 0:
        score += 15.0
    if uptrend_val:
        score += 10.0
    return min(score, 100.0)


def _score_short(
    rsi_val: float | None,
    volume_ratio_val: float | None,
    macd_hist_val: float | None,
    downtrend_val: bool,
    cfg: dict,
) -> float:
    """Score a candidate short setup 0–100. Soft factors add points."""
    score = 40.0
    if rsi_val is not None:
        if rsi_val > cfg["rsi_overbought"]:
            score += 20.0
        elif rsi_val > 50:
            score += 8.0
    if volume_ratio_val is not None:
        if volume_ratio_val > cfg["volume_ratio_soft"]:
            score += 15.0
        elif volume_ratio_val > 0.8:
            score += 5.0
    if macd_hist_val is not None and macd_hist_val < 0:
        score += 15.0
    if downtrend_val:
        score += 10.0
    return min(score, 100.0)


# ──────────────────────────────────────────────────────────────────────────────
# Main strategy function
# ──────────────────────────────────────────────────────────────────────────────

def enhanced_strategy(
    df: pl.DataFrame,
    config: dict = None,  # noqa: ARG001 — reserved
    mode: str = "balanced",
) -> pl.DataFrame:
    """
    Event-based trading strategy with market regime detection.

    Parameters
    ----------
    df     : Polars DataFrame with columns: open, high, low, close, volume
    config : Reserved. Pass None; use `mode` to control behaviour.
    mode   : "testing" | "balanced" | "strict"

    Returns
    -------
    Polars DataFrame with all original columns plus signal and regime columns.

    New output columns vs previous version
    ----------------------------------------
    volatility_pct   : atr / close  (float)
    market_regime    : "TRENDING" | "CHOPPY" | "HIGH_VOLATILITY" | "LOW_VOLATILITY"
    market_quality_ok: True only when regime == TRENDING
    trend_strength   : |ma_fast - ma_slow| / close  (float, unchanged)
    """
    if mode not in _MODE_CONFIG:
        raise ValueError(f"Invalid mode '{mode}'. Choose from: {list(_MODE_CONFIG)}")

    cfg = _MODE_CONFIG[mode]
    n   = df.height

    close  = df["close"].cast(pl.Float64)
    high   = df["high"].cast(pl.Float64)
    low    = df["low"].cast(pl.Float64)
    volume = df["volume"].cast(pl.Float64)

    # ── Indicators ────────────────────────────────────────────────────────────
    ma_fast  = _sma(close, 20)
    ma_slow  = _sma(close, 50)
    ema_trend = _ema(close, 200)
    rsi      = _rsi(close, 14)
    atr      = _atr(high, low, close, 14)
    macd_line, macd_sig, macd_hist = _macd(close)

    vol_sma = _sma(volume, 20)
    volume_ratio = pl.Series([
        v / s if (s is not None and s > 0) else None
        for v, s in zip(volume.to_list(), vol_sma.to_list())
    ], dtype=pl.Float64)

    ma_fast_list   = ma_fast.to_list()
    ma_slow_list   = ma_slow.to_list()
    ema_list       = ema_trend.to_list()
    close_list     = close.to_list()
    rsi_list       = rsi.to_list()
    atr_list       = atr.to_list()
    macd_list      = macd_line.to_list()
    macd_sig_list  = macd_sig.to_list()
    macd_hist_list = macd_hist.to_list()
    vol_ratio_list = volume_ratio.to_list()

    # ── Trend direction (EMA 200) ─────────────────────────────────────────────
    uptrend_list: list[bool] = [
        (c is not None and e is not None and c > e)
        for c, e in zip(close_list, ema_list)
    ]
    downtrend_list: list[bool] = [
        (c is not None and e is not None and c < e)
        for c, e in zip(close_list, ema_list)
    ]

    # ── Trend strength = |ma_fast - ma_slow| / close ─────────────────────────
    trend_strength_list: list[float] = [
        abs(maf - mas) / c
        if (maf is not None and mas is not None and c is not None and c != 0)
        else 0.0
        for maf, mas, c in zip(ma_fast_list, ma_slow_list, close_list)
    ]

    # ── Volatility = atr / close ──────────────────────────────────────────────
    volatility_pct_list: list[float] = [
        a / c if (a is not None and c is not None and c != 0) else 0.0
        for a, c in zip(atr_list, close_list)
    ]

    # ── Market regime classification ──────────────────────────────────────────
    # TRENDING        : trend_strength meets minimum AND volatility in acceptable range
    # CHOPPY          : trend_strength too low (MAs tangled)
    # HIGH_VOLATILITY : volatility too high (runaway / spike conditions)
    # LOW_VOLATILITY  : volatility too low (dead market, no meaningful moves)

    min_ts  = cfg["min_trend_strength"]
    min_vol = cfg["min_volatility_pct"]
    max_vol = cfg["max_volatility_pct"]

    market_regime_list: list[str] = []
    market_quality_ok_list: list[bool] = []

    for ts, vp in zip(trend_strength_list, volatility_pct_list):
        if vp > max_vol:
            regime = _REGIME_HIGH_VOL
        elif vp < min_vol:
            regime = _REGIME_LOW_VOL
        elif ts < min_ts:
            regime = _REGIME_CHOPPY
        else:
            regime = _REGIME_TRENDING
        market_regime_list.append(regime)
        market_quality_ok_list.append(regime == _REGIME_TRENDING)

    # ── Raw setup detection (candle-event, non-persistent) ────────────────────
    #
    # 2-of-3 confirmation: any two of {MA crossover, MACD crossover, RSI reversal}
    # must agree. Entry is additionally gated by market_quality_ok.

    raw_long_list:  list[bool] = [False] * n
    raw_short_list: list[bool] = [False] * n

    for i in range(1, n):
        maf_cur  = ma_fast_list[i];    maf_prev = ma_fast_list[i - 1]
        mas_cur  = ma_slow_list[i];    mas_prev = ma_slow_list[i - 1]
        macd_cur = macd_list[i];       macd_p   = macd_list[i - 1]
        msig_cur = macd_sig_list[i];   msig_p   = macd_sig_list[i - 1]
        rsi_cur  = rsi_list[i];        rsi_prev = rsi_list[i - 1]

        # MA crossover
        ma_golden = (
            maf_cur is not None and maf_prev is not None and
            mas_cur is not None and mas_prev is not None and
            maf_prev <= mas_prev and maf_cur > mas_cur
        )
        ma_death = (
            maf_cur is not None and maf_prev is not None and
            mas_cur is not None and mas_prev is not None and
            maf_prev >= mas_prev and maf_cur < mas_cur
        )

        # MACD crossover
        macd_bull = (
            macd_cur is not None and macd_p is not None and
            msig_cur is not None and msig_p is not None and
            macd_p <= msig_p and macd_cur > msig_cur
        )
        macd_bear = (
            macd_cur is not None and macd_p is not None and
            msig_cur is not None and msig_p is not None and
            macd_p >= msig_p and macd_cur < msig_cur
        )

        # RSI reversal (threshold crossing, trend-filtered)
        rsi_bull_raw = (
            rsi_cur is not None and rsi_prev is not None and
            rsi_prev < cfg["rsi_oversold"] and rsi_cur >= cfg["rsi_oversold"]
        )
        rsi_bear_raw = (
            rsi_cur is not None and rsi_prev is not None and
            rsi_prev > cfg["rsi_overbought"] and rsi_cur <= cfg["rsi_overbought"]
        )
        rsi_bull_valid = rsi_bull_raw and uptrend_list[i]
        rsi_bear_valid = rsi_bear_raw and downtrend_list[i]

        # Balanced confirmation:
        # - Keep strong trend-following entries: MA + MACD
        # - Allow RSI reversal entries only when RSI crosses back from extremes
        # - Still protected by market_quality_ok below
        long_confirmed = (
            (ma_golden and macd_bull)
            or rsi_bull_valid
        )
        short_confirmed = (
            (ma_death and macd_bear)
            or rsi_bear_valid
        )

        # Market quality gate: block entries outside TRENDING regime
        raw_long_list[i]  = market_quality_ok_list[i] and long_confirmed
        raw_short_list[i] = market_quality_ok_list[i] and short_confirmed

    # ── Signal type label ─────────────────────────────────────────────────────

    def _signal_type(i: int, direction: str) -> str:
        maf_cur  = ma_fast_list[i]
        maf_prev = ma_fast_list[i - 1] if i > 0 else None
        mas_cur  = ma_slow_list[i]
        mas_prev = ma_slow_list[i - 1] if i > 0 else None
        macd_cur = macd_list[i]
        macd_p   = macd_list[i - 1] if i > 0 else None
        msig_cur = macd_sig_list[i]
        msig_p   = macd_sig_list[i - 1] if i > 0 else None
        rsi_cur  = rsi_list[i]
        rsi_prev = rsi_list[i - 1] if i > 0 else None

        if direction == "long":
            ma_cross   = (maf_cur and maf_prev and mas_cur and mas_prev and
                          maf_prev <= mas_prev and maf_cur > mas_cur)
            macd_cross = (macd_cur and macd_p and msig_cur and msig_p and
                          macd_p <= msig_p and macd_cur > msig_cur)
            rsi_rev    = (rsi_cur and rsi_prev and
                          rsi_prev < cfg["rsi_oversold"] and rsi_cur >= cfg["rsi_oversold"])
        else:
            ma_cross   = (maf_cur and maf_prev and mas_cur and mas_prev and
                          maf_prev >= mas_prev and maf_cur < mas_cur)
            macd_cross = (macd_cur and macd_p and msig_cur and msig_p and
                          macd_p >= msig_p and macd_cur < msig_cur)
            rsi_rev    = (rsi_cur and rsi_prev and
                          rsi_prev > cfg["rsi_overbought"] and rsi_cur <= cfg["rsi_overbought"])

        parts = []
        if ma_cross:   parts.append("MA")
        if macd_cross: parts.append("MACD")
        if rsi_rev:    parts.append("RSI")
        return "+".join(parts) if parts else "UNKNOWN"

    # ── Quality score, filtering, and final entry events ─────────────────────

    enter_long_list:   list[bool]         = [False] * n
    enter_short_list:  list[bool]         = [False] * n
    signal_list:       list[int]          = [0] * n
    sig_type_list:     list[str]          = ["NONE"] * n
    quality_list:      list[float]        = [0.0] * n
    trade_ready_list:  list[bool]         = [False] * n
    trade_reason_list: list[str]          = ["NO_SIGNAL"] * n
    stop_loss_list:    list[float | None] = [None] * n
    take_profit_list:  list[float | None] = [None] * n
    trailing_stop_list:list[float | None] = [None] * n
    position_size_list:list[float]        = [cfg["position_size_pct"]] * n

    for i in range(n):
        c       = close_list[i]
        atr_val = atr_list[i]

        if raw_long_list[i]:
            quality  = _score_long(rsi_list[i], vol_ratio_list[i],
                                   macd_hist_list[i], uptrend_list[i], cfg)
            sig_type = _signal_type(i, "long")
            quality_list[i]     = quality
            sig_type_list[i]    = sig_type
            trade_ready_list[i] = True

            if quality < cfg["min_signal_quality"]:
                trade_reason_list[i] = f"LOW_QUALITY({quality:.0f})"
                trade_ready_list[i]  = False
            else:
                trade_reason_list[i] = "OK"
                enter_long_list[i]   = True
                signal_list[i]       = 1
                if c is not None and atr_val is not None:
                    stop_loss_list[i]      = c - cfg["atr_sl_mult"]    * atr_val
                    take_profit_list[i]    = c + cfg["atr_tp_mult"]    * atr_val
                    trailing_stop_list[i]  = c - cfg["atr_trail_mult"] * atr_val

        elif raw_short_list[i]:
            quality  = _score_short(rsi_list[i], vol_ratio_list[i],
                                    macd_hist_list[i], downtrend_list[i], cfg)
            sig_type = _signal_type(i, "short")
            quality_list[i]     = quality
            sig_type_list[i]    = sig_type
            trade_ready_list[i] = True

            if quality < cfg["min_signal_quality"]:
                trade_reason_list[i] = f"LOW_QUALITY({quality:.0f})"
                trade_ready_list[i]  = False
            else:
                trade_reason_list[i] = "OK"
                enter_short_list[i]  = True
                signal_list[i]       = -1
                if c is not None and atr_val is not None:
                    stop_loss_list[i]      = c + cfg["atr_sl_mult"]    * atr_val
                    take_profit_list[i]    = c - cfg["atr_tp_mult"]    * atr_val
                    trailing_stop_list[i]  = c + cfg["atr_trail_mult"] * atr_val

    # ── Exit columns (not used by BacktestPro — SL/TP only — kept for compatibility)
    exit_long_list:  list[bool] = [False] * n
    exit_short_list: list[bool] = [False] * n

    # ── Assemble result dataframe ─────────────────────────────────────────────
    result = df.with_columns([
        # Core indicators
        pl.Series("ma_fast",        ma_fast_list,        dtype=pl.Float64),
        pl.Series("ma_slow",        ma_slow_list,        dtype=pl.Float64),
        pl.Series("rsi",            rsi_list,            dtype=pl.Float64),
        pl.Series("atr",            atr_list,            dtype=pl.Float64),
        pl.Series("macd",           macd_list,           dtype=pl.Float64),
        pl.Series("macd_signal",    macd_sig_list,       dtype=pl.Float64),
        pl.Series("macd_hist",      macd_hist_list,      dtype=pl.Float64),
        pl.Series("volume_ratio",   vol_ratio_list,      dtype=pl.Float64),
        # Trend & regime
        pl.Series("uptrend",          uptrend_list,           dtype=pl.Boolean),
        pl.Series("downtrend",        downtrend_list,         dtype=pl.Boolean),
        pl.Series("trend_strength",   trend_strength_list,    dtype=pl.Float64),
        pl.Series("volatility_pct",   volatility_pct_list,    dtype=pl.Float64),
        pl.Series("market_regime",    market_regime_list,     dtype=pl.Utf8),
        pl.Series("market_quality_ok",market_quality_ok_list, dtype=pl.Boolean),
        # Raw setups
        pl.Series("enter_long_raw",  raw_long_list,  dtype=pl.Boolean),
        pl.Series("enter_short_raw", raw_short_list, dtype=pl.Boolean),
        # Signal metadata
        pl.Series("signal",         signal_list,        dtype=pl.Int8),
        pl.Series("signal_type",    sig_type_list,      dtype=pl.Utf8),
        pl.Series("signal_quality", quality_list,       dtype=pl.Float64),
        pl.Series("trade_ready",    trade_ready_list,   dtype=pl.Boolean),
        pl.Series("trade_reason",   trade_reason_list,  dtype=pl.Utf8),
        # Entry / exit events
        pl.Series("enter_long",  enter_long_list,  dtype=pl.Boolean),
        pl.Series("enter_short", enter_short_list, dtype=pl.Boolean),
        pl.Series("exit_long",   exit_long_list,   dtype=pl.Boolean),
        pl.Series("exit_short",  exit_short_list,  dtype=pl.Boolean),
        # Risk management
        pl.Series("stop_loss",         stop_loss_list,      dtype=pl.Float64),
        pl.Series("take_profit",        take_profit_list,    dtype=pl.Float64),
        pl.Series("trailing_stop",      trailing_stop_list,  dtype=pl.Float64),
        pl.Series("position_size_pct",  position_size_list,  dtype=pl.Float64),
    ])

    return result