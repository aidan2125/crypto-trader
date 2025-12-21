"""
Risk Management Module - Standalone and Importable
All 13 issues fixed
"""

import json
import os

# File paths
BALANCE_FILE = "data/paper_balance.json"
POSITIONS_FILE = "data/positions.json"
RISK_CONFIG_FILE = "data/risk_config.json"

# Default risk configuration
DEFAULT_RISK_CONFIG = {
    "max_positions": 5,
    "max_portfolio_risk": 0.20,
    "position_size_pct": 0.10,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.05,
    "trailing_stop_pct": 0.03,
    "trading_fee_pct": 0.001,
    "slippage_pct": 0.0005,
    "min_trade_size": 10,
}

# Ensure directories exist
os.makedirs("data", exist_ok=True)

# ------------------- Utility Functions -------------------

def load_json(file_path, default=None):
    """Load JSON file with error handling."""
    if not os.path.exists(file_path):
        return default if default is not None else {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {file_path}: {e}")
        return default if default is not None else {}

def save_json(file_path, data):
    """Save data to JSON file."""
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"Error saving {file_path}: {e}")

# ------------------- Config Management -------------------

def load_risk_config():
    """Load risk configuration from file."""
    config = load_json(RISK_CONFIG_FILE, default=DEFAULT_RISK_CONFIG.copy())
    
    # Ensure all required keys exist
    for key, value in DEFAULT_RISK_CONFIG.items():
        config.setdefault(key, value)
    
    # Validate config values
    if not validate_risk_config(config):
        print("Invalid risk config detected, using defaults")
        return DEFAULT_RISK_CONFIG.copy()
    
    return config

def save_risk_config(config):
    """Save risk configuration to file."""
    if not validate_risk_config(config):
        print("Cannot save invalid risk config")
        return False
    
    save_json(RISK_CONFIG_FILE, config)
    return True

def validate_risk_config(config):
    """Validate risk configuration values."""
    try:
        # Check all required keys exist
        for key in DEFAULT_RISK_CONFIG.keys():
            if key not in config:
                print(f"Missing required key: {key}")
                return False
        
        # Validate numeric ranges
        if config["max_positions"] < 1:
            print("max_positions must be >= 1")
            return False
        
        if not (0 < config["position_size_pct"] <= 1):
            print("position_size_pct must be between 0 and 1")
            return False
        
        if not (0 < config["stop_loss_pct"] < 1):
            print("stop_loss_pct must be between 0 and 1")
            return False
        
        if not (0 < config["take_profit_pct"] < 5):
            print("take_profit_pct must be between 0 and 5 (500%)")
            return False
        
        if config["min_trade_size"] < 0:
            print("min_trade_size must be >= 0")
            return False
        
        return True
    except (TypeError, KeyError) as e:
        print(f"Config validation error: {e}")
        return False

# ------------------- Position Sizing -------------------

def calculate_position_size(currency="USD"):
    """
    Calculate position size based on available balance and risk settings.
    
    Args:
        currency: Currency to trade in
        
    Returns:
        tuple: (position_size, reason)
    """
    try:
        config = load_risk_config()
        balances = load_json(BALANCE_FILE, default={})
        
        if currency not in balances or not isinstance(balances[currency], dict):
            return 0, f"NO_{currency}_ACCOUNT"
        
        cash = balances[currency].get("cash", 0)
        
        if cash <= 0:
            return 0, "NO_CASH_AVAILABLE"
        
        # Calculate position size as percentage of balance
        position_size = cash * config["position_size_pct"]
        
        # Enforce minimum trade size
        if position_size < config["min_trade_size"]:
            return 0, f"BELOW_MIN (need ${config['min_trade_size']:.2f}, have ${position_size:.2f})"
        
        return position_size, "OK"
        
    except Exception as e:
        print(f"Error calculating position size: {e}")
        return 0, f"ERROR: {str(e)}"

# ------------------- Position Limits -------------------

def check_max_positions():
    """
    Check if we've reached maximum number of open positions.
    
    Returns:
        tuple: (can_open, current_count, max_allowed)
    """
    try:
        config = load_risk_config()
        positions = load_json(POSITIONS_FILE, default={})
        current_count = len(positions)
        can_open = current_count < config["max_positions"]
        
        return can_open, current_count, config["max_positions"]
    except Exception as e:
        print(f"Error checking max positions: {e}")
        return False, 0, 0

# ------------------- Stop Loss / Take Profit -------------------

def calculate_stop_loss(entry_price):
    """Calculate stop loss price based on entry."""
    try:
        config = load_risk_config()
        return entry_price * (1 - config["stop_loss_pct"])
    except Exception as e:
        print(f"Error calculating stop loss: {e}")
        return entry_price * 0.98  # Default 2%

def calculate_take_profit(entry_price):
    """Calculate take profit price based on entry."""
    try:
        config = load_risk_config()
        return entry_price * (1 + config["take_profit_pct"])
    except Exception as e:
        print(f"Error calculating take profit: {e}")
        return entry_price * 1.05  # Default 5%

# ------------------- Exit Conditions -------------------

def check_exit_conditions(coin, current_price):
    """
    Check if position should be exited based on stop-loss or take-profit.
    
    Args:
        coin: Trading pair symbol
        current_price: Current market price
        
    Returns:
        tuple: (should_exit, reason, pnl_pct)
    """
    try:
        positions = load_json(POSITIONS_FILE, default={})
        position = positions.get(coin)
        
        if not position or not isinstance(position, dict):
            return False, None, 0
        
        entry_price = position.get("entry_price")
        if not entry_price:
            return False, "NO_ENTRY_PRICE", 0
        
        # Calculate current PnL percentage
        pnl_pct = (current_price - entry_price) / entry_price
        
        # Check stop loss
        stop_loss_price = calculate_stop_loss(entry_price)
        if current_price <= stop_loss_price:
            return True, "STOP_LOSS", pnl_pct
        
        # Check take profit
        take_profit_price = calculate_take_profit(entry_price)
        if current_price >= take_profit_price:
            return True, "TAKE_PROFIT", pnl_pct
        
        # Check trailing stop (if position has peaked)
        peak_price = position.get("peak_price", entry_price)
        config = load_risk_config()
        trailing_stop_price = peak_price * (1 - config["trailing_stop_pct"])
        
        if current_price <= trailing_stop_price and peak_price > entry_price:
            return True, "TRAILING_STOP", pnl_pct
        
        return False, None, pnl_pct
        
    except Exception as e:
        print(f"Error checking exit conditions for {coin}: {e}")
        return False, f"ERROR: {str(e)}", 0

def update_peak_price(coin, current_price):
    """
    Update peak price for trailing stop calculation.
    
    Args:
        coin: Trading pair symbol
        current_price: Current market price
        
    Returns:
        bool: True if peak was updated
    """
    try:
        positions = load_json(POSITIONS_FILE, default={})
        position = positions.get(coin)
        
        if not position or not isinstance(position, dict):
            return False
        
        entry_price = position.get("entry_price", 0)
        peak_price = position.get("peak_price", entry_price)
        
        if current_price > peak_price:
            position["peak_price"] = current_price
            positions[coin] = position
            save_json(POSITIONS_FILE, positions)
            return True
        
        return False
        
    except Exception as e:
        print(f"Error updating peak price for {coin}: {e}")
        return False

# ------------------- Fee Calculations -------------------

def calculate_fees_and_slippage(trade_size, price=None):
    """
    Calculate trading fees and slippage costs.
    
    Args:
        trade_size: Size of trade in currency units
        price: Current price (optional, for more accurate slippage)
        
    Returns:
        dict: Breakdown of costs
    """
    try:
        config = load_risk_config()
        
        fee = trade_size * config["trading_fee_pct"]
        slippage = trade_size * config["slippage_pct"]
        total_cost = fee + slippage
        
        result = {
            "fee": fee,
            "slippage": slippage,
            "total_cost": total_cost,
            "net_trade_size": trade_size - total_cost
        }
        
        # If price provided, calculate price impact
        if price is not None:
            result["slippage_price_impact"] = price * config["slippage_pct"]
        
        return result
        
    except Exception as e:
        print(f"Error calculating fees: {e}")
        return {
            "fee": 0,
            "slippage": 0,
            "total_cost": 0,
            "net_trade_size": trade_size
        }

# ------------------- Portfolio Metrics -------------------

def get_risk_metrics():
    """
    Get current portfolio risk metrics.
    
    Returns:
        dict: Risk metrics including exposure, position count, etc.
    """
    try:
        config = load_risk_config()
        positions = load_json(POSITIONS_FILE, default={})
        balances = load_json(BALANCE_FILE, default={})
        
        # Calculate total exposure
        total_exposure = 0
        for pos in positions.values():
            if isinstance(pos, dict):
                total_exposure += pos.get("trade_size", 0)
        
        # Calculate total cash
        total_cash = 0
        for acc in balances.values():
            if isinstance(acc, dict):
                total_cash += acc.get("cash", 0)
        
        # Calculate portfolio value
        total_value = total_cash + total_exposure
        exposure_pct = (total_exposure / total_value * 100) if total_value > 0 else 0
        
        return {
            "total_positions": len(positions),
            "max_positions": config["max_positions"],
            "total_exposure": total_exposure,
            "total_cash": total_cash,
            "total_value": total_value,
            "exposure_percentage": exposure_pct,
            "available_for_trading": total_cash * config["position_size_pct"]
        }
        
    except Exception as e:
        print(f"Error getting risk metrics: {e}")
        return {
            "total_positions": 0,
            "max_positions": 0,
            "total_exposure": 0,
            "total_cash": 0,
            "total_value": 0,
            "exposure_percentage": 0,
            "available_for_trading": 0
        }

# ------------------- Display Functions -------------------

def print_risk_summary():
    """Print a summary of current risk metrics."""
    try:
        metrics = get_risk_metrics()
        config = load_risk_config()
        
        print("\n" + "="*50)
        print("RISK MANAGEMENT SUMMARY".center(50))
        print("="*50)
        print(f"\nPositions: {metrics['total_positions']}/{metrics['max_positions']}")
        print(f"Total Portfolio Value: ${metrics['total_value']:.2f}")
        print(f"Cash Available: ${metrics['total_cash']:.2f}")
        print(f"Total Exposure: ${metrics['total_exposure']:.2f} ({metrics['exposure_percentage']:.1f}%)")
        print(f"Available for Next Trade: ${metrics['available_for_trading']:.2f}")
        print(f"\nRisk Settings:")
        print(f"  Position Size: {config['position_size_pct']*100:.1f}% of balance")
        print(f"  Stop Loss: {config['stop_loss_pct']*100:.1f}%")
        print(f"  Take Profit: {config['take_profit_pct']*100:.1f}%")
        print(f"  Trailing Stop: {config['trailing_stop_pct']*100:.1f}%")
        print(f"  Trading Fee: {config['trading_fee_pct']*100:.2f}%")
        print(f"  Min Trade Size: ${config['min_trade_size']:.2f}")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"Error printing risk summary: {e}")

# ------------------- Testing -------------------

if __name__ == "__main__":
    print("Risk Management Module - Test Suite\n")
    
    # Test 1: Config management
    print("Test 1: Load/Save Config")
    config = load_risk_config()
    print(f"Config loaded: {len(config)} keys")
    
    # Test 2: Position sizing
    print("\nTest 2: Position Sizing")
    size, reason = calculate_position_size("USD")
    print(f"Position size: ${size:.2f} ({reason})")
    
    # Test 3: Position limits
    print("\nTest 3: Position Limits")
    can_open, current, max_pos = check_max_positions()
    print(f"Can open: {can_open} (current: {current}/{max_pos})")
    
    # Test 4: Stop loss / Take profit
    print("\nTest 4: Stop Loss / Take Profit")
    entry = 30000
    stop = calculate_stop_loss(entry)
    profit = calculate_take_profit(entry)
    print(f"Entry: ${entry:.2f} | Stop: ${stop:.2f} | Target: ${profit:.2f}")
    
    # Test 5: Exit conditions
    print("\nTest 5: Exit Conditions")
    should_exit, reason, pnl = check_exit_conditions("BTC/USDT", 31000)
    print(f"Should exit: {should_exit}, Reason: {reason}, PnL: {pnl*100:.2f}%")
    
    # Test 6: Fees
    print("\nTest 6: Fee Calculation")
    fees = calculate_fees_and_slippage(100, 30000)
    print(f"Fees: ${fees['fee']:.2f} | Slippage: ${fees['slippage']:.2f} | Total: ${fees['total_cost']:.2f}")
    
    # Test 7: Portfolio metrics
    print("\nTest 7: Risk Metrics")
    print_risk_summary()
    
    print("All tests completed!")