from enum import IntEnum, auto
from typing import Literal

class TradeSignal(IntEnum):
    """
    Strongly typed enumeration for trading signals.
    Prevents invalid values at runtime and provides clear intent.
    """
    SELL = -1
    HOLD = 0
    BUY = 1

    def __str__(self) -> str:
        """Human-readable string representation"""
        return self.name.capitalize()  # "Buy", "Hold", "Sell"

    def __repr__(self) -> str:
        return f"<TradeSignal.{self.name}>"

# Type alias for static type checking (e.g., with mypy, pyright)
SignalType = Literal[TradeSignal.SELL, TradeSignal.HOLD, TradeSignal.BUY]

def validate_signal(signal: int | TradeSignal) -> TradeSignal:
    """
    Validate and normalize a trading signal.
    
    Args:
        signal: Raw signal value (-1, 0, 1) or TradeSignal enum
        
    Returns:
        TradeSignal: Validated and typed signal
        
    Raises:
        ValueError: If signal is invalid
    """
    try:
        # Accept both int and enum
        if isinstance(signal, TradeSignal):
            return signal
        return TradeSignal(signal)
    except ValueError:
        raise ValueError(
            f"Invalid trading signal: {signal!r}. "
            f"Must be one of: {', '.join(str(s.value) for s in TradeSignal)} "
            f"or {', '.join(repr(s) for s in TradeSignal)}"
        )