#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# Activate venv if present
if [ -f venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi
# Load secrets if present
if [ -f "$HOME/.config/crypto-trader/alerts.env" ]; then
    # shellcheck disable=SC1091
    source "$HOME/.config/crypto-trader/alerts.env"
fi

LOG=logs/simulation_continuous.log
mkdir -p logs
echo "=== STARTING CONTINUOUS SIMULATION $(date -u +"%Y-%m-%dT%H:%M:%SZ") ===" >> "$LOG"

while true; do
    echo "--- RUN START: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ---" >> "$LOG"
    /home/aidan/crypto-trader/venv/bin/python3 main.py >> "$LOG" 2>&1 || echo "RUN FAILED at $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$LOG"
    echo "--- RUN END: $(date -u +"%Y-%m-%dT%H:%M:%SZ") ---" >> "$LOG"
    sleep 60
done
