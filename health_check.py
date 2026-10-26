#!/usr/bin/env python3
"""Startup health check. Read-only: never places orders, never sends alerts.

Run standalone:  python health_check.py --mode dual
Exit code 1 if any FATAL check fails.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

MIN_FREE_MB = 500
MAX_CLOCK_SKEW_S = 20          # AltcoinTrader rejects signatures beyond +-30s
MAX_CANDLE_AGE_S = 3 * 3600    # latest 1h candle should be newer than this
LIVE_PHRASE = "I_UNDERSTAND_THE_RISK"


@dataclass
class Check:
    name: str
    ok: bool
    fatal: bool
    detail: str = ""


# ── individual checks: return a detail string, or raise on failure ──────────

def check_env_core(mode: str) -> str:
    required = []
    if mode in ("stocks", "dual"):
        required += ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError("missing env vars: " + ", ".join(missing))
    return f"mode={mode}"


def check_disk() -> str:
    free_mb = shutil.disk_usage(".").free / 1e6
    if free_mb < MIN_FREE_MB:
        raise RuntimeError(f"only {free_mb:.0f} MB free")
    for d in ("data", "logs"):
        Path(d).mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=d):
            pass
    return f"{free_mb:.0f} MB free, data/ and logs/ writable"


def check_db() -> str:
    path = os.getenv("TRADE_DB_PATH", "data/trades.db")
    if not Path(path).exists():
        return "no DB yet (created on first run)"
    con = sqlite3.connect(path, timeout=5)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"integrity_check: {result}")
        con.execute("BEGIN IMMEDIATE")   # proves we can take the write lock
        con.rollback()
    finally:
        con.close()
    return "integrity ok, writable"


def check_exchange_and_clock() -> str:
    from data.market_data import exchange
    try:
        server_ms = exchange.fetch_time()
    except Exception as e:
        raise RuntimeError(f"exchange unreachable: {type(e).__name__}")
    skew = abs(server_ms / 1000 - time.time())
    if skew > MAX_CLOCK_SKEW_S:
        raise RuntimeError(f"clock skew {skew:.0f}s, sync NTP")
    return f"reachable, clock skew {skew:.1f}s"


def check_candle_freshness() -> str:
    from data.market_data import exchange
    candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=2)
    if not candles:
        raise RuntimeError("no candles returned")
    age = time.time() - candles[-1][0] / 1000
    if age > MAX_CANDLE_AGE_S:
        raise RuntimeError(f"latest BTC/USDT 1h candle is {age/3600:.1f}h old")
    return f"latest candle {age/60:.0f} min old"


def check_alert_channels() -> str:
    found, problems = [], []
    if os.getenv("DISCORD_WEBHOOK_URL"):
        found.append("discord")
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        found.append("telegram")
    if all(os.getenv(k) for k in ("EMAIL_FROM", "EMAIL_TO", "SMTP_HOST")):
        found.append("email")
    else:
        problems.append("email vars incomplete (EMAIL_FROM/EMAIL_TO/SMTP_HOST)")
    if not found:
        raise RuntimeError("no alert channel configured")
    detail = "configured: " + ", ".join(found)
    if problems:
        raise RuntimeError(detail + "; " + "; ".join(problems))
    return detail


def check_discord() -> str:
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return "not configured, skipped"
    try:                       # GET on a webhook returns its info; sends nothing
        r = requests.get(url, timeout=5)
    except requests.RequestException as e:
        raise RuntimeError(f"unreachable: {type(e).__name__}")  # never leak the URL
    if r.status_code != 200:
        raise RuntimeError(f"webhook returned HTTP {r.status_code}")
    return "webhook valid"


def check_telegram() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return "not configured, skipped"
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        ok = r.json().get("ok")
    except Exception as e:
        raise RuntimeError(f"unreachable: {type(e).__name__}")  # never leak the token
    if not ok:
        raise RuntimeError("getMe rejected the token")
    return "bot token valid"


def check_alpaca() -> str:
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not (key and secret):
        raise RuntimeError("keys not set")
    from alpaca.trading.client import TradingClient
    paper = os.getenv("ALPACA_MODE", "paper").lower() != "live"
    acct = TradingClient(key, secret, paper=paper).get_account()
    return f"{'paper' if paper else 'LIVE'} account status {acct.status}"


def altcoin_is_live() -> bool:
    return (os.getenv("ALTCOINTRADER_DRY_RUN", "true").lower() == "false"
            and os.getenv("ALTCOINTRADER_LIVE_CONFIRM") == LIVE_PHRASE)


def check_altcoin() -> str:
    if not os.getenv("ALTCOINTRADER_API_KEY"):
        return "not configured, skipped"
    from execution import altcoin_trader as at
    balances = at.get_balances()                # read-only
    if not altcoin_is_live():
        return "auth ok (dry run)"
    problems = []
    for coin, pos in at._load_positions().items():
        ticker = at.COIN_TICKER_MAP.get(coin)
        held = balances.get(ticker, {}).get("total", 0.0)
        if held < pos.get("quantity", 0) * 0.98:
            problems.append(f"{coin}: tracked {pos.get('quantity')} but hold {held}")
    if problems:
        raise RuntimeError("position mismatch: " + "; ".join(problems))
    return "auth ok, tracked positions match balances"


# ── runner ──────────────────────────────────────────────────────────────────

def build_checks(mode: str):
    checks = [
        ("env vars",           True,  lambda: check_env_core(mode)),
        ("disk + folders",     True,  check_disk),
        ("database",           True,  check_db),
        ("exchange + clock",   True,  check_exchange_and_clock),
        ("candle freshness",   False, check_candle_freshness),
        ("alert channels",     False, check_alert_channels),
        ("discord webhook",    False, check_discord),
        ("telegram bot",       False, check_telegram),
        ("altcointrader",      altcoin_is_live(), check_altcoin),
    ]
    if mode in ("stocks", "dual"):
        checks.append(("alpaca", False, check_alpaca))
    return checks


def run_checks(checks) -> list:
    results = []
    for name, fatal, fn in checks:
        try:
            results.append(Check(name, True, fatal, fn() or ""))
        except Exception as e:
            results.append(Check(name, False, fatal, str(e)))
    return results


def startup_ok(results) -> bool:
    return not any((not c.ok) and c.fatal for c in results)


def print_report(results) -> None:
    print("\n" + "=" * 70 + "\n STARTUP HEALTH CHECK\n" + "=" * 70)
    for c in results:
        tag = "PASS" if c.ok else ("FAIL" if c.fatal else "WARN")
        print(f"  [{tag}] {c.name:<18} {c.detail}")
    print("=" * 70 + "\n")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=os.getenv("TRADING_MODE", "dual"),
                        choices=["crypto", "stocks", "dual"])
    args = parser.parse_args()
    results = run_checks(build_checks(args.mode))
    print_report(results)
    return 0 if startup_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
