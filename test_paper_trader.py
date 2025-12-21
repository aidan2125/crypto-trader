"""
Paper Trading System - Complete Test Suite
Run this file to verify all paper trading functionality
"""

from execution.paper_trader import execute_paper_trade, summarize_paper_trades, reset_paper_trading

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def run_all_tests():
    """Run comprehensive tests of the paper trading system"""
    
    # TEST 1: Reset and Initial State
    print_section("TEST 1: Reset Paper Trading Account")
    reset_paper_trading()
    summarize_paper_trades()
    
    # TEST 2: Basic BUY
    print_section("TEST 2: Execute BUY Trade")
    result = execute_paper_trade("BTC/USDT", signal=1, price=30000, currency="USD", trade_size=100)
    print(f"Result: {result}")
    print("Expected: BTC/USDT PAPER BUY @ 30000.00 (USD)")
    
    # TEST 3: Duplicate BUY (Should Fail)
    print_section("TEST 3: Try to BUY Again (Already in Position)")
    result = execute_paper_trade("BTC/USDT", signal=1, price=30500, currency="USD", trade_size=100)
    print(f"Result: {result}")
    print("Expected: BTC/USDT ALREADY IN POSITION (entry: 30000.00)")
    
    # TEST 4: HOLD Signal
    print_section("TEST 4: HOLD Signal with Open Position")
    result = execute_paper_trade("BTC/USDT", signal=0, price=31000, currency="USD")
    print(f"Result: {result}")
    print("Expected: BTC/USDT HOLDING POSITION (entry: 30000.00, unrealized PnL: 3.33)")
    
    # TEST 5: SELL at Profit
    print_section("TEST 5: SELL Trade at Profit")
    result = execute_paper_trade("BTC/USDT", signal=-1, price=31000, currency="USD")
    print(f"Result: {result}")
    print("Expected: BTC/USDT PAPER SELL @ 31000.00 | PnL: 3.33 USD")
    
    # TEST 6: Duplicate SELL (Should Fail)
    print_section("TEST 6: Try to SELL Again (No Position)")
    result = execute_paper_trade("BTC/USDT", signal=-1, price=31500, currency="USD")
    print(f"Result: {result}")
    print("Expected: BTC/USDT NO POSITION TO SELL")
    
    # TEST 7: Multiple Coins
    print_section("TEST 7: Buy Multiple Coins")
    result1 = execute_paper_trade("ETH/USDT", signal=1, price=2000, currency="USD", trade_size=100)
    print(f"ETH Result: {result1}")
    result2 = execute_paper_trade("SOL/USDT", signal=1, price=100, currency="USD", trade_size=100)
    print(f"SOL Result: {result2}")
    print("Expected: Both should buy successfully")
    
    # TEST 8: Check Summary with Open Positions
    print_section("TEST 8: Summary with Open Positions")
    summarize_paper_trades()
    print("Expected: 2 open positions (ETH, SOL), 1 completed trade (BTC), Total PnL: +$3.33")
    
    # TEST 9: SELL at Loss
    print_section("TEST 9: SELL Trade at Loss")
    result = execute_paper_trade("ETH/USDT", signal=-1, price=1900, currency="USD")
    print(f"Result: {result}")
    print("Expected: ETH/USDT PAPER SELL @ 1900.00 | PnL: -5.00 USD")
    
    # TEST 10: SELL at Profit
    print_section("TEST 10: SELL Trade at Bigger Profit")
    result = execute_paper_trade("SOL/USDT", signal=-1, price=150, currency="USD")
    print(f"Result: {result}")
    print("Expected: SOL/USDT PAPER SELL @ 150.00 | PnL: 50.00 USD")
    
    # TEST 11: Final Summary
    print_section("TEST 11: Final Summary (All Positions Closed)")
    summarize_paper_trades()
    print("Expected: No open positions, 3 completed trades, Total PnL: +$48.33, Cash: $1,048.33")
    
    # TEST 12: Insufficient Balance
    print_section("TEST 12: Try to BUY with Insufficient Balance")
    result = execute_paper_trade("DOGE/USDT", signal=1, price=0.10, currency="USD", trade_size=2000)
    print(f"Result: {result}")
    print("Expected: DOGE/USDT NOT ENOUGH USD BALANCE (have: 1048.33, need: 2000)")
    
    # TEST 13: HOLD with No Position
    print_section("TEST 13: HOLD Signal with No Position")
    result = execute_paper_trade("XRP/USDT", signal=0, price=0.50, currency="USD")
    print(f"Result: {result}")
    print("Expected: XRP/USDT HOLD - NO POSITION")
    
    # TEST 14: Buy and Sell Same Coin Again
    print_section("TEST 14: Multiple Trades on Same Coin")
    result1 = execute_paper_trade("BTC/USDT", signal=1, price=32000, currency="USD", trade_size=100)
    print(f"BUY Result: {result1}")
    result2 = execute_paper_trade("BTC/USDT", signal=-1, price=33000, currency="USD")
    print(f"SELL Result: {result2}")
    print("Expected: BUY at 32000, SELL at 33000, PnL: ~3.13 USD")
    
    # TEST 15: Final Complete Summary
    print_section("TEST 15: Complete Final Summary")
    summarize_paper_trades()
    print("Expected: No open positions, BTC has 2 trades total, Total PnL: +$51.46, Cash: $1,051.46")
    
    # Summary of All Tests
    print_section("TEST SUITE COMPLETE")
    print("""
All tests completed! Your paper trading system should handle:
✓ Basic BUY/SELL operations
✓ Duplicate trade prevention
✓ HOLD signals with position tracking
✓ Profit and loss calculations
✓ Multiple concurrent positions
✓ Insufficient balance detection
✓ Position state validation
✓ Multiple trades on same coin
✓ Accurate balance and PnL tracking
    """)

if __name__ == "__main__":
    run_all_tests()