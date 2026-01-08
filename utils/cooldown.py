"""
Cooldown Manager - Prevents overtrading same pair
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

COOLDOWN_FILE = Path("data") / "trade_cooldowns.json"

def load_cooldowns() -> dict:
    """Load cooldown state"""
    if not COOLDOWN_FILE.exists():
        return {}
    
    try:
        with open(COOLDOWN_FILE) as f:
            return json.load(f)
    except:
        return {}


def save_cooldowns(cooldowns: dict):
    """Save cooldown state"""
    COOLDOWN_FILE.parent.mkdir(exist_ok=True)
    with open(COOLDOWN_FILE, 'w') as f:
        json.dump(cooldowns, f, indent=4)


def check_trade_cooldown(
    coin: str,
    cooldown_minutes: int = 60
) -> tuple[bool, str]:
    """
    Check if coin is in cooldown period.
    
    Args:
        coin: Coin pair (e.g., "BTC/USDT")
        cooldown_minutes: Minutes to wait between trades (default 60)
        
    Returns:
        tuple: (can_trade, reason)
    """
    cooldowns = load_cooldowns()
    
    if coin not in cooldowns:
        return True, "No cooldown"
    
    last_trade_time = datetime.fromisoformat(cooldowns[coin])
    time_since_trade = datetime.now() - last_trade_time
    cooldown_period = timedelta(minutes=cooldown_minutes)
    
    if time_since_trade < cooldown_period:
        remaining = cooldown_period - time_since_trade
        remaining_mins = int(remaining.total_seconds() / 60)
        return False, f"Cooldown: {remaining_mins} minutes remaining"
    
    return True, "Cooldown expired"


def record_trade(coin: str):
    """Record that a trade was executed for cooldown tracking"""
    cooldowns = load_cooldowns()
    cooldowns[coin] = datetime.now().isoformat()
    save_cooldowns(cooldowns)


def check_global_cooldown(
    trades_today: int,
    max_trades_per_day: int = 20
) -> tuple[bool, str]:
    """
    Check if we've hit daily trade limit.
    
    Args:
        trades_today: Number of trades executed today
        max_trades_per_day: Maximum trades allowed per day
        
    Returns:
        tuple: (can_trade, reason)
    """
    if trades_today >= max_trades_per_day:
        return False, f"Daily trade limit: {trades_today}/{max_trades_per_day}"
    
    return True, f"Trade count OK: {trades_today}/{max_trades_per_day}"


# CUSTOMIZE HERE:
# - Line 33: cooldown_minutes = 60 - Time between trades on same pair (30, 60, 120?)
# - Line 73: max_trades_per_day = 20 - Max total trades per day (10, 20, 50?)
# - Add hourly limits if needed