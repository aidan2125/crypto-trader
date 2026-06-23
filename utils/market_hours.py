"""
utils/market_hours.py
Single utility: is_market_open()
Returns True if the US stock market (NASDAQ/NYSE) is currently open.
Used by main_enhanced.py to gate the stock trading loop.
"""

from datetime import datetime, time, timezone
import zoneinfo

# US Eastern timezone — handles EST/EDT automatically
ET = zoneinfo.ZoneInfo("America/New_York")

# Regular session: 9:30 AM – 4:00 PM ET, Monday–Friday
MARKET_OPEN  = time(9, 30)
MARKET_CLOSE = time(16, 0)

# US Federal holidays where markets are closed (YYYY-MM-DD strings).
# Update this list each year or hook into a library like 'trading_calendars'
# if you want full automation. This covers the major ones.
MARKET_HOLIDAYS_2025 = {
    "2025-01-01",  # New Year's Day
    "2025-01-20",  # Martin Luther King Jr. Day
    "2025-02-17",  # Presidents' Day
    "2025-04-18",  # Good Friday
    "2025-05-26",  # Memorial Day
    "2025-06-19",  # Juneteenth
    "2025-07-04",  # Independence Day
    "2025-09-01",  # Labor Day
    "2025-11-27",  # Thanksgiving Day
    "2025-12-25",  # Christmas Day
}

MARKET_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving Day
    "2026-12-25",  # Christmas Day
}

ALL_HOLIDAYS = MARKET_HOLIDAYS_2025 | MARKET_HOLIDAYS_2026


def is_market_open(now: datetime | None = None) -> bool:
    """
    Returns True if the US stock market is currently open.

    Args:
        now: datetime to check (defaults to current UTC time).
             Pass a custom datetime in tests to mock the clock.

    Returns:
        bool — True if market is open, False otherwise.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Convert to Eastern time
    now_et = now.astimezone(ET)

    # Weekend check
    if now_et.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    # Holiday check
    date_str = now_et.strftime("%Y-%m-%d")
    if date_str in ALL_HOLIDAYS:
        return False

    # Session hours check
    current_time = now_et.time()
    return MARKET_OPEN <= current_time < MARKET_CLOSE


def time_until_open(now: datetime | None = None) -> int:
    """
    Returns seconds until next market open.
    Useful for sleeping the stock loop until the market opens.
    Returns 0 if market is currently open.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if is_market_open(now):
        return 0

    now_et = now.astimezone(ET)
    current_time = now_et.time()

    # If before open today (and not weekend/holiday), calculate seconds to open
    if now_et.weekday() < 5 and now_et.strftime("%Y-%m-%d") not in ALL_HOLIDAYS:
        if current_time < MARKET_OPEN:
            open_today = now_et.replace(
                hour=MARKET_OPEN.hour,
                minute=MARKET_OPEN.minute,
                second=0,
                microsecond=0
            )
            return max(0, int((open_today - now_et).total_seconds()))

    # Otherwise, find the next weekday open
    from datetime import timedelta
    candidate = now_et.replace(
        hour=MARKET_OPEN.hour,
        minute=MARKET_OPEN.minute,
        second=0,
        microsecond=0
    ) + timedelta(days=1)

    # Skip weekends and holidays
    while candidate.weekday() >= 5 or candidate.strftime("%Y-%m-%d") in ALL_HOLIDAYS:
        candidate += timedelta(days=1)

    return max(0, int((candidate - now_et).total_seconds()))


if __name__ == "__main__":
    # Quick sanity check — run directly to test
    open_status = is_market_open()
    secs = time_until_open()
    print(f"Market open: {open_status}")
    if not open_status:
        hours = secs // 3600
        mins  = (secs % 3600) // 60
        print(f"Opens in:   {hours}h {mins}m")