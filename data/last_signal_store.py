import json
from pathlib import Path

SIGNAL_FILE = Path("data/last_signals.json")

def load_last_signals():
    if SIGNAL_FILE.exists():
        try:
            with open(SIGNAL_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}  # corrupted file → start fresh
    return {}

def save_last_signals(signals):
    # convert all values to standard Python types
    signals_clean = {k: int(v) for k, v in signals.items()}
    with open(SIGNAL_FILE, "w") as f:
        json.dump(signals_clean, f, indent=4)
