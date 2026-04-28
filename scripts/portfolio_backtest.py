#!/usr/bin/env python3
"""
scripts/portfolio_backtest.py

Multi-coin portfolio backtester.

Usage
-----
    # All coins from COIN_CURRENCY (default)
    python scripts/portfolio_backtest.py --mode auto

    # Specific subset
    python scripts/portfolio_backtest.py \\
        --symbols BTC/USDT ETH/USDT ADA/USDT LTC/USDT DOT/USDT \\
        --timeframe 1h \\
        --limit 1000 \\
        --mode auto

    # Export summary to CSV
    python scripts/portfolio_backtest.py --mode auto --export results.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

# ── Make project root importable when the script is run directly ─────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Project imports ───────────────────────────────────────────────────────────
import polars as pl

from data.multi_coin_list import COIN_CURRENCY
from data.market_data import fetch_ohlcv
from strategies.enhanced_signals_refactored import enhanced_strategy
from strategies.adaptive_mode import choose_strategy_mode
from run_backtest_simple import BacktestPro, load_risk_config


# ─────────────────────────────────────────────────────────────────────────────
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backtests across a portfolio of coins.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        metavar="SYMBOL",
        help=(
            "Space-separated list of trading pairs.\n"
            "Omit to run all symbols defined in data/multi_coin_list.py."
        ),
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        help="OHLCV timeframe (default: 1h)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Number of candles per symbol (default: 1000)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="auto",
        choices=["auto", "testing", "balanced", "strict"],
        help="Strategy mode (default: auto)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="FILE",
        help="Optional path to export per-symbol results as CSV.",
    )
    return parser.parse_args(argv)


# ─────────────────────────────────────────────────────────────────────────────
def resolve_symbols(requested: list[str] | None) -> list[str]:
    """
    Return the list of symbols to backtest.
    Uses `requested` if provided; otherwise falls back to all COIN_CURRENCY keys.
    """
    if requested:
        unknown = set(requested) - set(COIN_CURRENCY)
        if unknown:
            print(
                f"[WARNING] These symbols are not in COIN_CURRENCY and will "
                f"be skipped: {sorted(unknown)}",
                file=sys.stderr,
            )
        return [s for s in requested if s in COIN_CURRENCY]
    return list(COIN_CURRENCY.keys())


# ─────────────────────────────────────────────────────────────────────────────
def run_single(
    symbol: str,
    timeframe: str,
    limit: int,
    requested_mode: str,
    risk_config: dict,
) -> dict[str, Any]:
    """
    Full pipeline for one symbol:
        fetch → indicator pass → choose mode → final strategy pass → backtest

    The indicator pass (mode="testing") runs first so that ATR and other
    computed columns exist before choose_strategy_mode is called.
    The final strategy pass then applies the resolved mode to generate
    the actual trade signals used by the backtester.

    Returns a result dict for portfolio aggregation.
    """
    currency = COIN_CURRENCY.get(symbol, "USD")

    print(f"\n  Symbol    : {symbol}")
    print(f"  Timeframe : {timeframe}")
    print(f"  Candles   : {limit}")
    print(f"  Currency  : {currency}")

    # ── Step 1: fetch raw OHLCV ───────────────────────────────────────────────
    df = fetch_ohlcv(symbol, timeframe, limit)
    if df is None or df.is_empty():
        raise RuntimeError(f"No data returned for {symbol}")
    print(f"  {df.height:,} candles loaded.")

    # ── Step 2: indicator pass so ATR exists before mode selection ────────────
    # mode="testing" is the loosest — it guarantees ATR is computed.
    # Signals produced here are thrown away; only indicators are used.
    df_indicator_pass = enhanced_strategy(df.clone(), mode="testing")

    # ── Step 3: resolve mode using the indicator-enriched frame ──────────────
    selected_mode = choose_strategy_mode(
        symbol, df_indicator_pass, requested_mode=requested_mode
    )

    # ── Step 4: final strategy pass with the resolved mode ────────────────────
    df_final = enhanced_strategy(df.clone(), mode=selected_mode)

    # ── Step 5: run backtest ──────────────────────────────────────────────────
    engine = BacktestPro(initial_balance=10000, risk_config=risk_config)
    engine.run(
        df_final,
        symbol=symbol,
        strategy_name=f"Enhanced Strategy [{selected_mode}]",
    )

    # ── Step 6: extract metrics ───────────────────────────────────────────────
    df_trades = pl.DataFrame(engine.trades) if engine.trades else pl.DataFrame()

    total_trades = df_trades.height
    win_rate = (
        float(df_trades.filter(pl.col("pnl") > 0).height / total_trades)
        if total_trades > 0
        else 0.0
    )
    gross_profit = (
        float(df_trades.filter(pl.col("pnl") > 0)["pnl"].sum()) if total_trades > 0 else 0.0
    )
    gross_loss = (
        abs(float(df_trades.filter(pl.col("pnl") <= 0)["pnl"].sum()))
        if total_trades > 0
        else 0.0
    )
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    roi = float(engine.balance / engine.initial_balance - 1) if engine.initial_balance else 0.0
    total_pnl = float(df_trades["pnl"].sum()) if total_trades > 0 else 0.0

    equity_curve = pl.Series([engine.initial_balance] + engine.equity)
    max_dd = (
        float((equity_curve / equity_curve.cum_max() - 1).min())
        if equity_curve.len() > 1
        else 0.0
    )

    return {
        "symbol":          symbol,
        "requested_mode":  requested_mode,
        "mode":            selected_mode,
        "total_trades":    total_trades,
        "win_rate":        win_rate,
        "profit_factor":   profit_factor,
        "roi":             roi,
        "max_drawdown":    max_dd,
        "total_pnl":       total_pnl,
        "error":           None,
    }


# ─────────────────────────────────────────────────────────────────────────────
def run_portfolio(
    symbols: list[str],
    timeframe: str,
    limit: int,
    requested_mode: str,
    risk_config: dict,
) -> list[dict[str, Any]]:
    """
    Iterate over symbols, run a backtest for each, collect results.
    A failed symbol is logged and gets a placeholder error row — the rest continue.
    """
    all_results: list[dict[str, Any]] = []
    total = len(symbols)

    for idx, symbol in enumerate(symbols, start=1):
        print(f"\n{'#' * 55}")
        print(f"#  [{idx}/{total}]  {symbol}")
        print(f"{'#' * 55}")

        try:
            result = run_single(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                requested_mode=requested_mode,
                risk_config=risk_config,
            )
            all_results.append(result)
        except Exception as exc:
            print(f"[ERROR] Backtest failed for {symbol}: {exc}", file=sys.stderr)
            all_results.append(
                {
                    "symbol":         symbol,
                    "requested_mode": requested_mode,
                    "mode":           "–",
                    "total_trades":   0,
                    "win_rate":       0.0,
                    "profit_factor":  0.0,
                    "roi":            0.0,
                    "max_drawdown":   0.0,
                    "total_pnl":      0.0,
                    "error":          str(exc),
                }
            )

    return all_results


# ─────────────────────────────────────────────────────────────────────────────
def _fmt_pct(value: float) -> str:
    return f"{value:+.1%}" if value != 0.0 else "0.0%"


def _fmt_dd(value: float) -> str:
    v = abs(value)
    return f"-{v:.1%}" if v != 0.0 else "0.0%"


def print_portfolio_table(results: list[dict[str, Any]]) -> None:
    col = {
        "Symbol":        12,
        "Mode":          10,
        "Trades":         7,
        "Win Rate":      10,
        "Profit Factor": 15,
        "ROI":            9,
        "Max DD":         9,
    }
    header = (
        f"{'Symbol':<{col['Symbol']}}"
        f"{'Mode':<{col['Mode']}}"
        f"{'Trades':>{col['Trades']}}"
        f"{'Win Rate':>{col['Win Rate']}}"
        f"{'Profit Factor':>{col['Profit Factor']}}"
        f"{'ROI':>{col['ROI']}}"
        f"{'Max DD':>{col['Max DD']}}"
    )
    sep = "─" * len(header)

    print(f"\n{'═' * len(header)}")
    print("  PORTFOLIO BACKTEST RESULTS")
    print(f"{'═' * len(header)}")
    print(header)
    print(sep)

    for r in results:
        flag = " ⚠" if r.get("error") else ""
        print(
            f"{r['symbol']:<{col['Symbol']}}"
            f"{r['mode']:<{col['Mode']}}"
            f"{r['total_trades']:>{col['Trades']}}"
            f"{_fmt_pct(r['win_rate']):>{col['Win Rate']}}"
            f"{r['profit_factor']:>{col['Profit Factor']}.2f}"
            f"{_fmt_pct(r['roi']):>{col['ROI']}}"
            f"{_fmt_dd(r['max_drawdown']):>{col['Max DD']}}"
            f"{flag}"
        )

    print(sep)


def print_portfolio_summary(results: list[dict[str, Any]]) -> None:
    valid = [r for r in results if not r.get("error")]
    if not valid:
        print("\n[WARNING] No valid results to summarise.", file=sys.stderr)
        return

    total_trades = sum(r["total_trades"] for r in valid)
    avg_win_rate = sum(r["win_rate"] for r in valid) / len(valid)
    avg_roi = sum(r["roi"] for r in valid) / len(valid)
    total_pnl = sum(r["total_pnl"] for r in valid)
    best = max(valid, key=lambda r: r["roi"])
    worst = min(valid, key=lambda r: r["roi"])

    print(f"\n{'═' * 45}")
    print("  PORTFOLIO SUMMARY")
    print(f"{'═' * 45}")
    print(f"  {'Symbols tested':<22}: {len(results)}")
    print(f"  {'Successful':<22}: {len(valid)}")
    print(f"  {'Total Trades':<22}: {total_trades}")
    print(f"  {'Average Win Rate':<22}: {avg_win_rate:.1%}")
    print(f"  {'Average ROI':<22}: {avg_roi:+.2%}")
    print(f"  {'Total PnL':<22}: ${total_pnl:+,.2f}")
    print(f"  {'Best Symbol':<22}: {best['symbol']} ({best['roi']:+.1%} ROI)")
    print(f"  {'Worst Symbol':<22}: {worst['symbol']} ({worst['roi']:+.1%} ROI)")
    print(f"{'═' * 45}\n")


# ─────────────────────────────────────────────────────────────────────────────
def export_csv(results: list[dict[str, Any]], filepath: str) -> None:
    fields = [
        "symbol", "requested_mode", "mode", "total_trades",
        "win_rate", "profit_factor", "roi", "max_drawdown", "total_pnl", "error",
    ]
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"[INFO] Results exported to: {path.resolve()}")


# ─────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    symbols = resolve_symbols(args.symbols)
    if not symbols:
        print("[ERROR] No valid symbols to backtest.", file=sys.stderr)
        sys.exit(1)

    print(f"\nPortfolio : {len(symbols)} symbol(s) → {', '.join(symbols)}")
    print(f"Timeframe : {args.timeframe}  |  Limit : {args.limit}  |  Mode : {args.mode}")

    risk_config = load_risk_config()

    results = run_portfolio(
        symbols=symbols,
        timeframe=args.timeframe,
        limit=args.limit,
        requested_mode=args.mode,
        risk_config=risk_config,
    )

    print_portfolio_table(results)
    print_portfolio_summary(results)

    if args.export:
        export_csv(results, args.export)


if __name__ == "__main__":
    main()