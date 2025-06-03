import asyncio
import os
import random

from openai import OpenAI
from telethon import TelegramClient, events
import openai
import datetime
import aiohttp
import sqlite3
import atexit
import certifi
import ssl
from dotenv import load_dotenv

load_dotenv()

ssl_context = ssl.create_default_context(cafile=certifi.where())

# === CONFIGURATION ===
api_id = int(os.getenv("API_ID", 1))
api_hash = os.getenv("API_HASH", "your_api_hash_here")
session_name = 'filip_session'
chat_ids = [
    1626522644,  # Gubbin's lounge
    1652712042,  # Suits Calls | USA
    1710145932,  # Nanocaps - BSC
    1790816396,  # SHILLGROW 🚀| HardShill Lounge on BSC
    1505362437,  # Prods Shills
]
openai.api_key = os.getenv("OPENAI_API_KEY", "your_openai_api_key_here")
webhook_url = os.getenv("WEBHOOK_URL", "https://your-n8n-webhook-url.com/webhook")

message_template = '''Hi, I saw you're active in some crypto-related groups. If you're running a project or company in the crypto space, you might find what we do at P100 interesting, we offer crypto-friendly business accounts, 
IBANs, wallets, and Mastercards, all accessible via API.

Let me know if that sounds relevant, happy to share more details.
'''

log_file = 'sent_messages_log.txt'

client = TelegramClient(session_name, api_id, api_hash)

# === RATE LIMITING ===
COOLDOWN_MINUTES = 15

# === DATABASE SETUP ===
conn = sqlite3.connect('messaged_users.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS messaged_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    timestamp TEXT
)
''')

# Add table for tracking last message time
cursor.execute('''
CREATE TABLE IF NOT EXISTS rate_limit (
    id INTEGER PRIMARY KEY,
    last_message_time TEXT
)
''')
conn.commit()


def get_last_message_time():
    """Get the timestamp of when the last message was sent"""
    cursor.execute("SELECT last_message_time FROM rate_limit WHERE id = 1")
    result = cursor.fetchone()
    if result:
        return datetime.datetime.fromisoformat(result[0])
    return None


def update_last_message_time():
    """Update the timestamp of when a message was sent"""
    current_time = datetime.datetime.now().isoformat()
    cursor.execute("INSERT OR REPLACE INTO rate_limit (id, last_message_time) VALUES (1, ?)", (current_time,))
    conn.commit()


def can_process_messages():
    """Check if enough time has passed since last message to process new ones"""
    last_time = get_last_message_time()
    if last_time is None:
        return True

    time_diff = datetime.datetime.now() - last_time
    return time_diff.total_seconds() >= (COOLDOWN_MINUTES * 60)


def get_remaining_cooldown_minutes():
    """Get remaining minutes in cooldown period"""
    last_time = get_last_message_time()
    if last_time is None:
        return 0

    time_diff = datetime.datetime.now() - last_time
    remaining_seconds = (COOLDOWN_MINUTES * 60) - time_diff.total_seconds()
    return max(0, int(remaining_seconds / 60))


def has_already_messaged(user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM messaged_users WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None


def record_messaged_user(user_id: int, username: str):
    timestamp = datetime.datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO messaged_users (user_id, username, timestamp) VALUES (?, ?, ?)",
        (user_id, username, timestamp)
    )
    conn.commit()


atexit.register(lambda: conn.close())


# === AI ANALYSIS FUNCTION ===
def is_lead_relevant(message_text):
    try:
        openai_client = OpenAI(
            api_key=openai.api_key,
        )

        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "You are a crypto business lead classifier."},
                {"role": "user",
                 "content": f"Does this message suggest the user is working on a crypto-related company or project "
                            f"that might need business accounts, crypto infrastructure, or financial APIs? Respond "
                            f"only with 'yes' or 'no'. Message: {message_text}"}
            ]
        )

        answer = response.choices[0].message.content
        print(f"AI response: {answer}")

        return 'yes' in answer
    except Exception as e:
        print(f"AI analysis failed: {e}")
        return False


async def send_n8n_webhook_async(username: str):
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


# === MAIN EVENT HANDLER ===
@client.on(events.NewMessage(chat_ids))
async def handler(event):
    sender = await event.get_sender()
    sender_name = sender.first_name or "there"
    sender_id = sender.id
    username = sender.username if sender.username else "no_username"
    text = event.message.message

    print(f"New message from {sender_name} (ID: {sender_id})")

    # Check if we're still in cooldown period
    if not can_process_messages():
        remaining_minutes = get_remaining_cooldown_minutes()
        print(f"⏳ Rate limit active. {remaining_minutes} minutes remaining before processing messages again.")
        return

    # Skip if already messaged
    if has_already_messaged(sender_id):
        print(f"⚠️ Already messaged {sender_name} (ID: {sender_id}), skipping...")
        return

    if is_lead_relevant(text):
        try:
            print(f"✅ Relevant message detected from {sender_name} (ID: {sender_id})")
            record_messaged_user(sender_id, username)

            delay_minutes = random.randint(2, 6)
            delay_seconds = delay_minutes * 60
            print(f"⏳ Sleeping for {delay_minutes} minutes before messaging {sender_name}...")
            await asyncio.sleep(delay_seconds)

            await client.send_message(sender_id, message_template.format(first_name=sender_name))

            # Update rate limit timestamp - this starts the 15-minute cooldown
            update_last_message_time()
            print(f"🔒 Rate limit activated. No messages will be processed for {COOLDOWN_MINUTES} minutes.")

            # Save to log
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(
                    f"[{datetime.datetime.now()}] Sent message to {sender_name} (ID: {sender_id}) [username: {username}]\n")

            # Send webhook
            await send_n8n_webhook_async(username)
            print(f"📩 Message and webhook sent for {sender_name}")
        except Exception as e:
            print(f"❌ Failed to message {sender_name}: {e}")


with client:
    print("Bot is running and monitoring the group...")
    print(f"Rate limiting: {COOLDOWN_MINUTES} minute cooldown after each message sent")
    client.run_until_disconnected()