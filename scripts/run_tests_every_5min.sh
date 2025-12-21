#!/usr/bin/env bash
set -e

# Run tests from repo root, activate virtualenv if present, log output
cd "$(dirname "$0")/.."

# Acquire a non-blocking lock to avoid overlapping runs (fd 200)
LOCKFILE=/tmp/crypto_trader_test.lock
exec 200>"$LOCKFILE"
flock -n 200 || {
    echo "$(date +"%Y-%m-%d %H:%M:%S") - Another instance is running, exiting." >&2
    exit 0
}

# Try common venv locations
if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
elif [ -f venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

mkdir -p logs
TS=$(date +"%Y-%m-%d %H:%M:%S")
{
    echo "--- TEST RUN: $TS ---"
    python3 test_paper_trader.py
    echo "--- END TEST RUN ---\n"
} >> logs/test_run.log 2>&1 || echo "Test runner exited with non-zero status at $TS" >> logs/test_run.log

# release lock (file descriptor 200 will close on script exit)
exit 0
