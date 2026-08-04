#!/usr/bin/env python3
"""
Converts execute_paper_trade() and execute_stock_trade() to return dicts
instead of formatted strings, and fixes the two downstream call sites in
main_enhanced.py that currently assume a string.

Same pattern as the earlier isinstance() stopgap script: each patch is a
small, independent (old, new) pair with an assert that `old` appears
exactly once before it's applied. If any assert fails, the source has
drifted from what was reviewed and nothing gets written — re-diff by hand
rather than trusting the rest of the script.

Run from the repo root:
    python3 apply_dict_return_fix.py
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


# ─────────────────────────────────────────────────────────────────────────
# execution/enhanced_paper_trader.py
# ─────────────────────────────────────────────────────────────────────────
paper_trader_patches = [
    # BUY — already in position
    (
'''        if position:
            return f"{coin} ALREADY IN POSITION @ ${position.get('entry_price', 0.0):.2f}"''',
'''        if position:
            msg = f"{coin} ALREADY IN POSITION @ ${position.get('entry_price', 0.0):.2f}"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — account daily loss limit
    (
'''        if daily_pnl_account < 0 and abs(daily_pnl_account) >= max_account_loss:
            return f"ACCOUNT DAILY LOSS LIMIT HIT: {daily_pnl_account:+.2f} (limit: -{max_account_loss:.2f}) - all new entries blocked"''',
'''        if daily_pnl_account < 0 and abs(daily_pnl_account) >= max_account_loss:
            msg = f"ACCOUNT DAILY LOSS LIMIT HIT: {daily_pnl_account:+.2f} (limit: -{max_account_loss:.2f}) - all new entries blocked"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — per-coin daily loss limit
    (
'''        if daily_pnl_coin < 0 and abs(daily_pnl_coin) >= max_coin_loss:
            return f"{coin} DAILY LOSS LIMIT HIT: {daily_pnl_coin:+.2f} (limit: -{max_coin_loss:.2f}) - entries for {coin} blocked"''',
'''        if daily_pnl_coin < 0 and abs(daily_pnl_coin) >= max_coin_loss:
            msg = f"{coin} DAILY LOSS LIMIT HIT: {daily_pnl_coin:+.2f} (limit: -{max_coin_loss:.2f}) - entries for {coin} blocked"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — max positions
    (
'''        if not override_risk:
            can_open, current, max_pos = check_max_positions(len(positions), config)
            if not can_open:
                return f"MAX POSITIONS: {current}/{max_pos}"''',
'''        if not override_risk:
            can_open, current, max_pos = check_max_positions(len(positions), config)
            if not can_open:
                msg = f"MAX POSITIONS: {current}/{max_pos}"
                return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                        "size_usd": None, "stop_loss": None, "take_profit": None,
                        "pnl": None, "exit_reason": None}'''
    ),
    # BUY — ATR required
    (
'''        if atr is None or atr <= 0:
            return "ERROR: ATR required (>0)"''',
'''        if atr is None or atr <= 0:
            return {"success": False, "action": "BUY", "message": "ERROR: ATR required (>0)",
                    "quantity": 0, "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — size too small
    (
'''        calc_size = trade_size or calc_size
        if calc_size <= 0:
            return "SIZE TOO SMALL"''',
'''        calc_size = trade_size or calc_size
        if calc_size <= 0:
            return {"success": False, "action": "BUY", "message": "SIZE TOO SMALL",
                    "quantity": 0, "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — insufficient funds
    (
'''        fees_info = calculate_fees_and_slippage(calc_size, config)
        total_cost = calc_size + fees_info["total_cost"]
        if account["cash"] < total_cost:
            return f"INSUFFICIENT FUNDS: need ${total_cost:.2f}"''',
'''        fees_info = calculate_fees_and_slippage(calc_size, config)
        total_cost = calc_size + fees_info["total_cost"]
        if account["cash"] < total_cost:
            msg = f"INSUFFICIENT FUNDS: need ${total_cost:.2f}"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — success
    (
'''        return f"BUY {coin} @ ${effective_price:.2f}\\nSize: ${calc_size:.2f}\\nSL: ${sl:.2f} | TP: ${tp:.2f}"''',
'''        msg = f"BUY {coin} @ ${effective_price:.2f}\\nSize: ${calc_size:.2f}\\nSL: ${sl:.2f} | TP: ${tp:.2f}"
        return {"success": True, "action": "BUY", "message": msg,
                "quantity": calc_size / effective_price, "size_usd": calc_size,
                "stop_loss": sl, "take_profit": tp, "pnl": None, "exit_reason": None}'''
    ),
    # SELL — no position
    (
'''    if signal == -1:
        if not position:
            return f"{coin} NO POSITION"''',
'''    if signal == -1:
        if not position:
            return {"success": False, "action": "SELL", "message": f"{coin} NO POSITION",
                    "quantity": 0, "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # SELL — success
    (
'''        return f"SELL {coin} @ ${effective_price:.2f}\\nPnL: {net_pnl:+.2f} {pos_curr}\\nExit: {exit_type}"''',
'''        msg = f"SELL {coin} @ ${effective_price:.2f}\\nPnL: {net_pnl:+.2f} {pos_curr}\\nExit: {exit_type}"
        return {"success": True, "action": "SELL", "message": msg, "quantity": num_coins,
                "size_usd": size, "stop_loss": sl, "take_profit": tp, "pnl": net_pnl,
                "exit_reason": exit_type}'''
    ),
    # HOLD — open position
    (
'''    if position:
        unreal = (price - position["entry_price"]) * (position["trade_size"] / position["entry_price"])
        pct = unreal / position["trade_size"] * 100
        return f"HOLD {coin}\\nUnreal: {unreal:+.2f} ({pct:+.1f}%)"

    return f"{coin} NO POSITION"''',
'''    if position:
        unreal = (price - position["entry_price"]) * (position["trade_size"] / position["entry_price"])
        pct = unreal / position["trade_size"] * 100
        msg = f"HOLD {coin}\\nUnreal: {unreal:+.2f} ({pct:+.1f}%)"
        return {"success": True, "action": "HOLD", "message": msg, "quantity": 0,
                "size_usd": None, "stop_loss": position.get("stop_loss"),
                "take_profit": position.get("take_profit"), "pnl": unreal, "exit_reason": None}

    return {"success": False, "action": None, "message": f"{coin} NO POSITION", "quantity": 0,
            "size_usd": None, "stop_loss": None, "take_profit": None, "pnl": None,
            "exit_reason": None}'''
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# execution/alpaca_trader.py
#
# NOTE: applied against the last-confirmed snapshot from the context doc,
# NOT a freshly re-pasted source (unlike enhanced_paper_trader.py above).
# If any assert below fails, that's your signal this file has drifted —
# re-paste it and I'll regenerate these patches against the real source.
# ─────────────────────────────────────────────────────────────────────────
alpaca_trader_patches = [
    # BUY — already holding
    (
'''        if ticker in positions:
            return f"[SKIP] Already holding {ticker}"''',
'''        if ticker in positions:
            msg = f"[SKIP] Already holding {ticker}"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — max positions
    (
'''        if len(positions) >= max_positions:
            return f"[SKIP] Max positions ({max_positions}) reached"''',
'''        if len(positions) >= max_positions:
            msg = f"[SKIP] Max positions ({max_positions}) reached"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — order failed
    (
'''            return result
        else:
            return f"[ERROR] Order failed for {ticker} BUY"''',
'''            return result
        else:
            msg = f"[ERROR] Order failed for {ticker} BUY"
            return {"success": False, "action": "BUY", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": stop_loss, "take_profit": take_profit,
                    "pnl": None, "exit_reason": None}'''
    ),
    # BUY — success
    (
'''            logging.info(f"[alpaca_trader] {result}")
            _log_trade(ticker, "BUY", shares, price, stop_loss, take_profit, cost)
            return result''',
'''            logging.info(f"[alpaca_trader] {result}")
            _log_trade(ticker, "BUY", shares, price, stop_loss, take_profit, cost)
            return {"success": True, "action": "BUY", "message": result, "quantity": shares,
                    "size_usd": cost, "stop_loss": stop_loss, "take_profit": take_profit,
                    "pnl": None, "exit_reason": None}'''
    ),
    # SELL — no position
    (
'''        if ticker not in positions:
            return f"[SKIP] No position in {ticker} to close"''',
'''        if ticker not in positions:
            msg = f"[SKIP] No position in {ticker} to close"
            return {"success": False, "action": "SELL", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
    # SELL — order failed
    (
'''            _log_trade(ticker, "SELL", shares, price, pnl=pnl)
            return result
        else:
            return f"[ERROR] Order failed for {ticker} SELL"''',
'''            _log_trade(ticker, "SELL", shares, price, pnl=pnl)
            return {"success": True, "action": "SELL", "message": result, "quantity": shares,
                    "size_usd": cost, "stop_loss": None, "take_profit": None, "pnl": pnl,
                    "exit_reason": "MANUAL"}
        else:
            msg = f"[ERROR] Order failed for {ticker} SELL"
            return {"success": False, "action": "SELL", "message": msg, "quantity": 0,
                    "size_usd": None, "stop_loss": None, "take_profit": None,
                    "pnl": None, "exit_reason": None}'''
    ),
]

# ─────────────────────────────────────────────────────────────────────────
# main_enhanced.py — the two downstream fixes
# ─────────────────────────────────────────────────────────────────────────
main_enhanced_patches = [
    # cooldown detection: was string-sniffing "STOP_LOSS", now reads exit_reason
    (
'''            if trade_result and "STOP_LOSS" in str(trade_result):''',
'''            _exit_reason = trade_result.get("exit_reason") if isinstance(trade_result, dict) else None
            if _exit_reason == "STOP_LOSS" or (trade_result and not isinstance(trade_result, dict) and "STOP_LOSS" in str(trade_result)):'''
    ),
    # alert text: was embedding the raw value, now pulls the message field
    (
'''            message_parts.append(f"\\nTrade: {trade_result or 'No action'}")''',
'''            if isinstance(trade_result, dict):
                _trade_display = trade_result.get("message", "No action")
            else:
                _trade_display = trade_result or "No action"
            message_parts.append(f"\\nTrade: {_trade_display}")'''
    ),
]


if __name__ == "__main__":
    apply_patches("execution/enhanced_paper_trader.py", paper_trader_patches)
    apply_patches("execution/alpaca_trader.py", alpaca_trader_patches)
    apply_patches("main_enhanced.py", main_enhanced_patches)
    print("\nAll patches applied. Next: run test_refactor_paths.py, then --once against a live cycle.")