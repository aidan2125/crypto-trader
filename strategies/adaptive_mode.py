"""
strategies/adaptive_mode.py

Adaptive strategy mode selection for crypto trading bot.
Selects the best mode (balanced / strict) per symbol, either from an
explicit CLI flag or via asset overrides and volatility heuristics.

Rules
-----
- Explicit mode (testing / balanced / strict) → returned as-is.
- "auto" + symbol in ASSET_OVERRIDES → use override.
- "auto" + symbol not in overrides → derive from ATR %.
- If ATR is unavailable → default to "strict" (safer than "balanced").
- Non-BTC symbols in "auto" mode are NEVER assigned "testing".
"""

from __future__ import annotations

import polars as pl


# ── Asset-level overrides ─────────────────────────────────────────────────────
# Every coin that should always get a fixed mode regardless of volatility.
ASSET_OVERRIDES: dict[str, str] = {
    "BTC/USDT": "balanced",
    "ETH/USDT": "strict",
    "LTC/USDT": "strict",
    "ADA/USDT": "strict",
    "DOT/USDT": "strict",
    "XRP/USDT": "strict",   # ← added
}

# ── Volatility thresholds ─────────────────────────────────────────────────────
ATR_STRICT_THRESHOLD: float = 0.02   # atr/close > 2 %  →  strict
ATR_LOOKBACK: int = 50               # candles used for the recent-average

VALID_MODES = {"testing", "balanced", "strict", "auto"}


# ─────────────────────────────────────────────────────────────────────────────
def choose_strategy_mode(
    symbol: str,
    df: pl.DataFrame,
    requested_mode: str = "auto",
) -> str:
    """
    Return the resolved strategy mode for *symbol*.

    Parameters
    ----------
    symbol:
        Trading pair, e.g. "BTC/USDT".
    df:
        DataFrame that MUST already contain 'atr' and 'close' columns
        (i.e. enhanced_strategy has already been called in indicator-pass mode).
        Only required when *requested_mode* is "auto".
    requested_mode:
        One of "auto" | "testing" | "balanced" | "strict".
        Anything other than "auto" is returned unchanged after validation.

    Returns
    -------
    str – The resolved mode name ("testing" | "balanced" | "strict").
    """
    requested_mode = requested_mode.lower().strip()

    if requested_mode not in VALID_MODES:
        raise ValueError(
            f"Unknown mode '{requested_mode}'. "
            f"Valid options: {sorted(VALID_MODES)}"
        )

    # ── Pass-through: explicit user choice ────────────────────────────────────
    if requested_mode != "auto":
        _print_decision(
            symbol=symbol,
            requested=requested_mode,
            selected=requested_mode,
            reason="user-specified",
            atr_pct=None,
        )
        return requested_mode

    # ── Auto: asset override takes priority ───────────────────────────────────
    if symbol in ASSET_OVERRIDES:
        selected = ASSET_OVERRIDES[symbol]
        _print_decision(
            symbol=symbol,
            requested="auto",
            selected=selected,
            reason=f"{symbol} override",
            atr_pct=_compute_atr_pct(df),   # still print ATR% for visibility
        )
        return selected

    # ── Auto: volatility fallback ─────────────────────────────────────────────
    selected, reason, atr_pct = _volatility_mode(df)

    # Safety guard: non-BTC symbols must never be "testing" in auto mode
    if selected == "testing" and symbol != "BTC/USDT":
        selected = "balanced"
        reason += " (testing blocked for altcoin → balanced)"

    _print_decision(
        symbol=symbol,
        requested="auto",
        selected=selected,
        reason=reason,
        atr_pct=atr_pct,
    )
    return selected


# ─────────────────────────────────────────────────────────────────────────────
def _compute_atr_pct(df: pl.DataFrame) -> float | None:
    """Return recent mean ATR % or None if columns are missing / all-null."""
    if "atr" not in df.columns or "close" not in df.columns:
        return None
    recent = df.tail(ATR_LOOKBACK)
    val = (
        recent
        .select((pl.col("atr") / pl.col("close")).alias("atr_pct"))
        .mean()
        .item(0, "atr_pct")
    )
    return float(val) if val is not None else None


def _volatility_mode(df: pl.DataFrame) -> tuple[str, str, float | None]:
    """
    Derive mode from recent ATR %.

    Returns (mode, human-readable reason, atr_pct_or_None).
    """
    required = {"atr", "close"}
    missing = required - set(df.columns)

    if missing:
        # ATR unavailable → strict is safer than balanced
        return (
            "strict",
            f"missing ATR/close columns — defaulted to strict for safety",
            None,
        )

    atr_pct = _compute_atr_pct(df)

    if atr_pct is None:
        return (
            "strict",
            "atr_pct unavailable — defaulted to strict for safety",
            None,
        )

    if atr_pct > ATR_STRICT_THRESHOLD:
        return (
            "strict",
            f"high volatility (atr_pct={atr_pct:.4f} > {ATR_STRICT_THRESHOLD})",
            atr_pct,
        )

    return (
        "balanced",
        f"normal volatility (atr_pct={atr_pct:.4f} ≤ {ATR_STRICT_THRESHOLD})",
        atr_pct,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _print_decision(
    symbol: str,
    requested: str,
    selected: str,
    reason: str,
    atr_pct: float | None,
) -> None:
    """Print a consistent, human-readable mode-selection block."""
    w = 15
    atr_str = f"{atr_pct:.4f}" if atr_pct is not None else "unavailable"
    print(
        f"\n{'─' * 45}\n"
        f"{'Symbol':<{w}}: {symbol}\n"
        f"{'Requested Mode':<{w}}: {requested}\n"
        f"{'Selected Mode':<{w}}: {selected}\n"
        f"{'Reason':<{w}}: {reason}\n"
        f"{'ATR %':<{w}}: {atr_str}\n"
        f"{'─' * 45}"
    )