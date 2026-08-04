"""
Drop this in tests/test_refactor_paths.py in your crypto-trader repo and run:

    PYTHONPATH=. python3 tests/test_refactor_paths.py

Exercises the three paths the structural refactor actually changed the logic
for, none of which showed up in a normal no-signal-change run:

  1. Signal change  -> execute_fn called, alert built, last_signals saved
  2. SL trade result -> _cooldown.start() fires, next call for same key
                         is skipped while cooldown is active
  3. Fatal error     -> _handle_symbol_error re-raises instead of swallowing

Everything external (exchange calls, Telegram/Discord/email, SQLite logger,
the strategy/indicator pass) is mocked. Nothing here touches your real
data/*.json, data/trades.db, or sends a live alert.
"""

import sys
from unittest.mock import MagicMock, patch


def fake_df(signal, price=50000.0, atr=100.0, quality=80.0):
    """Minimal stand-in for the polars DataFrame slice main_enhanced reads
    columns off of (df.tail(1)['signal'][0] etc)."""
    row = {
        "signal": [signal],
        "close": [price],
        "atr": [atr],
        "signal_quality": [quality],
    }

    class FakeRow:
        def __init__(self, d):
            self._d = d
        @property
        def columns(self):
            return list(self._d.keys())
        def __getitem__(self, key):
            return self._d[key]

    class FakeDF:
        def __init__(self, d):
            self._d = d
        def is_empty(self):
            return False
        def tail(self, n):
            return FakeRow(self._d)
        @property
        def columns(self):
            return list(self._d.keys())

    return FakeDF(row)


def run():
    import main_enhanced as m

    print("── Test 1: signal change fires trade + alert ──")
    with patch.object(m, "load_last_signals", return_value={}), \
         patch.object(m, "save_last_signals") as mock_save, \
         patch.object(m, "enhanced_strategy", side_effect=lambda df, mode: df), \
         patch.object(m, "send_all_alerts", return_value={"telegram": True, "email": False, "discord": False}) as mock_alerts, \
         patch.object(m._trade_logger, "log_trade"), \
         patch.object(m._trade_logger, "log_signal"):

        executed = {}
        def fake_execute(symbol, signal, price, currency, atr):
            executed["called_with"] = (symbol, signal, price, currency, atr)
            return {"success": True, "action": "BUY", "message": f"BUY {symbol} @ ${price:.2f}",
                    "quantity": 1, "size_usd": 100.0, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}

        m.run_for_symbol(
            "BTC/USDT",
            asset_type="crypto",
            fetch_fn=lambda: fake_df(signal=1),
            currency="USD",
            execute_fn=fake_execute,
            cooldown_key="BTC/USDT",
            field_label="Coin",
            signal_title="SIGNAL CHANGE",
            do_plot=False,
        )

        assert "called_with" in executed, "execute_fn was never called on a signal change"
        assert mock_alerts.called, "alert was never sent on a signal change"
        assert mock_save.called, "last_signals was never persisted"
        print("  PASS — trade executed, alert sent, signal state saved")

    print("\n── Test 2: STOP_LOSS trade result starts cooldown, blocks next call ──")
    with patch.object(m, "load_last_signals", return_value={"ETH/USDT": 1}), \
         patch.object(m, "save_last_signals"), \
         patch.object(m, "enhanced_strategy", side_effect=lambda df, mode: df), \
         patch.object(m, "send_all_alerts", return_value={"telegram": True, "email": False, "discord": False}), \
         patch.object(m._trade_logger, "log_trade"), \
         patch.object(m._trade_logger, "log_signal"):

        def fake_execute_sl(symbol, signal, price, currency, atr):
            # Realistic shape: your real execute_paper_trade/execute_stock_trade
            # now return a dict with a human-readable "message" field plus
            # structured fields — run_for_symbol reads exit_reason directly
            # for cooldown detection and message for the alert text.
            return {"success": True, "action": "SELL", "message": f"SELL {symbol} @ ${price:.2f}\nExit: STOP_LOSS",
                    "quantity": 1, "size_usd": 100.0, "stop_loss": price * 1.02, "take_profit": None,
                    "pnl": -50, "exit_reason": "STOP_LOSS"}

        # First call: signal flips to -1, execute_fn reports a stop-loss
        m.run_for_symbol(
            "ETH/USDT",
            asset_type="crypto",
            fetch_fn=lambda: fake_df(signal=-1),
            currency="USD",
            execute_fn=fake_execute_sl,
            cooldown_key="ETH/USDT",
            field_label="Coin",
            signal_title="SIGNAL CHANGE",
            do_plot=False,
        )
        active, mins_left = m._cooldown.is_active("ETH/USDT")
        assert active, "cooldown did not start after a STOP_LOSS trade result"
        print(f"  Cooldown active after SL: {active} ({mins_left}m left)")

        # Second call, same cycle: should be skipped by the cooldown check
        # before execute_fn is even called.
        called_again = {"flag": False}
        def should_not_run(symbol, signal, price, currency, atr):
            called_again["flag"] = True
            return None

        m.run_for_symbol(
            "ETH/USDT",
            asset_type="crypto",
            fetch_fn=lambda: fake_df(signal=-1),
            currency="USD",
            execute_fn=should_not_run,
            cooldown_key="ETH/USDT",
            field_label="Coin",
            signal_title="SIGNAL CHANGE",
            do_plot=False,
        )
        assert not called_again["flag"], "execute_fn ran again despite active cooldown"
        print("  PASS — cooldown correctly blocked the next signal for this symbol")

    print("\n── Test 3: fatal error propagates instead of being swallowed ──")
    def boom():
        raise Exception("AuthenticationError: Invalid API-Key provided")

    try:
        m.run_for_symbol(
            "AAPL",
            asset_type="stock",
            fetch_fn=boom,
            currency="USD",
            execute_fn=lambda *a: None,
            cooldown_key="STOCK:AAPL",
            field_label="Ticker",
            signal_title="STOCK SIGNAL CHANGE",
            do_plot=False,
        )
        raise AssertionError("fatal auth error was swallowed instead of re-raised")
    except Exception as e:
        assert "AuthenticationError" in str(e), f"wrong exception propagated: {e}"
        print(f"  PASS — fatal error correctly propagated: {e}")

    print("\n── Test 4 (control): ordinary error does NOT propagate ──")
    def flaky():
        raise Exception("Connection timed out")

    try:
        m.run_for_symbol(
            "SOL/USDT",
            asset_type="crypto",
            fetch_fn=flaky,
            currency="USD",
            execute_fn=lambda *a: None,
            cooldown_key="SOL/USDT",
            field_label="Coin",
            signal_title="SIGNAL CHANGE",
            do_plot=False,
        )
        print("  PASS — ordinary error was logged and swallowed, loop kept going")
    except Exception as e:
        raise AssertionError(f"a non-fatal error incorrectly propagated: {e}")

    print("\nAll refactor-path tests passed.")


if __name__ == "__main__":
    run()