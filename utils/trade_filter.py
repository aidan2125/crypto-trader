"""
Trade Filters - Check if market conditions are tradable
"""

def check_volatility_filter(
    current_atr: float,
    avg_atr: float,
    min_ratio: float = 0.5,
    max_ratio: float = 3.0
) -> tuple[bool, str]:
    """
    Filter out trades when volatility is extreme.
    
    Args:
        current_atr: Current ATR value
        avg_atr: Average ATR over period
        min_ratio: Minimum ATR ratio (default 0.5 = half average)
        max_ratio: Maximum ATR ratio (default 3.0 = triple average)
        
    Returns:
        tuple: (can_trade, reason)
    """
    if avg_atr == 0:
        return False, "No volatility data"
    
    ratio = current_atr / avg_atr
    
    if ratio < min_ratio:
        return False, f"Volatility too low: {ratio:.2f}x average (min {min_ratio}x)"
    
    if ratio > max_ratio:
        return False, f"Volatility too high: {ratio:.2f}x average (max {max_ratio}x)"
    
    return True, f"Volatility OK: {ratio:.2f}x average"


def check_volume_filter(
    current_volume: float,
    avg_volume: float,
    min_ratio: float = 0.5
) -> tuple[bool, str]:
    """
    Filter out trades when volume is too low.
    
    Args:
        current_volume: Current volume
        avg_volume: Average volume
        min_ratio: Minimum volume ratio (default 0.5)
        
    Returns:
        tuple: (can_trade, reason)
    """
    if avg_volume == 0:
        return True, "No volume filter"
    
    ratio = current_volume / avg_volume
    
    if ratio < min_ratio:
        return False, f"Volume too low: {ratio:.1%} of average"
    
    return True, f"Volume OK: {ratio:.1%} of average"


def check_spread_filter(
    bid: float,
    ask: float,
    max_spread_pct: float = 0.005
) -> tuple[bool, str]:
    """
    Filter out trades when spread is too wide.
    
    Args:
        bid: Bid price
        ask: Ask price
        max_spread_pct: Max allowed spread (default 0.5%)
        
    Returns:
        tuple: (can_trade, reason)
    """
    if bid == 0:
        return True, "No spread data"
    
    spread = (ask - bid) / bid
    
    if spread > max_spread_pct:
        return False, f"Spread too wide: {spread:.2%} > {max_spread_pct:.2%}"
    
    return True, f"Spread OK: {spread:.2%}"


# CUSTOMIZE HERE:
# - Line 14-15: Volatility limits (0.5x to 3.0x) - adjust based on your tolerance
# - Line 45: min_ratio = 0.5 - Minimum volume threshold
# - Line 73: max_spread_pct = 0.005 - Max 0.5% spread (tighten for low slippage)