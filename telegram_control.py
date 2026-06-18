#!/usr/bin/env python3
"""
Telegram Control Bot - Standalone Version
Fixed event loop handling, no emojis
"""
import os
import logging
import json
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")

# File paths
POSITIONS_FILE = Path("data") / "positions.json"
TRADES_FILE = Path("data") / "trades.json"
LAST_SIGNALS_FILE = Path("data") / "last_signals.json"

def load_json(filepath, default=None):
    """Load JSON file safely."""
    filepath = Path(filepath)
    if filepath.exists():
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
    return default if default is not None else {}

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized."""
    if not ALLOWED_USER_ID:
        return False
    try:
        return user_id == int(ALLOWED_USER_ID)
    except (ValueError, TypeError):
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized /start from {update.effective_user.id}")
        return

    message = (
        "Crypto Trading Bot Control\n\n"
        "Available Commands:\n"
        "/status - Show bot status\n"
        "/positions - List open positions\n"
        "/signals - Show last signals\n"
        "/trades - Show recent trades\n"
        "/help - Show this message\n"
    )
    await update.message.reply_text(message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized /help from {update.effective_user.id}")
        return

    message = (
        "Crypto Trading Bot Commands:\n\n"
        "/start - Welcome message\n"
        "/status - Show bot status\n"
        "/positions - List all open positions\n"
        "/signals - Show last signal for each coin\n"
        "/trades - Show recent trade history\n"
        "/help - Show this message\n\n"
        "Bot is running in paper trading mode."
    )
    await update.message.reply_text(message)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized /status from {update.effective_user.id}")
        return

    try:
        positions = load_json(POSITIONS_FILE, {})
        trades = load_json(TRADES_FILE, [])

        # Calculate portfolio value
        total_value = 0.0
        for coin, pos in positions.items():
            total_value += pos.get('quantity', 0) * pos.get('entry_price', 0)

        # Count recent trades
        recent_trades = len([t for t in trades if isinstance(t, dict)])

        message = (
            f"Bot Status Report\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Open Positions: {len(positions)}\n"
            f"Portfolio Value: ${total_value:.2f}\n"
            f"Total Trades: {recent_trades}\n\n"
            f"Status: Running"
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /status: {e}")
        await update.message.reply_text(f"Error fetching status: {e}")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /positions command."""
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized /positions from {update.effective_user.id}")
        return

    try:
        positions_data = load_json(POSITIONS_FILE, {})

        if not positions_data:
            await update.message.reply_text("No open positions")
            return

        message = "Open Positions:\n\n"

        for coin, pos in positions_data.items():
            entry_price = pos.get('entry_price', 0)
            quantity = pos.get('quantity', 0)
            stop_loss = pos.get('stop_loss', 0)
            take_profit = pos.get('take_profit', 0)

            message += (
                f"{coin}\n"
                f" Quantity: {quantity:.6f}\n"
                f" Entry: ${entry_price:.2f}\n"
                f" Stop Loss: ${stop_loss:.2f}\n"
                f" Take Profit: ${take_profit:.2f}\n"
                f" Value: ${entry_price * quantity:.2f}\n\n"
            )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /positions: {e}")
        await update.message.reply_text(f"Error fetching positions: {e}")

async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /signals command."""
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized /signals from {update.effective_user.id}")
        return

    try:
        signals_data = load_json(LAST_SIGNALS_FILE, {})

        if not signals_data:
            await update.message.reply_text("No signal data available")
            return

        signal_names = {-1: "SELL", 0: "HOLD", 1: "BUY"}

        message = "Last Signals:\n\n"

        for coin, signal in signals_data.items():
            signal_text = signal_names.get(signal, str(signal))
            message += f"{coin}: {signal_text}\n"

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /signals: {e}")
        await update.message.reply_text(f"Error fetching signals: {e}")

async def trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trades command."""
    if not is_authorized(update.effective_user.id):
        logger.warning(f"Unauthorized /trades from {update.effective_user.id}")
        return

    try:
        trades_data = load_json(TRADES_FILE, [])

        if not trades_data:
            await update.message.reply_text("No trade history available")
            return

        # Show last 10 trades
        recent_trades = trades_data[-10:] if len(trades_data) > 10 else trades_data

        message = f"Recent Trades (Last {len(recent_trades)}):\n\n"

        for trade in reversed(recent_trades):
            if not isinstance(trade, dict):
                continue

            coin = trade.get('coin', 'Unknown')
            action = trade.get('action', 'Unknown')
            price = trade.get('price', 0)
            quantity = trade.get('quantity', 0)
            pnl = trade.get('pnl', 0)
            timestamp = trade.get('timestamp', 'Unknown')

            pnl_sign = "+" if pnl > 0 else "-" if pnl < 0 else ""

            message += (
                f"{coin} - {action}\n"
                f" Price: ${price:.2f}\n"
                f" Qty: {quantity:.6f}\n"
                f" P/L: ${pnl_sign}{abs(pnl):.2f}\n"
                f" Time: {timestamp}\n\n"
            )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in /trades: {e}")
        await update.message.reply_text(f"Error fetching trades: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot."""
    # Validate environment variables
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        print("\nERROR: TELEGRAM_BOT_TOKEN environment variable not set")
        print("Set it with: export TELEGRAM_BOT_TOKEN='your_token_here'\n")
        return

    if not ALLOWED_USER_ID:
        logger.error("TELEGRAM_ALLOWED_USER_ID not set")
        print("\nERROR: TELEGRAM_ALLOWED_USER_ID environment variable not set")
        print("Set it with: export TELEGRAM_ALLOWED_USER_ID='your_user_id_here'\n")
        return

    logger.info("Starting Telegram Control Bot...")
    print("\nTelegram Control Bot Starting...")
    print(f"Authorized User ID: {ALLOWED_USER_ID}")
    print("Press Ctrl+C to stop\n")

    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("positions", positions))
    application.add_handler(CommandHandler("signals", signals))
    application.add_handler(CommandHandler("trades", trades))

    # Add error handler
    application.add_error_handler(error_handler)

    # Run the bot
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
