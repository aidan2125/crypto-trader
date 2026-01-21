# ============================================
# FILE 1: database/supabase_client.py
# ============================================

import os
from dotenv import load_dotenv
from supabase import create_client
from supabase.client import Client

# Load environment variables from .env
load_dotenv()

# Get credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment or .env file")

# Create the client (singleton pattern – create once and reuse)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("✓ Supabase client initialized successfully")
