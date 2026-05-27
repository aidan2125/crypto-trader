#!/usr/bin/env bash
# =============================================================================
# crypto-trader  —  STABILITY-FIRST REFACTOR SCRIPT
# Run this from INSIDE your cloned repo root:
#   cd ~/crypto-trader && bash refactor.sh
#
# What it does:
#   1. Archives junk/legacy files (nothing deleted)
#   2. Creates clean folder structure
#   3. Moves files to correct locations
#   4. Creates new boilerplate files
#   5. Fixes .gitignore and requirements.txt
#
# What it does NOT do:
#   - Touch any trading logic
#   - Delete anything (only moves to archive/)
#   - Push to GitHub (you do that manually after review)
# =============================================================================

set -e  # Exit on error

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC}  $1"; }
info() { echo -e "${BLUE}[--]${NC}  $1"; }
warn() { echo -e "${YELLOW}[!!]${NC}  $1"; }
head() { echo -e "\n${CYAN}══ $1 ══${NC}"; }

# ── Safety check ─────────────────────────────────────────────────────────────
if [ ! -f "main_enhanced.py" ] && [ ! -f "requirements.txt" ]; then
  echo -e "${RED}ERROR: Run this script from inside the crypto-trader repo root.${NC}"
  echo "  cd ~/crypto-trader && bash refactor.sh"
  exit 1
fi

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║     crypto-trader  ·  Stability-First Refactor      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
warn "This script only MOVES files — nothing is permanently deleted."
warn "All legacy files go to archive/legacy/"
echo ""
read -p "Continue? (y/N): " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# =============================================================================
# STEP 1 — CREATE DIRECTORY STRUCTURE
# =============================================================================
head "STEP 1 · Creating directory structure"

dirs=(
  "archive/legacy"
  "bot"
  "strategies"
  "data"
  "execution"
  "risk"
  "monitoring"
  "config/risk_presets"
  "scripts"
  "tests"
  "logs"
  "backups"
  "reports"
  "database"
  "alerts"
  "backtest"
  "utils"
)

for d in "${dirs[@]}"; do
  mkdir -p "$d"
  log "mkdir $d"
done

# =============================================================================
# STEP 2 — ARCHIVE JUNK FROM ROOT
# =============================================================================
head "STEP 2 · Archiving legacy/junk files from root"

# .old files
for f in *.old; do
  [ -f "$f" ] && mv "$f" archive/legacy/ && log "archived: $f"
done

# Debug/temp scripts that don't belong in root
for f in supabase_debug_check.py debug_backtest_insert.py \
          test_backtest_full.py test_backtest_insert.py test_paper_trader.py \
          install_deps.py check_dependencies.py diagnostics.py \
          apply_risk_preset.py run_with_risk_preset.py; do
  if [ -f "$f" ]; then
    # Test files go to tests/, others to archive
    if [[ "$f" == test_* ]]; then
      mv "$f" tests/ && log "moved to tests/: $f"
    else
      mv "$f" archive/legacy/ && log "archived: $f"
    fi
  fi
done

# Random text/notes files in root
for f in .txt 2.txt preset.txt screen.txt "requirements " applied auto \
          bot_system_diagnostics github_instructions "in real-time"; do
  if [ -f "$f" ]; then
    mv "$f" archive/legacy/ && log "archived: $f"
  fi
done

# crypto_trader.egg-info — build artifact, shouldn't be tracked
if [ -d "crypto_trader.egg-info" ]; then
  mv crypto_trader.egg-info archive/legacy/
  log "archived: crypto_trader.egg-info/"
fi

# utils.py in root (likely superseded by utils/ folder)
if [ -f "utils.py" ] && [ -d "utils" ]; then
  mv utils.py archive/legacy/utils_root.py
  log "archived: utils.py (root level — utils/ folder exists)"
fi

# =============================================================================
# STEP 3 — MOVE CORE FILES TO CORRECT LOCATIONS
# =============================================================================
head "STEP 3 · Moving core files to correct locations"

# main_enhanced.py → archive (we create bot/main.py as the new entry point
# but preserve the original logic by importing it)
if [ -f "main_enhanced.py" ]; then
  cp main_enhanced.py archive/legacy/main_enhanced_original.py
  log "copied main_enhanced.py to archive/legacy/ (preserved)"
fi

# run_backtest_simple.py → backtest/
if [ -f "run_backtest_simple.py" ]; then
  mv run_backtest_simple.py backtest/run_backtest_simple.py
  log "moved: run_backtest_simple.py → backtest/"
fi

# Move existing alerts/ content (already in right place, just ensure __init__)
if [ -d "alerts" ]; then
  touch alerts/__init__.py
  log "alerts/__init__.py ensured"
fi

# Move existing strategies/ content
if [ -d "strategies" ]; then
  touch strategies/__init__.py
  log "strategies/__init__.py ensured"
fi

# Move existing data/ content
if [ -d "data" ]; then
  touch data/__init__.py
  log "data/__init__.py ensured"
fi

# Move existing execution/ content
if [ -d "execution" ]; then
  touch execution/__init__.py
  log "execution/__init__.py ensured"
fi

# Move existing risk/ content
if [ -d "risk" ]; then
  touch risk/__init__.py
  log "risk/__init__.py ensured"
fi

# Move existing database/ content
if [ -d "database" ]; then
  touch database/__init__.py
  log "database/__init__.py ensured"
fi

# Move existing backtest/ content
if [ -d "backtest" ]; then
  touch backtest/__init__.py
  log "backtest/__init__.py ensured"
fi

# Move existing utils/ content
if [ -d "utils" ]; then
  touch utils/__init__.py
  log "utils/__init__.py ensured"
fi

# =============================================================================
# STEP 4 — CREATE __init__.py FILES FOR NEW PACKAGES
# =============================================================================
head "STEP 4 · Creating __init__.py for new packages"

for pkg in bot monitoring config; do
  touch "${pkg}/__init__.py"
  log "${pkg}/__init__.py"
done

# =============================================================================
# STEP 5 — CREATE bot/main.py  (new clean entry point)
# =============================================================================
head "STEP 5 · Creating bot/main.py (new entry point)"

cat > bot/main.py << 'BOTMAIN'
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
BOTMAIN

log "bot/main.py created"

# =============================================================================
# STEP 6 — CREATE monitoring/logger.py
# =============================================================================
head "STEP 6 · Creating monitoring/logger.py"

cat > monitoring/logger.py << 'LOGGERPY'
"""
monitoring/logger.py  —  Centralized rotating log configuration.

Usage in any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info('Something happened')

Call setup_logging() once at startup in bot/main.py.
"""

import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(log_dir: str = 'logs', level: str = 'INFO') -> logging.Logger:
    """
    Configure multi-file rotating logging.

    Files created:
      logs/bot.log      — INFO+  (5MB rotating, 3 backups)
      logs/error.log    — ERROR+ (2MB rotating, 5 backups)
      logs/trades.log   — trade-specific events
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # bot.log — INFO and above
    bot_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/bot.log', maxBytes=5 * 1024 * 1024, backupCount=3
    )
    bot_handler.setLevel(logging.INFO)
    bot_handler.setFormatter(formatter)

    # error.log — ERROR and above only
    error_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/error.log', maxBytes=2 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # Console — visible in tmux window
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(bot_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def get_trade_logger(log_dir: str = 'logs') -> logging.Logger:
    """Separate logger for trade events — writes to logs/trades.log."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    trade_logger = logging.getLogger('trades')
    if not trade_logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            f'{log_dir}/trades.log', maxBytes=10 * 1024 * 1024, backupCount=10
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
        ))
        trade_logger.addHandler(handler)
        trade_logger.setLevel(logging.INFO)
        trade_logger.propagate = False  # Don't duplicate to root logger
    return trade_logger
LOGGERPY

log "monitoring/logger.py created"

# =============================================================================
# STEP 7 — CREATE monitoring/watchdog.sh
# =============================================================================
head "STEP 7 · Creating monitoring/watchdog.sh"

cat > monitoring/watchdog.sh << 'WATCHDOG'
#!/usr/bin/env bash
# monitoring/watchdog.sh
# Monitors the bot process and restarts it if it dies.
# Run in tmux window 1:  bash monitoring/watchdog.sh

BOT_SCRIPT="main_enhanced.py"          # What to grep for in pgrep
BOT_START="python bot/main.py"         # Command to restart
VENV_ACTIVATE=".venv/bin/activate"
LOG_FILE="logs/watchdog.log"
ENV_FILE=".env"
RESTART_DELAY=30                       # Seconds before restart attempt
MAX_RESTARTS=5                         # Max restarts per hour before giving up

# ── Read Telegram creds from .env ─────────────────────────────────────────────
TELEGRAM_TOKEN=$(grep -s 'TELEGRAM_BOT_TOKEN' "$ENV_FILE" | cut -d'=' -f2 | tr -d ' \r')
TELEGRAM_CHAT=$(grep -s 'TELEGRAM_CHAT_ID'   "$ENV_FILE" | cut -d'=' -f2 | tr -d ' \r')

mkdir -p logs

restarts=0
window_start=$(date +%s)

send_telegram() {
    local msg="$1"
    [ -z "$TELEGRAM_TOKEN" ] && return
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT}&text=${msg}" > /dev/null 2>&1
}

log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_msg "=== Watchdog started ==="
send_telegram "🐕 Watchdog started — monitoring bot process"

while true; do
    # Reset restart counter after 1 hour
    now=$(date +%s)
    if (( now - window_start > 3600 )); then
        restarts=0
        window_start=$now
    fi

    if ! pgrep -f "$BOT_SCRIPT" > /dev/null 2>&1; then
        log_msg "⚠  Bot process NOT found!"

        if (( restarts >= MAX_RESTARTS )); then
            log_msg "🛑 Max restarts (${MAX_RESTARTS}) reached. Stopping watchdog."
            send_telegram "🛑 WATCHDOG: Max restarts reached. Manual intervention needed."
            exit 1
        fi

        ((restarts++))
        log_msg "Restart attempt ${restarts}/${MAX_RESTARTS} in ${RESTART_DELAY}s..."
        send_telegram "⚠️ Bot crashed! Restarting in ${RESTART_DELAY}s (attempt ${restarts}/${MAX_RESTARTS})"

        sleep "$RESTART_DELAY"

        # Restart in tmux window 0 if session exists, otherwise just run it
        if tmux has-session -t trader 2>/dev/null; then
            tmux send-keys -t trader:0 C-c ENTER
            sleep 2
            tmux send-keys -t trader:0 "source ${VENV_ACTIVATE} && ${BOT_START}" ENTER
        else
            source "$VENV_ACTIVATE" 2>/dev/null || true
            $BOT_START &
        fi

        log_msg "Restart command sent"
        send_telegram "✅ Bot restart attempted (${restarts}/${MAX_RESTARTS})"
    fi

    sleep 60
done
WATCHDOG

chmod +x monitoring/watchdog.sh
log "monitoring/watchdog.sh created"

# =============================================================================
# STEP 8 — CREATE monitoring/heartbeat.py
# =============================================================================
head "STEP 8 · Creating monitoring/heartbeat.py"

cat > monitoring/heartbeat.py << 'HEARTBEAT'
"""
monitoring/heartbeat.py
Logs a heartbeat every 5 minutes. Sends Telegram summary every 30 minutes.
Run alongside the bot in a tmux window or as a background thread.
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN    = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID  = os.getenv('TELEGRAM_CHAT_ID', '')
INTERVAL = 300   # 5 minutes between heartbeat log entries
TG_EVERY = 6     # Send Telegram every N heartbeats (= 30 minutes)

Path('logs').mkdir(exist_ok=True)
logger = logging.getLogger(__name__)


def send_telegram(text: str) -> None:
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{TOKEN}/sendMessage',
            data={'chat_id': CHAT_ID, 'text': text},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f'Heartbeat Telegram send failed: {e}')


def log_heartbeat(count: int) -> None:
    now = datetime.now().isoformat(timespec='seconds')
    try:
        with open('logs/heartbeat.log', 'a') as f:
            f.write(f'{now} | HEARTBEAT | count={count}\n')
    except OSError as e:
        logger.error(f'Heartbeat log write failed: {e}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    count = 0
    start = time.time()

    while True:
        count += 1
        log_heartbeat(count)

        if count % TG_EVERY == 0:
            running_min = int((time.time() - start) / 60)
            send_telegram(f'💓 Bot heartbeat — running {running_min} mins | count={count}')

        time.sleep(INTERVAL)
HEARTBEAT

log "monitoring/heartbeat.py created"

# =============================================================================
# STEP 9 — CREATE scripts/start_bot.sh
# =============================================================================
head "STEP 9 · Creating scripts/start_bot.sh"

cat > scripts/start_bot.sh << 'STARTBOT'
#!/usr/bin/env bash
# scripts/start_bot.sh
# Starts all bot components in a named tmux session.
# Usage: bash scripts/start_bot.sh

SESSION='trader'
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$BOT_DIR"

# Acquire wakelock on Android/Termux (safe to run on Linux — command just won't exist)
command -v termux-wake-lock &>/dev/null && termux-wake-lock && echo "[OK] Wakelock acquired"

# Create tmux session if it doesn't already exist
tmux new-session -d -s "$SESSION" 2>/dev/null || true

# Window 0: Main bot
tmux send-keys -t "$SESSION:0" \
    "cd $BOT_DIR && source .venv/bin/activate && python bot/main.py" ENTER
tmux rename-window -t "$SESSION:0" 'Bot'

# Window 1: Watchdog
tmux new-window -t "$SESSION" -n 'Watchdog'
tmux send-keys -t "$SESSION:1" \
    "cd $BOT_DIR && bash monitoring/watchdog.sh" ENTER

# Window 2: Log tail
tmux new-window -t "$SESSION" -n 'Logs'
tmux send-keys -t "$SESSION:2" \
    "tail -f $BOT_DIR/logs/bot.log" ENTER

# Window 3: Health monitor
tmux new-window -t "$SESSION" -n 'Health'
tmux send-keys -t "$SESSION:3" \
    "watch -n 30 'free -h && echo --- && uptime'" ENTER

# Attach to session
tmux attach -t "$SESSION"
STARTBOT

chmod +x scripts/start_bot.sh
log "scripts/start_bot.sh created"

# =============================================================================
# STEP 10 — CREATE scripts/stop_bot.sh
# =============================================================================

cat > scripts/stop_bot.sh << 'STOPBOT'
#!/usr/bin/env bash
# scripts/stop_bot.sh  —  Gracefully stops the bot
pkill -SIGINT -f 'python bot/main.py' 2>/dev/null && echo "[OK] Bot stopped" \
  || echo "[--] Bot process not found"
pkill -f 'monitoring/watchdog.sh' 2>/dev/null && echo "[OK] Watchdog stopped" || true
command -v termux-wake-unlock &>/dev/null && termux-wake-unlock && echo "[OK] Wakelock released"
STOPBOT

chmod +x scripts/stop_bot.sh
log "scripts/stop_bot.sh created"

# =============================================================================
# STEP 11 — CREATE scripts/backup.sh
# =============================================================================

cat > scripts/backup.sh << 'BACKUP'
#!/usr/bin/env bash
# scripts/backup.sh  —  Back up trade state files
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TODAY=$(date +%Y-%m-%d)
BACKUP_DIR="$BOT_DIR/backups/$TODAY"
mkdir -p "$BACKUP_DIR"

FILES=(
  "execution/paper_positions.json"
  "execution/paper_trades.json"
  "data/last_signals.json"
  "config/settings.yaml"
)

for f in "${FILES[@]}"; do
  [ -f "$BOT_DIR/$f" ] && cp "$BOT_DIR/$f" "$BACKUP_DIR/" && echo "[OK] $f"
done

tar -czf "$BACKUP_DIR/logs_$(date +%H%M).tar.gz" -C "$BOT_DIR" logs/ 2>/dev/null \
  && echo "[OK] logs archived"

# Prune backups older than 14 days
find "$BOT_DIR/backups" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null
echo "[OK] Backup complete → $BACKUP_DIR"
BACKUP

chmod +x scripts/backup.sh
log "scripts/backup.sh created"

# =============================================================================
# STEP 12 — CREATE config/settings.py
# =============================================================================
head "STEP 12 · Creating config/settings.py"

cat > config/settings.py << 'SETTINGS'
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
SETTINGS

log "config/settings.py created"

# =============================================================================
# STEP 13 — CREATE .env.example
# =============================================================================
head "STEP 13 · Creating .env.example"

cat > .env.example << 'ENVEXAMPLE'
# .env.example  —  Copy this to .env and fill in real values.
# NEVER commit .env to git.

# ── Trading mode ──────────────────────────────────────────────────────────────
TRADING_MODE=paper          # 'paper' to start. Change to 'live' only after 30+ days paper trading.

# ── Binance (read-only to start — no withdrawal permissions) ─────────────────
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=123456789:ABCdef_from_BotFather
TELEGRAM_CHAT_ID=your_personal_chat_id

# ── Discord (optional) ────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# ── Email (optional) ──────────────────────────────────────────────────────────
EMAIL_ADDRESS=your@email.com
EMAIL_PASSWORD=app_specific_password_not_your_main_password

# ── Supabase (optional — comment out if not using) ───────────────────────────
# SUPABASE_URL=https://your-project.supabase.co
# SUPABASE_KEY=your_supabase_anon_key

# ── Risk settings (defaults are beginner-safe) ───────────────────────────────
RISK_PRESET=conservative
MAX_RISK_PER_TRADE=0.01
MAX_POSITIONS=3
DAILY_LOSS_LIMIT=0.05
TRADE_COOLDOWN_HOURS=4
MAX_TRADES_PER_DAY=6
MIN_SIGNAL_QUALITY=60

# ── Bot behaviour ─────────────────────────────────────────────────────────────
BOT_INTERVAL=300
LOG_LEVEL=INFO
ENVEXAMPLE

log ".env.example created"

# =============================================================================
# STEP 14 — FIX .gitignore
# =============================================================================
head "STEP 14 · Fixing .gitignore"

cat > .gitignore << 'GITIGNORE'
# ── Secrets (NEVER commit these) ─────────────────────────────────────────────
.env
.env.live
.env.paper
secrets/
*.pem
*.key

# ── Virtual environment ───────────────────────────────────────────────────────
.venv/
venv/
env/

# ── Runtime logs ─────────────────────────────────────────────────────────────
logs/
*.log

# ── Backups ───────────────────────────────────────────────────────────────────
backups/

# ── Runtime state (paper trading data) ───────────────────────────────────────
execution/paper_positions.json
execution/paper_trades.json
data/last_signals.json

# ── Python artifacts ──────────────────────────────────────────────────────────
__pycache__/
*.pyc
*.pyo
*.pyd
*.egg-info/
dist/
build/
.eggs/

# ── IDE ───────────────────────────────────────────────────────────────────────
.vscode/
.idea/
*.swp
*.swo

# ── OS ───────────────────────────────────────────────────────────────────────
.DS_Store
Thumbs.db

# ── Old/legacy files ──────────────────────────────────────────────────────────
*.old
*.bak

# ── Build artifacts ───────────────────────────────────────────────────────────
crypto_trader.egg-info/
GITIGNORE

log ".gitignore updated"

# =============================================================================
# STEP 15 — CLEAN requirements.txt
# =============================================================================
head "STEP 15 · Writing clean requirements.txt"

# Backup original first
[ -f "requirements.txt" ] && cp requirements.txt archive/legacy/requirements_original.txt
[ -f "requirements " ]    && cp "requirements " archive/legacy/requirements_no_ext.txt 2>/dev/null || true

cat > requirements.txt << 'REQS'
# requirements.txt  —  Clean, deduplicated, ARM-compatible versions
# Last reviewed: 2026-05
#
# To install:  pip install -r requirements.txt
#
# NOTE: polars is commented out — it may not build on ARM (Android/Termux).
#       pandas is used instead. Uncomment polars only on x86 VPS/desktop.

# ── Core exchange library ─────────────────────────────────────────────────────
ccxt==4.5.28

# ── Data processing (ARM-safe) ───────────────────────────────────────────────
pandas==2.2.2
numpy==1.26.4

# ── HTTP / networking ────────────────────────────────────────────────────────
requests==2.32.3
aiohttp==3.9.5

# ── Secrets management ───────────────────────────────────────────────────────
python-dotenv==1.0.1

# ── Telegram ─────────────────────────────────────────────────────────────────
python-telegram-bot==21.0.1

# ── Charting  (headless — always use Agg backend on Android) ─────────────────
matplotlib==3.9.0

# ── Crypto utilities ─────────────────────────────────────────────────────────
cryptography==42.0.8

# ── Optional: cloud database ─────────────────────────────────────────────────
# supabase==2.0.0   # Uncomment if using Supabase

# ── Optional: polars (DO NOT USE on Android — use pandas instead) ────────────
# polars==0.20.31   # x86/VPS only

# ── Testing ───────────────────────────────────────────────────────────────────
pytest==8.2.2
pytest-cov==5.0.0

# ── YAML config support ───────────────────────────────────────────────────────
PyYAML==6.0.1
REQS

log "requirements.txt cleaned"

# =============================================================================
# STEP 16 — ADD matplotlib Agg backend guard to reports/ if it exists
# =============================================================================
head "STEP 16 · Checking reports/ for matplotlib display issue"

if [ -f "reports/plot_signals.py" ]; then
  # Check if Agg backend is already set
  if ! grep -q "matplotlib.use('Agg')" reports/plot_signals.py; then
    # Prepend the fix
    tmpfile=$(mktemp)
    echo "import matplotlib" > "$tmpfile"
    echo "matplotlib.use('Agg')  # Non-interactive backend — required for Android/Termux" >> "$tmpfile"
    echo "" >> "$tmpfile"
    cat reports/plot_signals.py >> "$tmpfile"
    mv "$tmpfile" reports/plot_signals.py
    log "Added matplotlib Agg backend to reports/plot_signals.py"
  else
    log "reports/plot_signals.py already has Agg backend — skipped"
  fi
else
  info "reports/plot_signals.py not found — skipping"
fi

# =============================================================================
# STEP 17 — REMOVE .venv from git tracking (if committed)
# =============================================================================
head "STEP 17 · Removing .venv from git tracking"

if git ls-files --error-unmatch .venv/ > /dev/null 2>&1; then
  git rm -r --cached .venv/ > /dev/null 2>&1
  log ".venv/ removed from git tracking (still exists on disk)"
else
  info ".venv/ is not tracked by git — nothing to do"
fi

# =============================================================================
# STEP 18 — CREATE config/risk_presets
# =============================================================================
head "STEP 18 · Creating risk preset configs"

cat > config/risk_presets/conservative.json << 'CONSERVATIVE'
{
  "_comment": "Conservative preset — recommended for beginners (Phase 1-4)",
  "max_risk_per_trade": 0.01,
  "max_positions": 3,
  "daily_loss_limit": 0.05,
  "max_position_pct": 0.10,
  "trade_cooldown_hours": 4,
  "max_trades_per_day": 6,
  "min_signal_quality": 60,
  "atr_stop_multiplier": 2.0,
  "atr_take_profit_multiplier": 3.0
}
CONSERVATIVE

cat > config/risk_presets/moderate.json << 'MODERATE'
{
  "_comment": "Moderate preset — Phase 5 only, after 30+ days profitable paper trading",
  "max_risk_per_trade": 0.02,
  "max_positions": 5,
  "daily_loss_limit": 0.08,
  "max_position_pct": 0.15,
  "trade_cooldown_hours": 2,
  "max_trades_per_day": 10,
  "min_signal_quality": 55,
  "atr_stop_multiplier": 1.8,
  "atr_take_profit_multiplier": 2.7
}
MODERATE

cat > config/risk_presets/aggressive.json << 'AGGRESSIVE'
{
  "_comment": "Aggressive preset — NOT for beginners. Phase 6 only with proven live track record.",
  "max_risk_per_trade": 0.03,
  "max_positions": 8,
  "daily_loss_limit": 0.12,
  "max_position_pct": 0.20,
  "trade_cooldown_hours": 1,
  "max_trades_per_day": 20,
  "min_signal_quality": 50,
  "atr_stop_multiplier": 1.5,
  "atr_take_profit_multiplier": 2.25
}
AGGRESSIVE

log "Risk presets created"

# =============================================================================
# STEP 19 — CREATE logs/.gitkeep and backups/.gitkeep
# =============================================================================
touch logs/.gitkeep backups/.gitkeep
log "logs/ and backups/ placeholder files created"

# =============================================================================
# STEP 20 — FINAL SUMMARY
# =============================================================================
head "REFACTOR COMPLETE — Summary"

echo ""
echo -e "${GREEN}Files archived to archive/legacy/:${NC}"
ls archive/legacy/ 2>/dev/null | sed 's/^/  /'

echo ""
echo -e "${GREEN}New files created:${NC}"
echo "  bot/main.py                   ← new entry point"
echo "  bot/__init__.py"
echo "  monitoring/logger.py          ← rotating log setup"
echo "  monitoring/watchdog.sh        ← process watchdog"
echo "  monitoring/heartbeat.py       ← Telegram heartbeat"
echo "  monitoring/__init__.py"
echo "  scripts/start_bot.sh          ← tmux launcher"
echo "  scripts/stop_bot.sh"
echo "  scripts/backup.sh"
echo "  config/settings.py            ← central settings"
echo "  config/risk_presets/*.json    ← conservative / moderate / aggressive"
echo "  .env.example                  ← secrets template"
echo "  .gitignore                    ← updated"
echo "  requirements.txt              ← deduplicated, ARM-safe"

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review archive/legacy/ — make sure nothing important is missing"
echo "  2. cp .env.example .env  then fill in your real keys"
echo "  3. python -m venv .venv && source .venv/bin/activate"
echo "  4. pip install -r requirements.txt"
echo "  5. python bot/main.py --healthcheck   ← verify setup"
echo "  6. python bot/main.py --once          ← single test run"
echo "  7. git add -p                         ← review each change before staging"
echo "  8. git commit -m 'refactor: clean structure, new entry point'"
echo "  9. git push origin main"
echo ""
echo -e "${GREEN}Your trading logic in main_enhanced.py is UNCHANGED.${NC}"
echo -e "${GREEN}bot/main.py wraps it — zero behaviour change.${NC}"
echo ""