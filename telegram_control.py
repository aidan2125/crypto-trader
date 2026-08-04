#!/usr/bin/env python3
"""
Telegram Control Bot - Improved Version
Changes are annotated with: # CHANGE: <reason>
"""
import os
import logging
import json
import fcntl                                          # CHANGE: added for file locking
from datetime import datetime,timezone
from functools import wraps                           # CHANGE: added for auth decorator
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
load_dotenv()
# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# CHANGE: support a comma-separated list of allowed user IDs instead of just one
_raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", os.getenv("TELEGRAM_ALLOWED_USER_ID", ""))
ALLOWED_USER_IDS: set[int] = set()
for _id in _raw_ids.split(","):
    _id = _id.strip()
    if _id.isdigit():
        ALLOWED_USER_IDS.add(int(_id))

# CHANGE: configurable trade history limit via env var (default 10)
TRADES_DISPLAY_LIMIT = int(os.getenv("TRADES_DISPLAY_LIMIT", "10"))

# CHANGE: stale-data threshold in seconds (default 5 minutes)
STALE_DATA_THRESHOLD = int(os.getenv("STALE_DATA_THRESHOLD_SECONDS", "300"))

# File paths
DATA_DIR = Path("data")
POSITIONS_FILE    = DATA_DIR / "positions.json"
TRADES_FILE       = DATA_DIR / "trades.json"
LAST_SIGNALS_FILE = DATA_DIR / "last_signals.json"
HEARTBEAT_FILE    = DATA_DIR / "heartbeat.json"       # CHANGE: new — trading bot writes this


# ─────────────────────────────────────────────
# CHANGE: improved load_json — distinguishes "file missing" from "file corrupt"
#         and uses fcntl file locking to prevent partial reads during concurrent writes
# ─────────────────────────────────────────────
def load_json(filepath, default=None):
    """Load JSON file safely with file locking."""
    filepath = Path(filepath)
    if not filepath.exists():
        return default if default is not None else {}
    try:
        with open(filepath, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)           # CHANGE: shared (read) lock
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except json.JSONDecodeError as e:
        logger.error(f"Corrupt JSON in {filepath}: {e}")   # CHANGE: specific error type
        return default if default is not None else {}
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return default if default is not None else {}


# ─────────────────────────────────────────────
# CHANGE: auth is now a decorator instead of copy-pasted if-blocks in every handler
# ─────────────────────────────────────────────
def authorized_only(func):
    """Decorator: silently drop requests from unauthorized users."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in ALLOWED_USER_IDS:
            logger.warning(f"Unauthorized /{func.__name__} attempt from user {uid}")
            return                                    # CHANGE: no reply to unknown users
        return await func(update, context)
    return wrapper


# ─────────────────────────────────────────────
# CHANGE: new helper — checks heartbeat file written by the trading bot
#         returns (is_alive: bool, age_seconds: float | None)
# ─────────────────────────────────────────────
def check_trading_bot_health() -> tuple[bool, float | None]:
    """Return (alive, age_in_seconds). alive=False if no heartbeat or too old."""
    hb = load_json(HEARTBEAT_FILE, {})
    ts_str = hb.get("timestamp")
    if not ts_str:
        return False, None
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age < STALE_DATA_THRESHOLD, age
    except ValueError:
        return False, None

# ─────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────

@authorized_only                                      # CHANGE: uses decorator
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    message = (
        "Crypto Trading Bot Control\n\n"
        "Available Commands:\n"
        "/status    - Show bot status & health\n"
        "/positions - List open positions\n"
        "/signals   - Show last signals\n"
        "/trades    - Show recent trades\n"
        "/trades N  - Show last N trades\n"   # CHANGE: documents the new N argument
        "/pause     - Pause trading\n"        # CHANGE: new command
        "/resume    - Resume trading\n"       # CHANGE: new command
        "/help      - Show this message\n"
    )
    await update.message.reply_text(message)


@authorized_only                                      # CHANGE: uses decorator
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    message = (
        "Crypto Trading Bot Commands:\n\n"
        "/start         - Welcome message\n"
        "/status        - Show bot status & health check\n"
        "/positions     - List all open positions\n"
        "/signals       - Show last signal for each coin\n"
        "/trades [N]    - Show last N trades (default: 10)\n"
        "/pause         - Pause the trading bot\n"
        "/resume        - Resume the trading bot\n"
        "/help          - Show this message\n\n"
        "Bot is running in paper trading mode."
    )
    await update.message.reply_text(message)


@authorized_only                                      # CHANGE: uses decorator
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    try:
        positions = load_json(POSITIONS_FILE, {})
        trades    = load_json(TRADES_FILE, [])

        # Cost basis (unchanged from original)
        total_cost = sum(
            p.get('quantity', 0) * p.get('entry_price', 0)
            for p in positions.values()
        )

        # CHANGE: calculate realised P&L from closed trades
        realised_pnl = sum(
            t.get('pnl', 0) for t in trades if isinstance(t, dict)
        )

        # CHANGE: check trading-bot heartbeat
        alive, age = check_trading_bot_health()
        if alive:
            health_line = f"Trading Bot: Online (last heartbeat {age:.0f}s ago)"
        elif age is not None:
            health_line = f"Trading Bot: STALE (last heartbeat {age:.0f}s ago) - check process!"
        else:
            health_line = "Trading Bot: NO HEARTBEAT - may be offline!"

        # CHANGE: read pause state
        pause_state = load_json(DATA_DIR / "pause_state.json", {})
        paused = pause_state.get("paused", False)
        trade_status = "PAUSED" if paused else "Running"

        message = (
            f"Bot Status Report\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Open Positions:  {len(positions)}\n"
            f"Cost Basis:      ${total_cost:.2f}\n"
            f"Realised P&L:    ${realised_pnl:+.2f}\n"   # CHANGE: shows P&L with sign
            f"Total Trades:    {len([t for t in trades if isinstance(t, dict)])}\n\n"
            f"Trade Status:    {trade_status}\n"
            f"{health_line}\n"                            # CHANGE: health check line
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /status: {e}")
        await update.message.reply_text(f"Error fetching status: {e}")


@authorized_only                                      # CHANGE: uses decorator
async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /positions command."""
    try:
        positions_data = load_json(POSITIONS_FILE, {})

        if not positions_data:
            await update.message.reply_text("No open positions")
            return

        message = "Open Positions:\n\n"

        for coin, pos in positions_data.items():
            entry_price  = pos.get('entry_price', 0)
            quantity     = pos.get('quantity', 0)
            stop_loss    = pos.get('stop_loss', 0)
            take_profit  = pos.get('take_profit', 0)
            current_price = pos.get('current_price', entry_price)  # CHANGE: use current_price if available

            # CHANGE: show unrealised P&L per position
            unrealised = (current_price - entry_price) * quantity
            pnl_sign   = "+" if unrealised >= 0 else ""

            message += (
                f"{coin}\n"
                f"  Quantity:    {quantity:.6f}\n"
                f"  Entry:       ${entry_price:.2f}\n"
                f"  Current:     ${current_price:.2f}\n"  # CHANGE: current price line
                f"  Stop Loss:   ${stop_loss:.2f}\n"
                f"  Take Profit: ${take_profit:.2f}\n"
                f"  Cost Basis:  ${entry_price * quantity:.2f}\n"
                f"  Unrealised:  ${pnl_sign}{unrealised:.2f}\n\n"  # CHANGE: unrealised P&L
            )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /positions: {e}")
        await update.message.reply_text(f"Error fetching positions: {e}")


@authorized_only                                      # CHANGE: uses decorator
async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /signals command."""
    try:
        signals_data = load_json(LAST_SIGNALS_FILE, {})

        if not signals_data:
            await update.message.reply_text("No signal data available")
            return

        signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}

        # CHANGE: check if signal data is stale
        signals_meta = load_json(DATA_DIR / "last_signals_meta.json", {})
        ts_str = signals_meta.get("timestamp")
        staleness = ""
        if ts_str:
            try:
                age = (datetime.now() - datetime.fromisoformat(ts_str)).total_seconds()
                if age > STALE_DATA_THRESHOLD:
                    staleness = f"  WARNING: signals are {age/60:.0f} min old\n"
            except ValueError:
                pass

        message = f"Last Signals:\n{staleness}\n"

        for coin, signal in signals_data.items():
            signal_text = signal_names.get(signal, str(signal))
            message += f"  {coin}: {signal_text}\n"

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /signals: {e}")
        await update.message.reply_text(f"Error fetching signals: {e}")


@authorized_only                                      # CHANGE: uses decorator
async def trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trades [N] command."""
    # CHANGE: accept an optional numeric argument, e.g. /trades 20
    limit = TRADES_DISPLAY_LIMIT
    if context.args:
        try:
            limit = max(1, min(int(context.args[0]), 100))  # clamp to 1–100
        except ValueError:
            await update.message.reply_text("Usage: /trades [number]  e.g. /trades 20")
            return

    try:
        trades_data = load_json(TRADES_FILE, [])

        if not trades_data:
            await update.message.reply_text("No trade history available")
            return

        recent_trades = trades_data[-limit:]
        message = f"Recent Trades (Last {len(recent_trades)}):\n\n"

        for trade in reversed(recent_trades):
            if not isinstance(trade, dict):
                continue

            coin      = trade.get('coin', 'Unknown')
            action    = trade.get('action', 'Unknown')
            price     = trade.get('price', 0)
            quantity  = trade.get('quantity', 0)
            pnl       = trade.get('pnl', 0)
            timestamp = trade.get('timestamp', 'Unknown')

            pnl_sign = "+" if pnl > 0 else ""

            message += (
                f"{coin} - {action}\n"
                f"  Price: ${price:.2f}\n"
                f"  Qty:   {quantity:.6f}\n"
                f"  P/L:   ${pnl_sign}{pnl:.2f}\n"   # CHANGE: no abs(), show raw sign
                f"  Time:  {timestamp}\n\n"
            )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /trades: {e}")
        await update.message.reply_text(f"Error fetching trades: {e}")


# ─────────────────────────────────────────────
# CHANGE: new /pause and /resume commands
#         writes a pause_state.json that the trading bot should honour
# ─────────────────────────────────────────────

@authorized_only
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pause command — write pause flag for the trading bot."""
    try:
        pause_file = DATA_DIR / "pause_state.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(pause_file, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump({"paused": True, "since": datetime.now().isoformat()}, f)
            fcntl.flock(f, fcntl.LOCK_UN)
        await update.message.reply_text("Trading PAUSED. Use /resume to restart.")
        logger.info(f"Trading paused by user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in /pause: {e}")
        await update.message.reply_text(f"Error setting pause: {e}")


@authorized_only
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resume command — clear pause flag for the trading bot."""
    try:
        pause_file = DATA_DIR / "pause_state.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(pause_file, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump({"paused": False, "since": datetime.now().isoformat()}, f)
            fcntl.flock(f, fcntl.LOCK_UN)
        await update.message.reply_text("Trading RESUMED.")
        logger.info(f"Trading resumed by user {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error in /resume: {e}")
        await update.message.reply_text(f"Error clearing pause: {e}")


# ─────────────────────────────────────────────
# CHANGE: new push-notification helper
#         Call this from your trading bot (or a shared module) to push alerts
# ─────────────────────────────────────────────

async def send_alert(application: Application, text: str):
    """
    Push a notification to all authorised users.
    Example usage from the trading bot:
        await send_alert(application, "BTCUSDT SELL filled at $65,000 | P&L: +$320")
    """
    for uid in ALLOWED_USER_IDS:
        try:
            await application.bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            logger.error(f"Failed to send alert to {uid}: {e}")


# ─────────────────────────────────────────────
# Error handler
# ─────────────────────────────────────────────

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        print("\nERROR: TELEGRAM_BOT_TOKEN environment variable not set")
        print("Set it with: export TELEGRAM_BOT_TOKEN='your_token_here'\n")
        return

    # CHANGE: validate the new multi-ID variable (also accepts old single-ID var)
    if not ALLOWED_USER_IDS:
        logger.error("No authorised user IDs configured")
        print("\nERROR: Set TELEGRAM_ALLOWED_USER_IDS (comma-separated) or TELEGRAM_ALLOWED_USER_ID")
        print("Example: export TELEGRAM_ALLOWED_USER_IDS='111111,222222'\n")
        return

    logger.info("Starting Telegram Control Bot...")
    print("\nTelegram Control Bot Starting...")
    print(f"Authorised User IDs: {ALLOWED_USER_IDS}")
    print("Press Ctrl+C to stop\n")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start",   start))
    application.add_handler(CommandHandler("help",    help_command))
    application.add_handler(CommandHandler("status",  status))
    application.add_handler(CommandHandler("positions", positions))
    application.add_handler(CommandHandler("signals", signals))
    application.add_handler(CommandHandler("trades",  trades))
    application.add_handler(CommandHandler("pause",   pause))    # CHANGE: new
    application.add_handler(CommandHandler("resume",  resume))   # CHANGE: new

    application.add_error_handler(error_handler)

    try:
        logger.info("Bot is running. Press Ctrl+C to stop.")
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\nBot stopped gracefully")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        print(f"\nBot error: {e}")


if __name__ == "__main__":
    main()
