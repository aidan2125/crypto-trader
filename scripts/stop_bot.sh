#!/usr/bin/env bash
# scripts/stop_bot.sh  —  Gracefully stops the bot
pkill -SIGINT -f 'python bot/main.py' 2>/dev/null && echo "[OK] Bot stopped" \
  || echo "[--] Bot process not found"
pkill -f 'monitoring/watchdog.sh' 2>/dev/null && echo "[OK] Watchdog stopped" || true
command -v termux-wake-unlock &>/dev/null && termux-wake-unlock && echo "[OK] Wakelock released"
