import sqlite3
from datetime import datetime, timezone

from data.multi_coin_list import COIN_CURRENCY

TRADES_DB = "data/trades.db"

# Duplicated from execution/enhanced_paper_trader.py rather than imported
# from it: that module already imports FROM risk.daily_pnl
# (get_daily_realized_pnl), so importing back the other way would create
# a circular import. TODO: move this constant somewhere both sides can
# share without a cycle (e.g. utils/currencies.py) instead of keeping two
# copies in sync by hand.
ZAR_TO_USD_RATE = 1 / 18.5


def _to_usd(amount, symbol):
    """
    Convert a realized-PnL amount, native to whatever currency `symbol`
    trades in (per data.multi_coin_list), to its USD equivalent.

    NOTE: this uses the CURRENT COIN_CURRENCY mapping, not whatever
    currency was actually in effect when a given historical trade closed.
    If COIN_CURRENCY is ever edited (a coin's trading currency changes),
    old rows in trades.db would silently get reinterpreted under the new
    mapping. If the `trades` table has its own per-row currency column
    (trade_logger.py would confirm this — not reviewed yet), querying
    that directly would be more correct than this static lookup.
    """
    currency = COIN_CURRENCY.get(symbol)
    if currency is None:
        print(f"WARNING: no COIN_CURRENCY mapping for {symbol!r} — "
              f"treating its PnL as USD, which may be wrong.")
        currency = "USD"
    if currency == "ZAR":
        return amount * ZAR_TO_USD_RATE
    return amount


def get_daily_realized_pnl(db_path=TRADES_DB, symbol=None):
    """
    Sum of realized PnL from EXIT trades for today (UTC), normalized to USD.
    Opens the DB read-only so it never contends with the live bot's write lock.
    Returns 0.0 if there are no exits yet today.

    Args:
        db_path: path to the trades database
        symbol: if provided, restrict the sum to this symbol only (e.g. "BTC/USDT").
                 If None, sums across all symbols (account-wide).

    Return value is always USD-normalized. Previously this summed the raw
    `pnl` column directly — fine for a single symbol (one symbol trades in
    one currency), but WRONG for the account-wide case (symbol=None): a
    ZAR-denominated coin's PnL and a USD-denominated coin's PnL were added
    together as if they were the same unit, off by ~18.5x. Since the
    caller (enhanced_paper_trader.py) compares this figure against a
    USD-normalized equity threshold for the daily-loss circuit breaker,
    both sides now need to be on the same basis, or the breaker can trip
    at the wrong time in either direction.

    NOTE: matches on the `ts` column by string prefix (LIKE 'YYYY-MM-DD%')
    rather than SQLite's date() function. date() only parses a trailing
    "Z" on SQLite >= 3.42 — trade_logger.py's _now() no longer writes one,
    so a prefix match is both correct and independent of SQLite version.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()

        if symbol is not None:
            # Single symbol → single currency, so a raw SQL sum is safe;
            # convert once at the end.
            cur.execute(
                """
                SELECT COALESCE(SUM(pnl), 0.0)
                FROM trades
                WHERE action = 'EXIT' AND ts LIKE ? AND symbol = ?
                """,
                (today + "%", symbol)
            )
            raw_pnl = cur.fetchone()[0]
            return _to_usd(raw_pnl, symbol)

        # Account-wide → different rows can be in different currencies,
        # so we MUST group by symbol and convert each group individually
        # before summing. A single global SQL SUM(pnl) here would mix
        # currencies, which was the bug.
        cur.execute(
            """
            SELECT symbol, COALESCE(SUM(pnl), 0.0)
            FROM trades
            WHERE action = 'EXIT' AND ts LIKE ?
            GROUP BY symbol
            """,
            (today + "%",)
        )
        rows = cur.fetchall()
        return sum(_to_usd(sym_pnl, sym) for sym, sym_pnl in rows)
    finally:
        conn.close()