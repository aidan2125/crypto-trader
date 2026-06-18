"""
config/settings.py  —  Central settings loader.

Priority: CLI args > .env overrides > defaults.yaml > hardcoded defaults.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_root = Path(__file__).parent.parent
load_dotenv(_root / '.env')

# ── Trading mode ──────────────────────────────────────────────────────────────
TRADING_MODE = os.getenv('TRADING_MODE', 'paper').lower()  # 'paper' | 'live'

# ── Binance ───────────────────────────────────────────────────────────────────
BINANCE_API_KEY    = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID', '')

# ── Discord (optional) ────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')

# ── Supabase (optional) ───────────────────────────────────────────────────────
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')

# ── Risk defaults (beginner-safe) ─────────────────────────────────────────────
RISK_PRESET          = os.getenv('RISK_PRESET', 'conservative')
MAX_RISK_PER_TRADE   = float(os.getenv('MAX_RISK_PER_TRADE', '0.01'))   # 1%
MAX_POSITIONS        = int(os.getenv('MAX_POSITIONS', '3'))
DAILY_LOSS_LIMIT     = float(os.getenv('DAILY_LOSS_LIMIT', '0.05'))     # 5%
MAX_POSITION_PCT     = float(os.getenv('MAX_POSITION_PCT', '0.10'))     # 10%
TRADE_COOLDOWN_HOURS = float(os.getenv('TRADE_COOLDOWN_HOURS', '4'))
MAX_TRADES_PER_DAY   = int(os.getenv('MAX_TRADES_PER_DAY', '6'))
MIN_SIGNAL_QUALITY   = float(os.getenv('MIN_SIGNAL_QUALITY', '60'))

# ── Bot loop ──────────────────────────────────────────────────────────────────
BOT_INTERVAL_SECONDS = int(os.getenv('BOT_INTERVAL', '300'))   # 5 minutes

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR   = os.getenv('LOG_DIR', 'logs')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
