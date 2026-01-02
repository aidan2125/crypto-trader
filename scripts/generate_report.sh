#!/bin/bash
cd /home/aidan/crypto-trader
source venv/bin/activate

# Generate HTML report
python3 - << 'PYTHON'
from execution.enhanced_paper_trader import load_json, SUMMARY_FILE, POSITIONS_FILE, BALANCE_FILE
from datetime import datetime

summary = load_json(SUMMARY_FILE, {})
positions = load_json(POSITIONS_FILE, {})
balances = load_json(BALANCE_FILE, {})

html = f"""
<html>
<head>
    <title>Crypto Bot Status</title>
    <meta http-equiv="refresh" content="60">
    <style>
        body {{ font-family: Arial; padding: 20px; background: #1a1a1a; color: #fff; }}
        .card {{ background: #2d2d2d; padding: 20px; margin: 10px 0; border-radius: 8px; }}
        .positive {{ color: #4ade80; }}
        .negative {{ color: #f87171; }}
    </style>
</head>
<body>
    <h1>📊 Crypto Trading Bot</h1>
    <p>Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="card">
        <h2>💰 Balance</h2>
        <p>USD: ${balances.get('USD', {}).get('cash', 0):.2f}</p>
        <p>Total PnL: <span class="{'positive' if summary.get('total_pnl', 0) >= 0 else 'negative'}">${summary.get('total_pnl', 0):.2f}</span></p>
        <p>Win Rate: {summary.get('win_rate', 0):.1f}%</p>
    </div>
    
    <div class="card">
        <h2>📈 Open Positions ({len(positions)})</h2>
        {'<p>None</p>' if not positions else '<br>'.join([f"{coin}: Entry ${pos['entry_price']:.2f}" for coin, pos in positions.items()])}
    </div>
</body>
</html>
"""

with open('/home/aidan/crypto-trader/reports/status.html', 'w') as f:
    f.write(html)
PYTHON
