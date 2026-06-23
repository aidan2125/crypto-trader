"""
config/stock_watchlist.py
Stock tickers to trade — equivalent of data/multi_coin_list.py COIN_CURRENCY.
Add or remove tickers freely. The bot will run enhanced_signals on each one.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Primary watchlist — high volatility NASDAQ stocks & leveraged ETFs
# These have similar ATR-signal behaviour to crypto (trending, volatile)
# ─────────────────────────────────────────────────────────────────────────────
STOCK_WATCHLIST = [
    "TQQQ",   # 3× leveraged NASDAQ ETF — amplified moves, great for ATR signals
    "NVDA",   # NVIDIA — high-beta, strong trends, huge daily ranges
    "TSLA",   # Tesla — volatile, momentum-driven, familiar to tune
    "COIN",   # Coinbase — correlates with your crypto side, same volatility profile
]

# ─────────────────────────────────────────────────────────────────────────────
# Optional expansion tickers (uncomment to add)
# ─────────────────────────────────────────────────────────────────────────────
# STOCK_WATCHLIST += [
#     "AMD",    # AMD — semiconductor, high-beta
#     "MSTR",   # MicroStrategy — basically a leveraged Bitcoin proxy as a stock
#     "SOXL",   # 3× semiconductor ETF — even more volatile than TQQQ
#     "META",   # Meta — strong trends during earnings cycles
#     "PLTR",   # Palantir — momentum favourite
# ]

# ─────────────────────────────────────────────────────────────────────────────
# Currency label for display in alerts (stocks are always USD)
# Mirrors the COIN_CURRENCY dict pattern from multi_coin_list.py
# ─────────────────────────────────────────────────────────────────────────────
STOCK_CURRENCY = {ticker: "USD" for ticker in STOCK_WATCHLIST}