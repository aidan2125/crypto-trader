# database/insert_presets.py

# lightweight dotenv loader (avoids external dependency)
import os
from datetime import datetime
import json
import urllib.request
import urllib.error
import sys

def load_dotenv(dotenv_path: str = ".env"):
    """Load simple KEY=VALUE pairs from a .env file into os.environ (if present)."""
    if not os.path.exists(dotenv_path):
        return False
    with open(dotenv_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)
    return True

# minimal Supabase REST client (avoids external dependency)
class _InsertExecutor:
    def __init__(self, base_url, headers, table, payload):
        self.base_url = base_url
        self.headers = headers
        self.table = table
        self.payload = payload
        self.data = None
        self.status_code = None
        self.error = None

    def execute(self):
        endpoint = f"{self.base_url}/rest/v1/{self.table}"
        body = json.dumps(self.payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, method="POST")
        for k, v in self.headers.items():
            req.add_header(k, v)
        req.add_header("Content-Type", "application/json")
        # ensure the Prefer header is present on the request as well
        req.add_header("Prefer", "return=representation")
        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode("utf-8")
                self.status_code = resp.getcode()
                try:
                    self.data = json.loads(resp_body)
                except Exception:
                    self.data = resp_body
        except urllib.error.HTTPError as e:
            self.status_code = e.code
            try:
                self.error = e.read().decode("utf-8")
            except Exception:
                self.error = str(e)
        except Exception as e:
            self.error = str(e)
        return self

class _Table:
    def __init__(self, client, table):
        self.client = client
        self.table = table

    def insert(self, payload):
        return _InsertExecutor(self.client.base_url, self.client.headers, self.table, payload)

class SupabaseClient:
    def __init__(self, url, key):
        self.base_url = url
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            # ask Supabase to return the inserted rows so we get data back
            "Prefer": "return=representation"
        }

    def table(self, name: str):
        return _Table(self, name)

def create_client(url: str, key: str):
    return SupabaseClient(url, key)

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_ANON_KEY not found in .env — aborting")
    sys.exit(1)

supabase = create_client(url, key)

presets = [
    {
        "preset_name": "conservative",
        "max_positions": 3,
        "position_size_pct": 0.05,
        "min_trade_size": 10,
        "use_dynamic_sl_tp": True,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.5,
        "min_risk_reward_ratio": 1.5,
        "stop_loss_pct": 0.015,
        "take_profit_pct": 0.03,
        "trailing_stop_pct": 0.02,
        "trading_fee_pct": 0.001,
        "slippage_pct": 0.0005,
        "max_portfolio_risk": 0.2,
        "max_loss_per_trade_pct": 0.02,
        "risk_per_trade": 0.01
    },
    {
        "preset_name": "moderate",
        "max_positions": 5,
        "position_size_pct": 0.10,
        "min_trade_size": 10,
        "use_dynamic_sl_tp": True,
        "atr_multiplier_sl": 2.0,
        "atr_multiplier_tp": 3.0,
        "min_risk_reward_ratio": 1.5,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.05,
        "trailing_stop_pct": 0.03,
        "trading_fee_pct": 0.001,
        "slippage_pct": 0.0005,
        "max_portfolio_risk": 0.2,
        "max_loss_per_trade_pct": 0.02,
        "risk_per_trade": 0.02
    },
    {
        "preset_name": "aggressive",
        "max_positions": 8,
        "position_size_pct": 0.15,
        "min_trade_size": 10,
        "use_dynamic_sl_tp": True,
        "atr_multiplier_sl": 2.5,
        "atr_multiplier_tp": 4.0,
        "min_risk_reward_ratio": 1.5,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.10,
        "trailing_stop_pct": 0.05,
        "trading_fee_pct": 0.001,
        "slippage_pct": 0.0005,
        "max_portfolio_risk": 0.2,
        "max_loss_per_trade_pct": 0.02,
        "risk_per_trade": 0.03
    }
]

print("Inserting risk presets into Supabase...")

for preset in presets:
    response = supabase.table("risk_presets").insert(preset).execute()
    if response.data:
        print(f"Inserted: {preset['preset_name']}")
    elif response.status_code in (200, 201, 204):
        print(f"Inserted (no body returned): {preset['preset_name']} (status={response.status_code})")
    else:
        print(f"Error inserting {preset['preset_name']}: status={response.status_code} error={response.error}")

print("Done! Check your Supabase dashboard → Table editor → risk_presets")