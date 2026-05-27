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
