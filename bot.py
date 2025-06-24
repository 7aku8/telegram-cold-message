import asyncio
import os
import random

from telethon import TelegramClient, events
import openai
import datetime
import sqlite3
import atexit
from dotenv import load_dotenv

from database import get_lead, create_lead, create_message
from ai_utils import is_lead_relevant, generate_first_message
from webhook import send_webhook

load_dotenv()

# === CONFIGURATION ===
api_id = int(os.getenv("API_ID", 1))
api_hash = os.getenv("API_HASH", "your_api_hash_here")
session_name = 'filip_session'
# chat_ids = [
#     1626522644,  # Gubbin's lounge
#     1652712042,  # Suits Calls | USA
#     1710145932,  # Nanocaps - BSC
#     1790816396,  # SHILLGROW 🚀| HardShill Lounge on BSC
#     1505362437,  # Prods Shills
# ]
chat_ids = [
-4876574630,  # P100 - Crypto Business Accounts
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


def can_process_messages():
    """Check if enough time has passed since last message to process new ones"""
    return True
    # last_time = get_last_message_time()
    # if last_time is None:
    #     return True
    #
    # time_diff = datetime.datetime.now() - last_time
    # return time_diff.total_seconds() >= (COOLDOWN_MINUTES * 60)


def get_remaining_cooldown_minutes():
    """Get remaining minutes in cooldown period"""
    return 0
    # last_time = get_last_message_time()
    # if last_time is None:
    #     return 0
    #
    # time_diff = datetime.datetime.now() - last_time
    # remaining_seconds = (COOLDOWN_MINUTES * 60) - time_diff.total_seconds()
    # return max(0, int(remaining_seconds / 60))


@client.on(events.NewMessage())
async def on_new_message(event):
    chat_id = event.chat_id

    is_lead = get_lead(chat_id)

    if is_lead:
        print(f"Lead already exists for chat ID {chat_id}, skipping...")
        return


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
    if get_lead(sender_id):
        print(f"⚠️ Already messaged {sender_name} (ID: {sender_id}), skipping...")
        return

    if is_lead_relevant(text):
        try:
            print(f"✅ Relevant message detected from {sender_name} (ID: {sender_id})")

            if os.getenv("ENVIRONMENT") == "production":
                delay_minutes = random.randint(2, 6)
                delay_seconds = delay_minutes * 60
                print(f"⏳ Sleeping for {delay_minutes} minutes before messaging {sender_name}...")
                await asyncio.sleep(delay_seconds)

            message = generate_first_message(sender_name, text)

            await client.send_message(sender_id, message)

            # Update rate limit timestamp - this starts the 15-minute cooldown
            # update_last_message_time()
            print(f"🔒 Rate limit activated. No messages will be processed for {COOLDOWN_MINUTES} minutes.")

            lead = create_lead(sender_id, os.getenv("BOT_ID", "unknown"), sender_name, username)
            print(f"Lead created: {lead}")
            create_message(lead.id, 'bot', message)

            # Save to log
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(
                    f"[{datetime.datetime.now()}] Sent message to {sender_name} (ID: {sender_id}) [username: {username}]\n")

            # Send webhook
            await send_webhook(username)
            print(f"📩 Message and webhook sent for {sender_name}")
        except Exception as e:
            print(f"❌ Failed to message {sender_name}: {e}")


with client:
    print("Bot is running and monitoring the group...")
    print(f"Rate limiting: {COOLDOWN_MINUTES} minute cooldown after each message sent")
    client.run_until_disconnected()