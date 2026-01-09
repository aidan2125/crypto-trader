# database/test_supabase.py

from dotenv import load_dotenv
from supabase import create_client
import os

# Load .env file
load_dotenv()

# Get credentials
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")

# Check if loaded
if not url or not key:
    print("ERROR: SUPABASE_URL or SUPABASE_ANON_KEY missing in .env file")
    print("Make sure your .env has:")
    print("SUPABASE_URL=https://your-project.supabase.co")
    print("SUPABASE_ANON_KEY=your-anon-key")
else:
    try:
        # Connect to Supabase
        supabase = create_client(url, key)
        
        # Simple test query: count rows in risk_presets (or any table you have)
        response = supabase.table("risk_presets").select("*").limit(1).execute()
        
        print("SUCCESS: Connected to Supabase!")
        print(f"Project URL: {url}")
        print(f"Test query response: {response.data}")
        
    except Exception as e:
        print(f"Connection FAILED: {e}")
