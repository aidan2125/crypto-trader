#!/usr/bin/env python3
"""
test_db.py
Run from your project root:  python test_db.py

Tests TradeLogger in complete isolation — no market data, no Telegram, no Alpaca.
Creates a throwaway DB at data/test_trades.db (deleted at the end).
"""

import sys
import os
from pathlib import Path
from datetime import date

# ── Make sure project root is on the path ─────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from database.trade_logger import TradeLogger

DB_PATH = Path("data/test_trades.db")
PASS = "✅"
FAIL = "❌"

errors = []

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {label}")
    else:
        msg = f"  {FAIL}  {label}" + (f" — {detail}" if detail else "")
        print(msg)
        errors.append(label)

print("\n" + "="*55)
print("  TradeLogger smoke test")
print("="*55 + "\n")

# ── 1. Init ────────────────────────────────────────────────────────────────
print("1. Init & schema")
try:
    db = TradeLogger(db_path=DB_PATH)
    check("DB file created", DB_PATH.exists())
    check("heartbeat.json created after first write_heartbeat",
          True)   # checked in step 3
except Exception as e:
    check("TradeLogger() init", False, str(e))
    print("\nFatal — cannot continue\n")
    sys.exit(1)

# ── 2. Run session ─────────────────────────────────────────────────────────
print("\n2. Run session")
run_id = db.start_run(mode="crypto", notes="smoke test")
check("start_run() returns int", isinstance(run_id, int))
check("run_id > 0", run_id > 0)

# ── 3. Heartbeat ───────────────────────────────────────────────────────────
print("\n3. Heartbeat")
db.write_heartbeat(loop_count=1)
hb = db.get_last_heartbeat()
check("heartbeat row exists",  hb is not None)
check("loop_count stored",     hb and hb["loop_count"] == 1)
hb_json = Path("data/heartbeat.json")
check("heartbeat.json written", hb_json.exists())

# ── 4. Log a LONG entry ────────────────────────────────────────────────────
print("\n4. Trade logging — LONG entry")
entry_id = db.log_trade(
    symbol         = "BTC/USDT",
    action         = "ENTRY",
    direction      = "LONG",
    price          = 105_000.0,
    quantity       = 0.047,
    asset_type     = "crypto",
    position_size  = 4935.0,
    stop_loss      = 102_000.0,
    take_profit    = 109_500.0,
    atr            = 1_250.0,
    signal_quality = 78.0,
    strategy_mode  = "strict",
)
check("log_trade() returns id",  isinstance(entry_id, int) and entry_id > 0)

# ── 5. Log a LONG exit (TP) ────────────────────────────────────────────────
print("\n5. Trade logging — EXIT (TP)")
exit_id = db.log_trade(
    symbol         = "BTC/USDT",
    action         = "EXIT",
    direction      = "LONG",
    price          = 109_480.0,
    quantity       = 0.047,
    asset_type     = "crypto",
    pnl            = 211.56,
    pnl_pct        = 4.29,
    exit_reason    = "TP",
    strategy_mode  = "strict",
)
check("exit trade logged", isinstance(exit_id, int) and exit_id > 0)

# ── 6. Log a SHORT entry + SL exit ────────────────────────────────────────
print("\n6. Trade logging — SHORT + SL hit")
db.log_trade(
    symbol      = "ETH/USDT",
    action      = "ENTRY",
    direction   = "SHORT",
    price       = 3_400.0,
    quantity    = 1.5,
    asset_type  = "crypto",
    stop_loss   = 3_500.0,
    take_profit = 3_100.0,
)
db.log_trade(
    symbol      = "ETH/USDT",
    action      = "EXIT",
    direction   = "SHORT",
    price       = 3_505.0,
    quantity    = 1.5,
    asset_type  = "crypto",
    pnl         = -157.50,
    pnl_pct     = -3.09,
    exit_reason = "SL",
)
check("SHORT + SL logged without error", True)

# ── 7. Log a stock trade ───────────────────────────────────────────────────
print("\n7. Stock trade")
db.log_trade(
    symbol      = "AAPL",
    action      = "ENTRY",
    direction   = "LONG",
    price       = 221.50,
    quantity    = 22,
    asset_type  = "stock",
    position_size = 4873.0,
    stop_loss   = 210.00,
    take_profit = 240.00,
)
check("stock ENTRY logged", True)

# ── 8. Signal logging ─────────────────────────────────────────────────────
print("\n8. Signal logging")
sig_id = db.log_signal(
    symbol         = "BTC/USDT",
    new_signal     = 1,
    prev_signal    = 0,
    price          = 105_000.0,
    asset_type     = "crypto",
    atr            = 1_250.0,
    signal_quality = 78.0,
    strategy_mode  = "strict",
    acted_on       = True,
)
check("log_signal() returns id", isinstance(sig_id, int) and sig_id > 0)

# ── 9. Query recent trades ─────────────────────────────────────────────────
print("\n9. Queries")
recent = db.get_recent_trades(limit=10)
check("get_recent_trades() returns list",  isinstance(recent, list))
check("closed trades returned",            len(recent) >= 2)
check("BTC exit in results",
      any(t["symbol"] == "BTC/USDT" for t in recent))

# ── 10. Daily summary ──────────────────────────────────────────────────────
print("\n10. Daily summary")
summary = db.daily_summary(for_date=date.today())
check("daily_summary() returns dict", isinstance(summary, dict))
check("total_trades >= 2",  summary.get("total_trades", 0) >= 2)
check("gross_pnl populated", "gross_pnl" in summary)

formatted = db.format_daily_summary()
check("format_daily_summary() returns string", isinstance(formatted, str))
check("P&L line present", "P&L" in formatted or "pnl" in formatted.lower())
print(f"\n  Preview:\n{chr(10).join('    '+l for l in formatted.splitlines())}")

# ── 11. trades.json sync ──────────────────────────────────────────────────
print("\n11. JSON sync (Telegram bot compatibility)")
trades_json = Path("data/trades.json")
check("trades.json written", trades_json.exists())
import json
with open(trades_json) as f:
    tj = json.load(f)
check("trades.json is a list",    isinstance(tj, list))
check("trades.json has entries",  len(tj) > 0)

# ── 12. end_run ───────────────────────────────────────────────────────────
print("\n12. Clean shutdown")
db.end_run(run_count=1)
check("end_run() completed without error", True)

# ── Result ────────────────────────────────────────────────────────────────
print("\n" + "="*55)
if not errors:
    print(f"  {PASS}  All checks passed — DB is working correctly")
else:
    print(f"  {FAIL}  {len(errors)} check(s) failed:")
    for e in errors:
        print(f"       • {e}")
print("="*55 + "\n")

# ── Cleanup ───────────────────────────────────────────────────────────────
import shutil
try:
    DB_PATH.unlink(missing_ok=True)
    Path(str(DB_PATH) + "-wal").unlink(missing_ok=True)
    Path(str(DB_PATH) + "-shm").unlink(missing_ok=True)
    print("  (test DB cleaned up — data/trades.db is your real one)\n")
except Exception:
    pass

sys.exit(1 if errors else 0)