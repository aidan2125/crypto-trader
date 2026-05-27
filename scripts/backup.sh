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
