# test_force_trade.py
from execution.enhanced_paper_trader import execute_paper_trade
from database.trade_logger import TradeLogger

logger = TradeLogger()

result = execute_paper_trade(
    coin="BTC/USDT",
    signal=1,
    price=65000.0,
    currency="USD",
    atr=800.0,
    trade_size=50.0,   # force a small, affordable position size
)

print("Trade result:", result)

if isinstance(result, dict):
    logger.log_trade(
        symbol="BTC/USDT", action="ENTRY", direction="LONG", price=65000.0,
        quantity=result.get("quantity", 0), asset_type="crypto",
        position_size=result.get("size_usd"), stop_loss=result.get("stop_loss"),
        take_profit=result.get("take_profit"), atr=800.0, strategy_mode="strict",
    )
    print("Logged. Check trades.db and data/paper_positions.json")
else:
    print(f"Trade rejected: {result}")