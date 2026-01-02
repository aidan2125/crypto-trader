#!/bin/bash
echo "======================================"
echo "   CRYPTO BOT STATUS"
echo "======================================"
echo ""

# Timer status
echo "⏰ Timer Status:"
systemctl --user is-active crypto-trader.timer

# Next run
echo ""
echo "📅 Next Run:"
systemctl --user list-timers crypto-trader.timer | grep crypto-trader

# Last 5 log lines
echo ""
echo "📝 Recent Logs:"
journalctl --user -u crypto-trader.service -n 5 --no-pager

# Trading summary
echo ""
echo "💰 Trading Summary:"
cd /home/aidan/crypto-trader
source venv/bin/activate
python3 -c "from execution.enhanced_paper_trader import summarize_paper_trades; summarize_paper_trades()"
