from dotenv import load_dotenv
from supabase import create_client
import os

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(url, key)

print("=== CHECKING TABLES ===\n")

print("1. Backtests table:")
try:
    backtests = supabase.table("backtests").select("*").limit(5).execute()
    print(f"   Rows: {len(backtests.data)}")
    if backtests.data:
        print(f"   Sample: {backtests.data[0]}")
    else:
        print("   EMPTY")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n2. Risk presets table:")
try:
    presets = supabase.table("risk_presets").select("*").execute()
    print(f"   Rows: {len(presets.data)}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n3. Coins table:")
try:
    coins = supabase.table("coins").select("*").execute()
    print(f"   Rows: {len(coins.data)}")
except Exception as e:
    print(f"   ERROR: {e}")
