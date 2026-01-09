import os
from dotenv import load_dotenv
from supabase import create_client
from supabase.client import Client

# Load environment variables from .env (optional but recommended)
load_dotenv()

# Get credentials – falls back to direct env if no .env
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment or .env file")

# Create the client (singleton pattern – create once and reuse)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Optional: Customize client options (e.g., timeouts, schema)
# from supabase.client import ClientOptions
# supabase: Client = create_client(
#     SUPABASE_URL,
#     SUPABASE_KEY,
#     options=ClientOptions(
#         schema="public",  # or "storage" for storage ops
#         postgrest_client_timeout=10,
#     )
# )

# Example function to test/get active preset (based on your earlier import)
def get_active_preset() -> dict | None:
    """
    Example: Fetch the active preset from a 'presets' table.
    Adjust table/columns to match your schema.
    """
    try:
        response = supabase.table("presets").select("*").eq("is_active", True).execute()
        if response.data:
            return response.data[0]  # Return first active preset
        return None
    except Exception as e:
        print(f"Error fetching active preset: {e}")
        return None

# For async/realtime usage (if needed later):
# from supabase import acreate_client
# supabase_async = await acreate_client(SUPABASE_URL, SUPABASE_KEY)