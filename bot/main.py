#!/usr/bin/env python3
"""
bot/main.py  —  Clean entry point for crypto-trader.

Supports:
  --once        Run a single cycle and exit
  --paper       Force paper trading mode
  --live        Force live trading mode (requires CONFIRM)
  --backtest    Run backtest and exit
  --healthcheck Print system health and exit
  --interval N  Run every N seconds (default: 300)

The actual trading logic lives in main_enhanced.py (root).
This file is the new canonical entry point — it imports and calls that logic
so nothing is broken while we refactor incrementally.
"""

import argparse
import logging
import os
import sys

# Ensure project root is on the path (works from any working directory)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

# ── Logging bootstrap (full config in monitoring/logger.py) ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('bot.main')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Crypto Trading Bot — Samsung A55 / Termux Edition'
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once',       action='store_true', help='Single cycle then exit')
    mode.add_argument('--backtest',   action='store_true', help='Run backtest then exit')
    mode.add_argument('--healthcheck',action='store_true', help='Print health info then exit')
    parser.add_argument('--paper',    action='store_true', help='Force paper trading mode')
    parser.add_argument('--live',     action='store_true', help='Force live trading mode')
    parser.add_argument('--interval', type=int, default=300, help='Loop interval in seconds')
    return parser.parse_args()


def enforce_trading_mode(args):
    """Validate and set TRADING_MODE env var from CLI flags."""
    mode = os.getenv('TRADING_MODE', 'paper').lower()

    if args.live:
        confirm = input(
            '\n⚠  WARNING: Live trading requested.\n'
            '   Type CONFIRM to proceed (anything else cancels): '
        )
        if confirm.strip() != 'CONFIRM':
            logger.info('Live trading cancelled by user.')
            sys.exit(0)
        os.environ['TRADING_MODE'] = 'live'
        logger.warning('LIVE TRADING MODE ACTIVE')
    elif args.paper:
        os.environ['TRADING_MODE'] = 'paper'
        logger.info('Paper trading mode active (forced by --paper flag)')
    else:
        os.environ['TRADING_MODE'] = mode
        logger.info(f'Trading mode from .env: {mode}')


def run_healthcheck():
    """Print basic system health information."""
    import platform, shutil
    logger.info('=== HEALTH CHECK ===')
    logger.info(f'Python: {sys.version}')
    logger.info(f'Platform: {platform.platform()}')

    # Disk space
    total, used, free = shutil.disk_usage('.')
    logger.info(f'Disk — total: {total//1e9:.1f}GB  used: {used//1e9:.1f}GB  free: {free//1e9:.1f}GB')

    # Memory (Linux/Android)
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith(('MemTotal', 'MemAvailable')):
                    logger.info(f'RAM — {line.strip()}')
    except FileNotFoundError:
        logger.info('RAM info unavailable on this platform')

    # Check .env
    required = ['BINANCE_API_KEY', 'BINANCE_API_SECRET', 'TELEGRAM_BOT_TOKEN']
    for key in required:
        val = os.getenv(key)
        status = '✓ set' if val else '✗ MISSING'
        logger.info(f'.env  {key}: {status}')

    logger.info('=== END HEALTH CHECK ===')


def main():
    args = parse_args()

    if args.healthcheck:
        run_healthcheck()
        return

    enforce_trading_mode(args)

    if args.backtest:
        logger.info('Running backtest mode...')
        try:
            from backtest.run_backtest_simple import main as run_backtest
            run_backtest()
        except ImportError:
            # Fallback if backtest module not yet refactored
            import subprocess
            subprocess.run([sys.executable, 'backtest/run_backtest_simple.py'], check=True)
        return

    # ── Main bot execution ────────────────────────────────────────────────────
    # Delegate to main_enhanced.py until full refactor is complete.
    # This preserves 100% of existing behaviour.
    logger.info('Starting bot via main_enhanced.py...')
    try:
        import main_enhanced
        if args.once:
            # main_enhanced uses --once flag internally
            sys.argv = [sys.argv[0], '--once']
        elif args.interval:
            sys.argv = [sys.argv[0], '--interval', str(args.interval)]
        main_enhanced.main()
    except AttributeError:
        # main_enhanced may use if __name__ == '__main__' pattern
        logger.warning('main_enhanced.main() not found — running as subprocess')
        import subprocess
        cmd = [sys.executable, 'main_enhanced.py']
        if args.once:
            cmd.append('--once')
        elif args.interval:
            cmd.extend(['--interval', str(args.interval)])
        subprocess.run(cmd, check=True)


if __name__ == '__main__':
    main()
