from data.multi_coin_list import COIN_CURRENCY

# Wallet coins (Binance-style symbols; signals come from the same data as the rest of the bot).
_WALLET = [
    "XRP/USDT", "LINK/USDT", "TRX/USDT", "SOL/USDT", "LTC/USDT", "XLM/USDT",
    "PEPE/USDT", "DOGE/USDT", "AVAX/USDT", "POL/USDT", "ETHW/USDT",
    "ADA/USDT", "DOT/USDT",
]

# Coins NOT already in COIN_CURRENCY. Those are mirrored to Alpaca from
# run_for_coin; these get their own signal loop that trades on Alpaca only.
ALPACA_WALLET_COINS = [c for c in _WALLET if c not in COIN_CURRENCY]
