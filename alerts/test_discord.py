import os
import requests

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not WEBHOOK_URL:
    print("❌ No webhook URL set in environment.")
    print("Please run: export DISCORD_WEBHOOK_URL='your_webhook_url_here'")
else:
    print(f"Testing Discord webhook...")
    print(f"Webhook URL (first 50 chars): {WEBHOOK_URL[:50]}...")
    
    data = {"content": "✅ Discord webhook test — local script working!"}
    try:
        response = requests.post(WEBHOOK_URL, json=data, timeout=10)
        print(f"Status code: {response.status_code}")
        print(f"Response text: {repr(response.text)}")
        
        if response.status_code == 204:
            print("✅ SUCCESS! Check your Discord channel for the test message.")
        else:
            print(f"❌ FAILED! Status code {response.status_code}")
            print(f"Response: {response.text}")
    except requests.exceptions.Timeout:
        print("❌ Error: Request timed out")
    except requests.exceptions.ConnectionError:
        print("❌ Error: Connection failed - check your internet")
    except Exception as e:
        print(f"❌ Error sending Discord message: {e}")