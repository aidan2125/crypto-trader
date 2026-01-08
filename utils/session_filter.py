"""
Session Filter - Time-based trading rules
"""
from datetime import datetime, time as dt_time

def check_trading_hours(
    allowed_hours: tuple = (0, 23)
) -> tuple[bool, str]:
    """
    Check if current time is within allowed trading hours.
    
    Args:
        allowed_hours: Tuple of (start_hour, end_hour) in 24h format
        
    Returns:
        tuple: (can_trade, reason)
    """
    current_hour = datetime.now().hour
    start_hour, end_hour = allowed_hours
    
    if start_hour <= current_hour <= end_hour:
        return True, f"Within trading hours ({start_hour}:00-{end_hour}:00)"
    
    return False, f"Outside trading hours (current: {current_hour}:00)"


def check_weekend_trading(
    allow_weekends: bool = True
) -> tuple[bool, str]:
    """
    Check if trading is allowed on weekends.
    
    Args:
        allow_weekends: Whether to trade on weekends
        
    Returns:
        tuple: (can_trade, reason)
    """
    day = datetime.now().weekday()  # 0=Monday, 6=Sunday
    
    if not allow_weekends and day >= 5:  # Saturday or Sunday
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return False, f"Weekend trading disabled (today is {day_names[day]})"
    
    return True, "Day check passed"


def check_market_session(
    session: str = "24/7"
) -> tuple[bool, str]:
    """
    Check if within specific market session.
    
    Sessions:
    - "24/7": Always trade (crypto default)
    - "asia": 00:00-08:00 UTC
    - "europe": 08:00-16:00 UTC
    - "us": 16:00-00:00 UTC
    
    Args:
        session: Which session to trade
        
    Returns:
        tuple: (can_trade, reason)
    """
    if session == "24/7":
        return True, "24/7 trading enabled"
    
    current_hour = datetime.utcnow().hour
    
    sessions = {
        "asia": (0, 8),
        "europe": (8, 16),
        "us": (16, 24)
    }
    
    if session not in sessions:
        return True, f"Unknown session: {session}"
    
    start, end = sessions[session]
    
    if start <= current_hour < end:
        return True, f"Within {session} session"
    
    return False, f"Outside {session} session (current: {current_hour}:00 UTC)"


def check_high_volatility_hours(
    avoid_news_hours: bool = True
) -> tuple[bool, str]:
    """
    Avoid trading during known high-volatility periods.
    
    Common high-vol times (UTC):
    - 13:30-14:30: US market open
    - 14:00-14:05: Fed announcements
    - First/last hour of major sessions
    
    Args:
        avoid_news_hours: Whether to avoid high-vol periods
        
    Returns:
        tuple: (can_trade, reason)
    """
    if not avoid_news_hours:
        return True, "Volatility filter disabled"
    
    current_hour = datetime.utcnow().hour
    current_minute = datetime.utcnow().minute
    
    # Avoid US market open
    if current_hour == 13 and 30 <= current_minute <= 59:
        return False, "US market opening (high volatility)"
    
    if current_hour == 14 and current_minute <= 30:
        return False, "US market opening (high volatility)"
    
    return True, "No high-vol period detected"


# CUSTOMIZE HERE:
# - Line 11: allowed_hours = (0, 23) - Set your trading hours (e.g., (9, 17) for 9am-5pm)
# - Line 28: allow_weekends = True - Change to False to skip weekends
# - Line 57-61: sessions - Add/modify trading sessions for your timezone
# - Lines 95-101: High-vol hours - Add your specific times to avoid (news, market open/close)