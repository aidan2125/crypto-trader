#!/usr/bin/env python3
"""
test_telegram.py
Run from your project root:  python test_telegram.py

Tests your Telegram bot token + chat ID before wiring into the full bot.
Requires env vars:
    TELEGRAM_BOT_TOKEN   — from BotFather
    TELEGRAM_CHAT_ID     — your personal user ID (get it from @userinfobot)

Run with:
    TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python test_telegram.py
Or set them in your .env and load with:
    export $(cat .env | xargs) && python test_telegram.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

PASS = "pass"
FAIL = "fail"
errors = []

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {label}")
    else:
        msg = f"  {FAIL}  {label}" + (f"\n       → {detail}" if detail else "")
        print(msg)
        errors.append(label)

def tg_get(token: str, method: str, params: dict = None) -> dict:
    """Minimal Telegram API call using only stdlib (no requests needed)."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        data = json.dumps(params).encode()
        req  = urllib.request.Request(url, data=data,
                                       headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


print("\n" + "="*55)
print("  Telegram bot smoke test")
print("="*55 + "\n")

# ── 1. Env vars present ────────────────────────────────────────────────────
print("1. Environment variables")
token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

check("TELEGRAM_BOT_TOKEN set",  bool(token),
      "export TELEGRAM_BOT_TOKEN=your_token")
check("TELEGRAM_CHAT_ID set",    bool(chat_id),
      "export TELEGRAM_CHAT_ID=your_chat_id  (get it from @userinfobot)")

if not token or not chat_id:
    print("\n  Cannot continue without both env vars.\n")
    sys.exit(1)

# ── 2. Token format sanity ─────────────────────────────────────────────────
print("\n2. Token format")
check("Token contains ':'",       ":" in token,
      "BotFather tokens look like  1234567890:AAFxxx...")
check("Token length looks right", 40 < len(token) < 60,
      f"Got length {len(token)} — double-check you copied the full token")
check("Chat ID is numeric",       chat_id.lstrip("-").isdigit(),
      "Chat ID should be a plain number like 123456789")

# ── 3. getMe — validates the token ────────────────────────────────────────
print("\n3. Validate token via getMe")
try:
    resp = tg_get(token, "getMe")
    bot  = resp.get("result", {})
    check("API responded ok=true",   resp.get("ok") is True)
    check("Bot username returned",   bool(bot.get("username")),
          f"Got: {bot}")
    if bot.get("username"):
        print(f"       Bot name: @{bot['username']}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    check("getMe HTTP request",      False, f"HTTP {e.code}: {body}")
except Exception as e:
    check("getMe request",           False, str(e))

if errors:
    print("\n  Token invalid — fix it before continuing.\n")
    sys.exit(1)

# ── 4. sendMessage — sends a real test message to you ─────────────────────
print("\n4. Send test message to your chat")
ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
msg = (
    f"🤖 Trading Bot — Connection Test\n\n"
    f"✅ Token:   valid\n"
    f"✅ Chat ID: {chat_id}\n"
    f"🕐 Time:   {ts}\n\n"
    f"If you see this, Telegram alerts are working."
)
try:
    resp = tg_get(token, "sendMessage", {
        "chat_id": chat_id,
        "text":    msg,
    })
    check("sendMessage ok=true",   resp.get("ok") is True,
          json.dumps(resp))
    msg_id = resp.get("result", {}).get("message_id")
    check("message_id returned",  bool(msg_id))
    if msg_id:
        print(f"       Message ID: {msg_id} — check your Telegram now!")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    check("sendMessage HTTP request", False, f"HTTP {e.code}: {body}")
    if "chat not found" in body.lower():
        print("\n  Tip: you need to send /start to your bot first.")
        print("       Open Telegram → search your bot → press Start.\n")
except Exception as e:
    check("sendMessage request", False, str(e))

# ── 5. Test via your existing telegram_alerts.py ──────────────────────────
print("\n5. Test via alerts/telegram_alerts.py (your module)")
try:
    sys.path.insert(0, ".")
    from alerts.telegram_alerts import send_telegram_message
    result = send_telegram_message(
        f"🤖 alerts/telegram_alerts.py module test — {ts}"
    )
    check("send_telegram_message() returned truthy", bool(result))
except ImportError:
    print(f"  ⚠️   alerts/telegram_alerts.py not found — skipping module test")
    print(f"       (This is fine — just means the import path isn't set up yet)")
except Exception as e:
    check("send_telegram_message()", False, str(e))

# ── Result ────────────────────────────────────────────────────────────────
print("\n" + "="*55)
if not errors:
    print(f"  {PASS}  All checks passed")
    print(f"       You should see 1-2 messages in your Telegram chat.")
else:
    print(f"  {FAIL}  {len(errors)} check(s) failed:")
    for e in errors:
        print(f"       • {e}")
print("="*55 + "\n")

sys.exit(1 if errors else 0)