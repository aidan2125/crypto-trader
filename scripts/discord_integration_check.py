import os
import sys

from alerts import discord_alerts

if not os.getenv("DISCORD_WEBHOOK_URL"):
    sys.exit("DISCORD_WEBHOOK_URL not set")

ok = discord_alerts.send_discord_message("Integration test alert from CI")
print("send_discord_message returned:", ok)
sys.exit(0 if ok else "Discord send returned False")
