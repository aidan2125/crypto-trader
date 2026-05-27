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
