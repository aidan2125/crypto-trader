import json
from datetime import datetime

SUMMARY_FILE = "data/paper_summary.json"
POSITIONS_FILE = "data/positions.json"
BALANCE_FILE = "data/paper_balance.json"

def load_json_safe(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def main():
    timestamp = datetime.now()
    print(f"=== CRYPTO BOT DIAGNOSTICS - {timestamp} ===\n")

    balances = load_json_safe(BALANCE_FILE)
    positions = load_json_safe(POSITIONS_FILE)
    summary = load_json_safe(SUMMARY_FILE)

    # --- Cash Balances ---
    print("Cash Balances:")
    for currency, data in balances.items():
        cash = data.get("cash", 0)
        print(f"  {currency}: {cash:.2f}")
    print()

    # --- Open Positions ---
    print("Open Positions:")
    if positions:
        for coin, pos in positions.items():
            entry = pos.get("entry_price", 0)
            size = pos.get("trade_size", 0)
            currency = pos.get("currency", "")
            print(f"  {coin}: Entry {entry} {currency}, Size {size}")
    else:
        print("  None")
    print()

    # --- Trade Summary ---
    print("Trade Summary:")
    for coin, data in summary.items():
        if not isinstance(data, dict):
            continue  # Skip non-dict entries (like top-level total_pnl)
        trades = data.get("trades", 0)
        pnl = data.get("total_pnl", 0.0)
        print(f"  {coin}: Trades={trades}, Realized PnL={pnl:.2f}")

    total_pnl = summary.get("total_pnl", 0.0)
    print(f"\nTOTAL PnL: {total_pnl:.2f}")

if __name__ == "__main__":
    main()
