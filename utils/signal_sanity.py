"""
Signal Sanity - Prevent duplicate/conflicting signals
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

SIGNAL_HISTORY_FILE = Path("data") / "signal_history.json"

def load_signal_history() -> dict:
    """Load recent signal history"""
    if not SIGNAL_HISTORY_FILE.exists():
        return {}
    
    try:
        with open(SIGNAL_HISTORY_FILE) as f:
            return json.load(f)
    except:
        return {}


def save_signal_history(history: dict):
    """Save signal history"""
    SIGNAL_HISTORY_FILE.parent.mkdir(exist_ok=True)
    with open(SIGNAL_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)


def check_duplicate_signal(
    coin: str,
    signal: int,
    within_minutes: int = 15
) -> tuple[bool, str]:
    """
    Check if this exact signal was already generated recently.
    
    Args:
        coin: Coin pair
        signal: Signal value (1, -1, 0)
        within_minutes: Time window to check (default 15)
        
    Returns:
        tuple: (is_valid, reason)
    """
    history = load_signal_history()
    
    if coin not in history:
        return True, "No recent signal"
    
    last_signal = history[coin]
    last_signal_value = last_signal.get("signal")
    last_signal_time = datetime.fromisoformat(last_signal.get("timestamp"))
    
    time_since = datetime.now() - last_signal_time
    
    # If same signal within time window, it's a duplicate
    if signal == last_signal_value and time_since < timedelta(minutes=within_minutes):
        mins_ago = int(time_since.total_seconds() / 60)
        return False, f"Duplicate signal: same signal {mins_ago}min ago"
    
    return True, "Signal is new"


def check_signal_flip_flop(
    coin: str,
    signal: int,
    min_time_between_flips: int = 30
) -> tuple[bool, str]:
    """
    Detect rapid signal changes (flip-flopping).
    
    Args:
        coin: Coin pair
        signal: New signal
        min_time_between_flips: Minimum minutes between opposite signals
        
    Returns:
        tuple: (is_valid, reason)
    """
    history = load_signal_history()
    
    if coin not in history:
        return True, "No history to check"
    
    last_signal = history[coin]
    last_signal_value = last_signal.get("signal")
    last_signal_time = datetime.fromisoformat(last_signal.get("timestamp"))
    
    time_since = datetime.now() - last_signal_time
    
    # Check if opposite signal within time window
    is_opposite = (signal == 1 and last_signal_value == -1) or (signal == -1 and last_signal_value == 1)
    
    if is_opposite and time_since < timedelta(minutes=min_time_between_flips):
        mins_ago = int(time_since.total_seconds() / 60)
        return False, f"Flip-flop detected: opposite signal {mins_ago}min ago"
    
    return True, "No flip-flop detected"


def record_signal(coin: str, signal: int, signal_quality: float = None):
    """Record signal for history tracking"""
    history = load_signal_history()
    
    history[coin] = {
        "signal": signal,
        "timestamp": datetime.now().isoformat(),
        "signal_quality": signal_quality
    }
    
    save_signal_history(history)


def check_signal_quality_threshold(
    signal_quality: float,
    min_quality: float = 40.0
) -> tuple[bool, str]:
    """
    Check if signal quality meets minimum threshold.
    
    Args:
        signal_quality: Quality score 0-100
        min_quality: Minimum required quality
        
    Returns:
        tuple: (is_valid, reason)
    """
    if signal_quality is None:
        return True, "No quality data"
    
    if signal_quality < min_quality:
        return False, f"Quality too low: {signal_quality:.0f} < {min_quality:.0f}"
    
    return True, f"Quality OK: {signal_quality:.0f}"


# CUSTOMIZE HERE:
# - Line 36: within_minutes = 15 - Time to consider signals duplicates
# - Line 74: min_time_between_flips = 30 - Prevent rapid BUY->SELL->BUY changes
# - Line 126: min_quality = 40.0 - Minimum signal quality to accept