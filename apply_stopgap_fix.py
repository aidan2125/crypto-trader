#!/usr/bin/env python3
"""
Stopgap patch for main_enhanced.py — guards against trade_result being a
plain string (the current real shape from execute_paper_trade /
execute_stock_trade) instead of a dict, which was crashing SQLite logging
mid-function and silently skipping save_last_signals / alerts / log_signal
for every successful trade (84 hits in logs/bot.log confirmed this is live).

This does NOT fix execute_paper_trade/execute_stock_trade's return shape —
that's the real fix, tracked separately. This just stops the crash so
trades get logged (with reduced detail when it's a string) and the bot
state stays consistent.

Run from your repo root:
    PYTHONPATH=. python3 apply_stopgap_fix.py

It edits main_enhanced.py in place. It will refuse to run (AssertionError)
if the file doesn't match what this patch expects, rather than guessing
and potentially corrupting something — if that happens, paste me the
current content of the two functions and I'll regenerate the patch.
"""

from pathlib import Path

TARGET = Path("main_enhanced.py")

# ─────────────────────────────────────────────────────────────────────────
# Patch 1: run_for_symbol's SQLite trade-log block
# ─────────────────────────────────────────────────────────────────────────

OLD_1 = '''            # ── Log trade to SQLite ───────────────────────────────────────────
            if trade_result:
                _direction = "LONG"  if current_signal == 1  else \\
                             "SHORT" if current_signal == -1 else "FLAT"
                _action    = "ENTRY" if current_signal in (1, -1) else "EXIT"
                _trade_logger.log_trade(
                    symbol         = symbol,
                    action         = _action,
                    direction      = _direction,
                    price          = price,
                    quantity       = trade_result.get("quantity", 0),
                    asset_type     = asset_type,
                    position_size  = trade_result.get("size_usd"),
                    stop_loss      = trade_result.get("stop_loss"),
                    take_profit    = trade_result.get("take_profit"),
                    pnl            = trade_result.get("pnl"),
                    exit_reason    = trade_result.get("exit_reason"),
                    atr            = atr,
                    signal_quality = signal_quality,
                    strategy_mode  = strategy_mode,
                )'''

NEW_1 = '''            # ── Log trade to SQLite ───────────────────────────────────────────
            # STOPGAP: trade_result is currently a plain string in most real
            # paths (execute_paper_trade / execute_stock_trade return
            # f-strings, not dicts). Calling .get() on a string crashed this
            # function before reaching save_last_signals — confirmed live via
            # "'str' object has no attribute 'get'" in logs/bot.log.
            # Real fix: make execute_paper_trade/execute_stock_trade always
            # return a dict. Tracked separately.
            if isinstance(trade_result, dict):
                _direction = "LONG"  if current_signal == 1  else \\
                             "SHORT" if current_signal == -1 else "FLAT"
                _action    = "ENTRY" if current_signal in (1, -1) else "EXIT"
                _trade_logger.log_trade(
                    symbol         = symbol,
                    action         = _action,
                    direction      = _direction,
                    price          = price,
                    quantity       = trade_result.get("quantity", 0),
                    asset_type     = asset_type,
                    position_size  = trade_result.get("size_usd"),
                    stop_loss      = trade_result.get("stop_loss"),
                    take_profit    = trade_result.get("take_profit"),
                    pnl            = trade_result.get("pnl"),
                    exit_reason    = trade_result.get("exit_reason"),
                    atr            = atr,
                    signal_quality = signal_quality,
                    strategy_mode  = strategy_mode,
                )
            elif trade_result:
                # String result — still get it into trades.db, just without
                # the structured numeric fields we can't pull out of a string.
                _direction = "LONG"  if current_signal == 1  else \\
                             "SHORT" if current_signal == -1 else "FLAT"
                _action    = "ENTRY" if current_signal in (1, -1) else "EXIT"
                logging.info(f"{log_prefix}{symbol}: trade_result was a string, not a dict — logging message only")
                _trade_logger.log_trade(
                    symbol         = symbol,
                    action         = _action,
                    direction      = _direction,
                    price          = price,
                    quantity       = 0,
                    asset_type     = asset_type,
                    exit_reason    = str(trade_result)[:200],
                    atr            = atr,
                    signal_quality = signal_quality,
                    strategy_mode  = strategy_mode,
                )'''

# ─────────────────────────────────────────────────────────────────────────
# Patch 2: check_all_positions_for_exits' SL block
# ─────────────────────────────────────────────────────────────────────────

OLD_2 = '''                    result = execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    _cooldown.start(coin)

                    if result:
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",   # exiting a long position
                            price       = current_price,
                            quantity    = result.get("quantity", 0),
                            asset_type  = "crypto",
                            pnl         = result.get("pnl"),
                            exit_reason = "SL",
                        )'''

NEW_2 = '''                    result = execute_paper_trade(coin, -1, current_price, currency, override_risk=True)
                    _cooldown.start(coin)

                    # STOPGAP: same string-vs-dict guard as run_for_symbol.
                    if isinstance(result, dict):
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",   # exiting a long position
                            price       = current_price,
                            quantity    = result.get("quantity", 0),
                            asset_type  = "crypto",
                            pnl         = result.get("pnl"),
                            exit_reason = "SL",
                        )
                    elif result:
                        logging.info(f"{coin}: SL exit result was a string, not a dict — logging message only")
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = 0,
                            asset_type  = "crypto",
                            exit_reason = f"SL: {str(result)[:190]}",
                        )'''

# ─────────────────────────────────────────────────────────────────────────
# Patch 3: check_all_positions_for_exits' TP block
# ─────────────────────────────────────────────────────────────────────────

OLD_3 = '''                    result = execute_paper_trade(coin, -1, current_price, currency, override_risk=True)

                    if result:
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = result.get("quantity", 0),
                            asset_type  = "crypto",
                            pnl         = result.get("pnl"),
                            exit_reason = "TP",
                        )'''

NEW_3 = '''                    result = execute_paper_trade(coin, -1, current_price, currency, override_risk=True)

                    # STOPGAP: same string-vs-dict guard as run_for_symbol.
                    if isinstance(result, dict):
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = result.get("quantity", 0),
                            asset_type  = "crypto",
                            pnl         = result.get("pnl"),
                            exit_reason = "TP",
                        )
                    elif result:
                        logging.info(f"{coin}: TP exit result was a string, not a dict — logging message only")
                        _trade_logger.log_trade(
                            symbol      = coin,
                            action      = "EXIT",
                            direction   = "LONG",
                            price       = current_price,
                            quantity    = 0,
                            asset_type  = "crypto",
                            exit_reason = f"TP: {str(result)[:190]}",
                        )'''


def apply_patch(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    assert count == 1, (
        f"{label}: expected exactly 1 match, found {count}. "
        f"Your file doesn't match what this patch expects — stopping "
        f"without changing anything. Paste me the current function and "
        f"I'll regenerate the patch."
    )
    return text.replace(old, new)


def main():
    assert TARGET.exists(), f"{TARGET} not found — run this from your repo root"
    text = TARGET.read_text()

    text = apply_patch(text, OLD_1, NEW_1, "Patch 1 (run_for_symbol trade log)")
    text = apply_patch(text, OLD_2, NEW_2, "Patch 2 (SL exit log)")
    text = apply_patch(text, OLD_3, NEW_3, "Patch 3 (TP exit log)")

    backup = TARGET.with_suffix(".py.bak")
    backup.write_text(Path(TARGET).read_text())
    print(f"Backup written to {backup}")

    TARGET.write_text(text)
    print(f"Patched {TARGET} — all 3 stopgap guards applied.")

    import ast
    ast.parse(text)
    print("Syntax check passed.")


if __name__ == "__main__":
    main()