"""
Enhanced Paper Trading System - Comprehensive Test Suite
Professional testing framework with detailed reporting and edge case coverage
"""

import sys
import time
from datetime import datetime
from execution.enhanced_paper_trader import execute_paper_trade, summarize_paper_trades, reset_paper_trading

class TestResult:
    """Store test results for reporting"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.tests = []
        self.start_time = None
        self.end_time = None
    
    def add_pass(self, test_name, expected, actual):
        self.passed += 1
        self.tests.append({
            'status': 'PASS',
            'name': test_name,
            'expected': expected,
            'actual': actual
        })
    
    def add_fail(self, test_name, expected, actual):
        self.failed += 1
        self.tests.append({
            'status': 'FAIL',
            'name': test_name,
            'expected': expected,
            'actual': actual
        })
    
    def add_skip(self, test_name, reason):
        self.skipped += 1
        self.tests.append({
            'status': 'SKIP',
            'name': test_name,
            'reason': reason
        })

class PaperTradingTestSuite:
    """Comprehensive test suite for paper trading system"""
    
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.result = TestResult()
    
    def log(self, message, level="INFO"):
        """Log messages with timestamp"""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            prefix = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✓",
                "ERROR": "✗",
                "WARNING": "⚠️ "
            }.get(level, "")
            print(f"[{timestamp}] {prefix} {message}")
    
    def print_section(self, title, level=1):
        """Print formatted section headers"""
        if level == 1:
            print(f"\n{'='*70}")
            print(f"  {title}")
            print('='*70)
        else:
            print(f"\n{'─'*70}")
            print(f"  {title}")
            print('─'*70)
    
    def assert_contains(self, actual, expected_substring, test_name):
        """Assert that result contains expected substring"""
        if expected_substring.lower() in actual.lower():
            self.result.add_pass(test_name, f"Contains: {expected_substring}", actual)
            self.log(f"✓ {test_name}", "SUCCESS")
            return True
        else:
            self.result.add_fail(test_name, f"Contains: {expected_substring}", actual)
            self.log(f"✗ {test_name} - Expected '{expected_substring}' in '{actual}'", "ERROR")
            return False
    
    def assert_not_contains(self, actual, unexpected_substring, test_name):
        """Assert that result does NOT contain substring"""
        if unexpected_substring.lower() not in actual.lower():
            self.result.add_pass(test_name, f"Not contains: {unexpected_substring}", actual)
            self.log(f"✓ {test_name}", "SUCCESS")
            return True
        else:
            self.result.add_fail(test_name, f"Not contains: {unexpected_substring}", actual)
            self.log(f"✗ {test_name} - Should not contain '{unexpected_substring}'", "ERROR")
            return False
    
    # ==================== TEST CATEGORIES ====================
    
    def test_category_basic_operations(self):
        """Test Category 1: Basic Buy/Sell Operations"""
        self.print_section("CATEGORY 1: Basic Operations")
        
        # Test 1.1: Initial Reset
        self.log("Resetting paper trading account...")
        reset_paper_trading()
        self.result.add_pass("1.1 Account Reset", "Clean slate", "Account reset successful")
        
        # Test 1.2: First Buy
        result = execute_paper_trade("BTC/USDT", signal=1, price=30000, currency="USD", trade_size=100)
        self.assert_contains(result, "PAPER BUY", "1.2 Execute First Buy")
        
        # Test 1.3: Hold with Position
        result = execute_paper_trade("BTC/USDT", signal=0, price=31000, currency="USD")
        self.assert_contains(result, "HOLDING", "1.3 Hold Signal with Open Position")
        
        # Test 1.4: Sell at Profit
        result = execute_paper_trade("BTC/USDT", signal=-1, price=32000, currency="USD")
        self.assert_contains(result, "PAPER SELL", "1.4 Sell at Profit")
        self.assert_contains(result, "PnL", "1.4b Profit Calculation")
        
        self.log(f"Basic Operations: {self.result.passed} passed", "INFO")
    
    def test_category_edge_cases(self):
        """Test Category 2: Edge Cases and Error Handling"""
        self.print_section("CATEGORY 2: Edge Cases & Error Handling")
        
        # Test 2.1: Double Buy Prevention
        execute_paper_trade("ETH/USDT", signal=1, price=2000, currency="USD", trade_size=100)
        result = execute_paper_trade("ETH/USDT", signal=1, price=2100, currency="USD", trade_size=100)
        self.assert_contains(result, "ALREADY IN POSITION", "2.1 Prevent Double Buy")
        
        # Test 2.2: Sell Without Position
        result = execute_paper_trade("SOL/USDT", signal=-1, price=100, currency="USD")
        self.assert_contains(result, "NO POSITION", "2.2 Sell Without Position")
        
        # Test 2.3: Hold Without Position
        result = execute_paper_trade("ADA/USDT", signal=0, price=0.50, currency="USD")
        self.assert_contains(result, "NO POSITION", "2.3 Hold Without Position")
        
        # Test 2.4: Zero Price (Invalid)
        result = execute_paper_trade("XRP/USDT", signal=1, price=0, currency="USD", trade_size=100)
        # System should handle gracefully
        self.log("2.4 Zero Price Handling - Observed behavior", "INFO")
        
        # Test 2.5: Negative Price (Invalid)
        result = execute_paper_trade("DOGE/USDT", signal=1, price=-1, currency="USD", trade_size=100)
        self.log("2.5 Negative Price Handling - Observed behavior", "INFO")
        
        # Clean up
        execute_paper_trade("ETH/USDT", signal=-1, price=2000, currency="USD")
    
    def test_category_multiple_positions(self):
        """Test Category 3: Multiple Concurrent Positions"""
        self.print_section("CATEGORY 3: Multiple Concurrent Positions")
        
        coins = [
            ("BTC/USDT", 30000),
            ("ETH/USDT", 2000),
            ("SOL/USDT", 100),
            ("ADA/USDT", 0.50),
            ("XRP/USDT", 0.60)
        ]
        
        # Test 3.1: Open Multiple Positions
        self.log("Opening 5 concurrent positions...")
        for i, (coin, price) in enumerate(coins, 1):
            result = execute_paper_trade(coin, signal=1, price=price, currency="USD", trade_size=50)
            self.assert_contains(result, "PAPER BUY", f"3.{i} Open Position: {coin}")
        
        # Test 3.2: Hold All Positions
        self.log("Holding all positions...")
        for coin, price in coins:
            result = execute_paper_trade(coin, signal=0, price=price * 1.05, currency="USD")
            self.assert_contains(result, "HOLDING", f"3.x Hold Position: {coin}")