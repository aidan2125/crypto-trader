"""
bot/signal_guard.py  —  Pre-scan signal quality guard.

Run this BEFORE the main coin processing loop. It:
  1. Fetches recent OHLCV for every coin in your list
  2. Runs the strategy to get the latest signal_quality score
  3. Ranks coins by score (highest first)
  4. Returns only the coins that pass the minimum threshold
  5. Optionally runs a quick backtest on the top coins to validate

Usage in main_enhanced.py:
    from bot.signal_guard import get_tradeable_coins

    coins = get_tradeable_coins(
        all_coins=list(COIN_CURRENCY.keys()),
        min_quality=60,        # minimum score to be considered
        top_n=4,               # max coins to trade this cycle
        backtest_min_roi=-0.03 # skip coin if quick backtest ROI < -3%
    )
    # Then replace your coin loop:
    for coin in coins:
        run_for_coin(coin)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Defaults (override via .env or function args) ─────────────────────────────
DEFAULT_MIN_QUALITY    = 60    # minimum signal_quality score (0-100)
DEFAULT_TOP_N          = 4     # max coins to trade per cycle
DEFAULT_BACKTEST_CANDLES = 500 # candles for quick backtest validation
DEFAULT_BACKTEST_MIN_ROI = -0.03  # skip coin if quick backtest ROI below -3%


@dataclass
class CoinScore:
    """Holds the scan result for a single coin."""
    coin:           str
    quality:        float         = 0.0
    signal:         int           = 0    # -1 short, 0 hold, 1 long
    price:          float         = 0.0
    atr:            Optional[float] = None
    market_ok:      bool          = False  # market_quality_ok from strategy
    backtest_roi:   Optional[float] = None  # filled if backtest_validation=True
    skip_reason:    str           = ""


def _scan_coin(coin: str, strategy_mode: str = "strict") -> CoinScore:
    """
    Fetch data for one coin, run the strategy, return its CoinScore.
    Returns a zero-score CoinScore on any error so the coin is naturally
    ranked last and filtered out.
    """
    # Import here to avoid circular imports at module level
    from data.market_data import fetch_ohlcv
    from strategies.enhanced_signals_refactored import enhanced_strategy

    result = CoinScore(coin=coin)

    try:
        df = fetch_ohlcv(symbol=coin, limit=200)  # 200 candles is enough to score
        if df is None or df.is_empty():
            result.skip_reason = "no data"
            return result

        df = enhanced_strategy(df, mode=strategy_mode)

        if "signal" not in df.columns:
            result.skip_reason = "strategy returned no signal column"
            return result

        last = df.tail(1)

        result.signal  = int(last["signal"][0])   if "signal"         in last.columns else 0
        result.price   = float(last["close"][0])  if "close"          in last.columns else 0.0

        if "signal_quality" in last.columns and last["signal_quality"][0] is not None:
            result.quality = float(last["signal_quality"][0])

        if "atr" in last.columns and last["atr"][0] is not None:
            result.atr = float(last["atr"][0])

        if "market_quality_ok" in last.columns and last["market_quality_ok"][0] is not None:
            result.market_ok = bool(last["market_quality_ok"][0])

    except Exception as e:
        result.skip_reason = f"scan error: {e}"
        logger.warning(f"[signal_guard] {coin} scan failed: {e}")

    return result


def _quick_backtest_roi(coin: str, candles: int = DEFAULT_BACKTEST_CANDLES) -> Optional[float]:
    """
    Run a minimal backtest on `candles` of recent data.
    Returns ROI as a decimal (e.g. -0.05 = -5%) or None on failure.
    """
    try:
        from data.market_data import fetch_ohlcv
        from backtest.run_backtest_simple import BacktestPro

        df = fetch_ohlcv(symbol=coin, limit=candles)
        if df is None or df.is_empty():
            return None

        bt = BacktestPro(initial_balance=10_000)
        result = bt.run(df, symbol=coin)

        if result and "roi" in result:
            return float(result["roi"])
        # Some BacktestPro implementations return summary dict with different keys
        if result and "ROI" in result:
            return float(result["ROI"]) / 100  # convert % to decimal
        return None

    except Exception as e:
        logger.warning(f"[signal_guard] {coin} quick backtest failed: {e}")
        return None


def get_tradeable_coins(
    all_coins:           list[str],
    min_quality:         float = DEFAULT_MIN_QUALITY,
    top_n:               int   = DEFAULT_TOP_N,
    backtest_validation: bool  = False,
    backtest_min_roi:    float = DEFAULT_BACKTEST_MIN_ROI,
    backtest_candles:    int   = DEFAULT_BACKTEST_CANDLES,
    require_market_ok:   bool  = True,
    strategy_mode:       str   = "strict",
) -> list[str]:
    """
    Scan all coins, rank by signal quality, return the best ones to trade.

    Args:
        all_coins:           Full list of coins to consider (from COIN_CURRENCY)
        min_quality:         Minimum signal_quality score to be eligible (0–100)
        top_n:               Maximum number of coins to return
        backtest_validation: If True, run a quick backtest on each passing coin
                             and skip ones with ROI below backtest_min_roi
        backtest_min_roi:    Minimum acceptable backtest ROI (e.g. -0.03 = -3%)
        backtest_candles:    How many candles to use for quick backtest
        require_market_ok:   If True, also require market_quality_ok == True
        strategy_mode:       Strategy mode passed to enhanced_strategy()

    Returns:
        Ordered list of coin symbols (best quality first), max length top_n.
        Empty list means no coins passed — bot should skip this cycle.
    """
    logger.info(f"[signal_guard] Scanning {len(all_coins)} coins for signal quality...")

    scores: list[CoinScore] = []

    for coin in all_coins:
        score = _scan_coin(coin, strategy_mode=strategy_mode)

        # Filter 1: must have a non-zero signal (not HOLD)
        if score.signal == 0:
            score.skip_reason = score.skip_reason or "signal is HOLD"
            logger.debug(f"[signal_guard] {coin} skipped — HOLD signal")
            scores.append(score)
            continue

        # Filter 2: minimum quality threshold
        if score.quality < min_quality:
            score.skip_reason = f"quality {score.quality:.0f} < {min_quality}"
            logger.debug(f"[signal_guard] {coin} skipped — {score.skip_reason}")
            scores.append(score)
            continue

        # Filter 3: market regime gate (optional)
        if require_market_ok and not score.market_ok:
            score.skip_reason = "market_quality_ok=False (non-trending regime)"
            logger.debug(f"[signal_guard] {coin} skipped — {score.skip_reason}")
            scores.append(score)
            continue

        # Filter 4: quick backtest validation (optional — slower, uses more API calls)
        if backtest_validation:
            roi = _quick_backtest_roi(coin, candles=backtest_candles)
            score.backtest_roi = roi
            if roi is not None and roi < backtest_min_roi:
                score.skip_reason = f"backtest ROI {roi:.1%} < {backtest_min_roi:.1%}"
                logger.debug(f"[signal_guard] {coin} skipped — {score.skip_reason}")
                scores.append(score)
                continue

        scores.append(score)

    # Rank by quality score descending
    eligible = [s for s in scores if not s.skip_reason]
    eligible.sort(key=lambda s: s.quality, reverse=True)

    # Take top N
    selected = eligible[:top_n]

    # ── Summary log ───────────────────────────────────────────────────────────
    skipped = [s for s in scores if s.skip_reason]

    logger.info(f"[signal_guard] ── Scan complete ──")
    logger.info(f"[signal_guard] Eligible: {len(eligible)} / {len(all_coins)} coins")

    if selected:
        logger.info(f"[signal_guard] Trading this cycle ({len(selected)}):")
        for s in selected:
            bt_info = f" | backtest ROI: {s.backtest_roi:.1%}" if s.backtest_roi is not None else ""
            logger.info(
                f"  ✓ {s.coin:<12} quality={s.quality:.0f}/100 "
                f"signal={'BUY' if s.signal==1 else 'SELL'} "
                f"price={s.price:.4f}{bt_info}"
            )
    else:
        logger.info("[signal_guard] No coins passed filters — skipping this cycle")

    if skipped:
        logger.info(f"[signal_guard] Skipped ({len(skipped)}):")
        for s in skipped:
            logger.info(f"  ✗ {s.coin:<12} {s.skip_reason}")

    return [s.coin for s in selected]


def print_scan_report(all_coins: list[str], min_quality: float = 0) -> None:
    """
    Diagnostic tool — print a full quality report for all coins.
    Call this with --scan flag for a quick market overview.

    Example:
        python -c "
        from data.multi_coin_list import COIN_CURRENCY
        from bot.signal_guard import print_scan_report
        print_scan_report(list(COIN_CURRENCY.keys()))
        "
    """
    print("\n" + "="*60)
    print("  SIGNAL QUALITY SCAN REPORT")
    print("="*60)

    scores = [_scan_coin(c) for c in all_coins]
    scores.sort(key=lambda s: s.quality, reverse=True)

    print(f"{'Coin':<14} {'Quality':>7} {'Signal':<6} {'Price':>12} {'Mkt OK':>7} {'Skip Reason'}")
    print("-"*60)

    for s in scores:
        signal_str = {1: "BUY", -1: "SELL", 0: "HOLD"}.get(s.signal, "?")
        mkt = "✓" if s.market_ok else "✗"
        skip = s.skip_reason or "—"
        print(
            f"{s.coin:<14} {s.quality:>7.1f} {signal_str:<6} "
            f"{s.price:>12.4f} {mkt:>7}  {skip}"
        )

    print("="*60 + "\n")