#!/usr/bin/env python3
"""
Updates the two mock trade-result dicts in test_refactor_paths.py so they
match what execute_paper_trade/execute_stock_trade actually return post-fix
(a "message" field, since run_for_symbol's alert text now reads from that
key instead of str()-ing the whole dict).

Run from the repo root:
    python3 fix_test_stubs.py
"""
import sys

def apply_patches(path, patches):
    with open(path, "r") as f:
        src = f.read()

    for i, (old, new) in enumerate(patches):
        count = src.count(old)
        if count != 1:
            print(f"FAILED on patch #{i} in {path}: expected 1 match, found {count}")
            print("--- old text ---")
            print(old)
            sys.exit(1)
        src = src.replace(old, new)

    with open(path, "w") as f:
        f.write(src)

    print(f"Applied {len(patches)} patches to {path}")


patches = [
    (
'''        def fake_execute(symbol, signal, price, currency, atr):
            executed["called_with"] = (symbol, signal, price, currency, atr)
            return {"quantity": 1, "pnl": None}''',
'''        def fake_execute(symbol, signal, price, currency, atr):
            executed["called_with"] = (symbol, signal, price, currency, atr)
            return {"success": True, "action": "BUY", "message": f"BUY {symbol} @ ${price:.2f}",
                    "quantity": 1, "size_usd": 100.0, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    (
'''        def fake_execute_sl(symbol, signal, price, currency, atr):
            # Realistic shape: your real execute_paper_trade/execute_stock_trade
            # return a dict, with the STOP_LOSS marker inside exit_reason (or
            # similar) so it shows up when the whole dict is str()'d.
            return {"quantity": 1, "pnl": -50, "exit_reason": "STOP_LOSS"}''',
'''        def fake_execute_sl(symbol, signal, price, currency, atr):
            # Realistic shape: your real execute_paper_trade/execute_stock_trade
            # now return a dict with a human-readable "message" field plus
            # structured fields — run_for_symbol reads exit_reason directly
            # for cooldown detection and message for the alert text.
            return {"success": True, "action": "SELL", "message": f"SELL {symbol} @ ${price:.2f}\\nExit: STOP_LOSS",
                    "quantity": 1, "size_usd": 100.0, "stop_loss": price * 1.02, "take_profit": None,
                    "pnl": -50, "exit_reason": "STOP_LOSS"}'''
    ),
]

if __name__ == "__main__":
    apply_patches("test_refactor_paths.py", patches)