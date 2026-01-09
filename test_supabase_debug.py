#!/usr/bin/env python3
"""
Debug Supabase connectivity and query responses.
Tests insert, select, and table discovery.
"""

import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_ANON_KEY")

print(f"URL: {url}")
print(f"Key: {key[:20]}..." if key else "Key: None")
print()

if not url or not key:
    print("ERROR: SUPABASE_URL or SUPABASE_ANON_KEY not set in .env")
    exit(1)

try:
    from supabase import create_client
    supabase = create_client(url, key)
    print("✓ Supabase client created successfully\n")
except Exception as e:
    print(f"✗ Failed to create Supabase client: {e}")
    exit(1)

# Test 1: List tables by querying common preset table names
print("=" * 60)
print("TEST 1: Query for active presets in known tables")
print("=" * 60)

for table_name in ["active_preset", "active_presets", "presets", "risk_presets"]:
    print(f"\nTrying table: '{table_name}'")
    try:
        response = supabase.table(table_name).select("*").limit(5).execute()
        print(f"  Response type: {type(response)}")
        
        if isinstance(response, dict):
            data = response.get("data", [])
        else:
            data = getattr(response, "data", [])
        
        print(f"  Data returned: {len(data)} rows")
        if data:
            print(f"  Sample row: {data[0]}")
    except Exception as e:
        print(f"  Error: {e}")

# Test 2: Query for active=True record
print("\n" + "=" * 60)
print("TEST 2: Query for active=true in 'presets' table")
print("=" * 60)
try:
    response = supabase.table("presets").select("*").eq("active", True).execute()
    print(f"Response type: {type(response)}")
    
    if isinstance(response, dict):
        data = response.get("data", [])
    else:
        data = getattr(response, "data", [])
    
    print(f"Rows found: {len(data)}")
    if data:
        print(f"Sample: {data[0]}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Query for preset by name
print("\n" + "=" * 60)
print("TEST 3: Query for preset name='moderate' in 'presets' table")
print("=" * 60)
try:
    response = supabase.table("presets").select("*").eq("name", "moderate").execute()
    print(f"Response type: {type(response)}")
    
    if isinstance(response, dict):
        data = response.get("data", [])
    else:
        data = getattr(response, "data", [])
    
    print(f"Rows found: {len(data)}")
    if data:
        print(f"Result: {data[0]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("Debug complete. Check results above.")
print("=" * 60)
