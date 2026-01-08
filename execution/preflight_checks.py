"""
Preflight Checks - Final verification before execution
"""
from typing import Optional

def check_balance_sufficient(
    required_amount: float,
    available_balance: float,
    safety_buffer: float = 0.05
) -> tuple[bool, str]:
    """
    Check if balance is sufficient with safety buffer.
    
    Args:
        required_amount: Amount needed for trade
        available_balance: Current balance
        safety_buffer: Keep 5% buffer (default)
        
    Returns:
        tuple: (is_sufficient, reason)
    """
    required_with_buffer = required_amount * (1 + safety_buffer)
    
    if available_balance < required_with_buffer:
        return False, f"Insufficient: need ${required_with_buffer:.2f}, have ${available_balance:.2f}"
    
    return True, f"Balance OK: ${available_balance:.2f} available"


def check_position_size_limits(
    position_size: float,
    min_size: float = 10.0,
    max_size: float = 10000.0
) -> tuple[bool, str]:
    """
    Check if position size is within limits.
    
    Args:
        position_size: Calculated position size
        min_size: Minimum trade size (default $10)
        max_size: Maximum trade size (default $10,000)
        
    Returns:
        tuple: (is_valid, reason)
    """
    if position_size < min_size:
        return False, f"Position too small: ${position_size:.2f} < ${min_size:.2f}"
    
    if position_size > max_size:
        return False, f"Position too large: ${position_size:.2f} > ${max_size:.2f}"
    
    return True, f"Position size OK: ${position_size:.2f}"


def check_price_sanity(
    current_price: float,
    recent_avg_price: Optional[float] = None,
    max_deviation: float = 0.10
) -> tuple[bool, str]:
    """
    Check if price is within reasonable range.
    
    Args:
        current_price: Current market price
        recent_avg_price: Recent average price
        max_deviation: Max allowed deviation (default 10%)
        
    Returns:
        tuple: (is_sane, reason)
    """
    if recent_avg_price is None:
        return True, "No reference price to compare"
    
    if current_price <= 0:
        return False, "Invalid price: <= 0"
    
    deviation = abs(current_price - recent_avg_price) / recent_avg_price
    
    if deviation > max_deviation:
        return False, f"Price deviation too high: {deviation:.1%} > {max_deviation:.1%}"
    
    return True, f"Price OK: {deviation:.1%} deviation"


def check_atr_validity(
    atr: Optional[float],
    price: float,
    min_atr_ratio: float = 0.001,
    max_atr_ratio: float = 0.50
) -> tuple[bool, str]:
    """
    Check if ATR is valid and reasonable.
    
    Args:
        atr: ATR value
        price: Current price
        min_atr_ratio: Min ATR/price ratio (default 0.1%)
        max_atr_ratio: Max ATR/price ratio (default 50%)
        
    Returns:
        tuple: (is_valid, reason)
    """
    if atr is None or atr <= 0:
        return False, "ATR missing or invalid"
    
    atr_ratio = atr / price
    
    if atr_ratio < min_atr_ratio:
        return False, f"ATR too low: {atr_ratio:.2%} of price"
    
    if atr_ratio > max_atr_ratio:
        return False, f"ATR too high: {atr_ratio:.2%} of price"
    
    return True, f"ATR OK: {atr_ratio:.2%} of price"


def run_all_preflight_checks(
    coin: str,
    price: float,
    atr: float,
    position_size: float,
    balance: float
) -> tuple[bool, list]:
    """
    Run all preflight checks.
    
    Returns:
        tuple: (all_passed, [list of messages])
    """
    checks = []
    all_passed = True
    
    # Balance check
    passed, msg = check_balance_sufficient(position_size, balance)
    checks.append(("Balance", passed, msg))
    all_passed = all_passed and passed
    
    # Position size check
    passed, msg = check_position_size_limits(position_size)
    checks.append(("Position Size", passed, msg))
    all_passed = all_passed and passed
    
    # Price sanity check
    passed, msg = check_price_sanity(price)
    checks.append(("Price", passed, msg))
    all_passed = all_passed and passed
    
    # ATR validity check
    passed, msg = check_atr_validity(atr, price)
    checks.append(("ATR", passed, msg))
    all_passed = all_passed and passed
    
    return all_passed, checks


# CUSTOMIZE HERE:
# - Line 14: safety_buffer = 0.05 - Keep 5% cash buffer (increase for safety)
# - Line 33-34: min_size/max_size - Your exchange's limits
# - Line 60: max_deviation = 0.10 - Max 10% price jump (tighten to detect errors)
# - Line 94-95: min_atr_ratio/max_atr_ratio - ATR sanity bounds