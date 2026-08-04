import sqlite3
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_DB = "data/test_trades_daily_pnl.db"


def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            asset_type TEXT NOT NULL DEFAULT 'crypto',
            direction TEXT NOT NULL,
            action TEXT NOT NULL,
            exit_reason TEXT,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            position_size REAL,
            stop_loss REAL,
            take_profit REAL,
            pnl REAL,
            pnl_pct REAL,
            atr REAL,
            signal_quality REAL,
            strategy_mode TEXT,
            run_id INTEGER,
            notes TEXT
        )
    """)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # BTC: two exits today, net -15.50 + 8.25 = -7.25
    cur.execute("""
        INSERT INTO trades (ts, symbol, direction, action, price, quantity, pnl)
        VALUES (?, 'BTC/USDT', 'LONG', 'EXIT', 65000, 0.01, -15.50)
    """, (today,))
    cur.execute("""
        INSERT INTO trades (ts, symbol, direction, action, price, quantity, pnl)
        VALUES (?, 'BTC/USDT', 'LONG', 'EXIT', 65200, 0.01, 8.25)
    """, (today,))

    # ETH: one exit today, -20.00
    cur.execute("""
        INSERT INTO trades (ts, symbol, direction, action, price, quantity, pnl)
        VALUES (?, 'ETH/USDT', 'LONG', 'EXIT', 3400, 0.1, -20.00)
    """, (today,))

    # SOL: entry only (pnl NULL) - should never count anywhere
    cur.execute("""
        INSERT INTO trades (ts, symbol, direction, action, price, quantity, pnl)
        VALUES (?, 'SOL/USDT', 'LONG', 'ENTRY', 150, 1.0, NULL)
    """, (today,))

    conn.commit()
    conn.close()


def test_daily_pnl():
    from risk.daily_pnl import get_daily_realized_pnl
    setup_test_db()

    # Account-wide: -15.50 + 8.25 - 20.00 = -27.25
    account_total = get_daily_realized_pnl(db_path=TEST_DB)
    expected_account = -15.50 + 8.25 - 20.00
    assert abs(account_total - expected_account) < 0.001, \
        f"Account-wide: expected {expected_account}, got {account_total}"
    print(f"PASS: account-wide PnL = {account_total:.2f} (expected {expected_account:.2f})")

    # Per-coin: BTC only = -15.50 + 8.25 = -7.25
    btc_total = get_daily_realized_pnl(db_path=TEST_DB, symbol="BTC/USDT")
    expected_btc = -15.50 + 8.25
    assert abs(btc_total - expected_btc) < 0.001, \
        f"BTC: expected {expected_btc}, got {btc_total}"
    print(f"PASS: BTC/USDT PnL = {btc_total:.2f} (expected {expected_btc:.2f})")

    # Per-coin: ETH only = -20.00
    eth_total = get_daily_realized_pnl(db_path=TEST_DB, symbol="ETH/USDT")
    expected_eth = -20.00
    assert abs(eth_total - expected_eth) < 0.001, \
        f"ETH: expected {expected_eth}, got {eth_total}"
    print(f"PASS: ETH/USDT PnL = {eth_total:.2f} (expected {expected_eth:.2f})")

    # Per-coin: SOL has no exits, should be 0.0
    sol_total = get_daily_realized_pnl(db_path=TEST_DB, symbol="SOL/USDT")
    assert abs(sol_total - 0.0) < 0.001, f"SOL: expected 0.0, got {sol_total}"
    print(f"PASS: SOL/USDT PnL = {sol_total:.2f} (expected 0.00, entry-only)")

    os.remove(TEST_DB)
    print("\nAll tests passed.")


if __name__ == "__main__":
    test_daily_pnl()
