#!/usr/bin/env python3
"""
Check recent continuous simulation runs for failures and send alert when consecutive failures exceed threshold.
"""
import json
import os
from pathlib import Path
from datetime import datetime

from alerts.telegram_alerts import send_telegram_message
from alerts.email_alerts import send_email

LOG = Path("logs/simulation_continuous.log")
STATE_FILE = Path(".alerts_state.json")
THRESHOLD = 3  # send alert after this many consecutive failed runs
LOOKBACK_RUNS = 5  # consider up to this many recent runs when counting


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def parse_runs(log_text):
    # Split on run start markers
    parts = log_text.split("--- RUN START:")
    runs = []
    for p in parts[1:]:
        # each p starts with timestamp then content until next RUN START
        runs.append(p)
    return runs


def run_check():
    if not LOG.exists():
        return

    text = LOG.read_text()
    runs = parse_runs(text)
    if not runs:
        return

    recent = runs[-LOOKBACK_RUNS:]
    # Count consecutive failures from the most recent run backwards
    consecutive_failures = 0
    for r in reversed(recent):
        if "RUN FAILED" in r or "ERROR:" in r or "Exception" in r:
            consecutive_failures += 1
        else:
            break

    state = load_state()
    last_alert_count = state.get("last_alert_count", 0)

    if consecutive_failures >= THRESHOLD and consecutive_failures > last_alert_count:
        # send alert
        ts = datetime.utcnow().isoformat()
        msg = f"ALERT: Continuous simulation has {consecutive_failures} consecutive failed runs as of {ts}. Check logs: logs/simulation_continuous.log"
        try:
            send_telegram_message(msg)
        except Exception:
            pass
        try:
            send_email(subject="Crypto-trader simulation alert", body=msg)
        except Exception:
            pass
        state["last_alert_count"] = consecutive_failures
        state["last_alert_time"] = ts
        save_state(state)
    elif consecutive_failures == 0 and last_alert_count != 0:
        # clear alert state when system recovers
        state["last_alert_count"] = 0
        state["last_recovered_time"] = datetime.utcnow().isoformat()
        save_state(state)


if __name__ == "__main__":
    run_check()
