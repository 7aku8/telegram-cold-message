import datetime
import os
import ssl

import aiohttp
import certifi

webhook_url = os.getenv("WEBHOOK_URL", "https://your-n8n-webhook-url.com/webhook")

ssl_context = ssl.create_default_context(cafile=certifi.where())


async def send_webhook(username: str):
    payload = {
        'username': username,
        'timestamp': datetime.datetime.now().isoformat()
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, timeout=5, ssl=ssl_context) as resp:
                if resp.status == 200:
                    print(f"✅ Async webhook sent for {username}")
                else:
                    print(f"❌ Async webhook failed: {resp.status}")
    except Exception as e:
        print(f"🚨 Async webhook error: {e}")
